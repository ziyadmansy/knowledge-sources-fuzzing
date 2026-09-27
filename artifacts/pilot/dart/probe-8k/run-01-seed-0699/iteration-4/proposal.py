from hypothesis import strategies as st

# Constants for enum values
STATUS_VALUES = ["active", "inactive", "unknown"]

# Helper: JSON string escaping for simple ASCII strings without control chars
def json_string(s: str) -> str:
    # Escape backslash and double quote only (minimal)
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects matching the record schema,
    with subtle variations designed to provoke divergence between four Dart JSON
    deserializers (manual, json_serializable, freezed, built_value).

    Strategy:
    - Start from a valid record.
    - Introduce exactly one "almost well-formed" deviation:
      * Missing a required field (id, amount, name, status, tags, child)
      * Wrong type for exactly one field (but only one at a time)
      * Enum field "status" with borderline invalid value (e.g. correct casing but unknown string)
      * Null vs missing vs present-but-null distinctions
      * Empty arrays vs arrays with empty strings
      * Nested child with similar deviations (one level only)
    - Otherwise valid fields and structure.
    - Duplicate keys with last-wins already known to be consistent, so avoid duplicates here.
    """

    # Base valid values
    valid_id = st.integers(min_value=0, max_value=1000)
    valid_amount = st.text(min_size=1, max_size=10).map(lambda s: s if s != "" else "0")
    valid_name = st.one_of(st.none(), st.text(min_size=1, max_size=10))
    valid_status = st.sampled_from(STATUS_VALUES)
    valid_tag = st.text(min_size=0, max_size=5)  # empty string allowed
    valid_tags = st.lists(valid_tag, min_size=0, max_size=3)
    # child is either null or a record (one level recursion)

    # Compose a valid record dict (not JSON text yet)
    @st.composite
    def record(draw, allow_missing_field=None, wrong_type_field=None, wrong_type_in_child=None, missing_in_child=None, wrong_enum_in_child=False):
        """
        allow_missing_field: one of the six fields or None
        wrong_type_field: one of the six fields or None
        wrong_type_in_child: one of the six fields or None
        missing_in_child: one of the six fields or None
        wrong_enum_in_child: bool, if True child.status is invalid enum string
        """

        # id field
        if allow_missing_field == "id":
            id_val = None
        elif wrong_type_field == "id":
            # id must be int, so give string
            id_val = draw(st.text(min_size=1, max_size=3))
        else:
            id_val = draw(valid_id)

        # amount field
        if allow_missing_field == "amount":
            amount_val = None
        elif wrong_type_field == "amount":
            # amount must be string, give int
            amount_val = draw(st.integers(min_value=0, max_value=100))
        else:
            amount_val = draw(valid_amount)

        # name field
        if allow_missing_field == "name":
            name_val = None
        elif wrong_type_field == "name":
            # name must be string or null, give int
            name_val = draw(st.integers(min_value=0, max_value=100))
        else:
            name_val = draw(valid_name)

        # status field
        if allow_missing_field == "status":
            status_val = None
        elif wrong_type_field == "status":
            # status must be enum string, give string not in enum
            status_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES))
        else:
            status_val = draw(valid_status)

        # tags field
        if allow_missing_field == "tags":
            tags_val = None
        elif wrong_type_field == "tags":
            # tags must be array of strings, give array with int or string
            # To keep JSON valid, choose array with one int element
            tags_val = [draw(st.integers(min_value=0, max_value=10))]
        else:
            tags_val = draw(valid_tags)

        # child field
        if allow_missing_field == "child":
            child_val = None
        elif wrong_type_field == "child":
            # child must be null or record, give wrong type (e.g. integer)
            child_val = draw(st.integers(min_value=0, max_value=10))
        else:
            # Compose child record or null
            # If no wrong_type_in_child or missing_in_child or wrong_enum_in_child, child is valid or null
            child_is_null = draw(st.booleans())
            if child_is_null:
                child_val = None
            else:
                # Compose child record with possible deviations
                child_val = draw(record(
                    allow_missing_field=missing_in_child,
                    wrong_type_field=wrong_type_in_child,
                    wrong_type_in_child=None,
                    missing_in_child=None,
                    wrong_enum_in_child=wrong_enum_in_child,
                ))

        # Build dict with only present fields (skip missing)
        obj = {}
        if id_val is not None or allow_missing_field != "id":
            obj["id"] = id_val
        if amount_val is not None or allow_missing_field != "amount":
            obj["amount"] = amount_val
        if name_val is not None or allow_missing_field != "name":
            obj["name"] = name_val
        if status_val is not None or allow_missing_field != "status":
            obj["status"] = status_val
        if tags_val is not None or allow_missing_field != "tags":
            obj["tags"] = tags_val
        if child_val is not None or allow_missing_field != "child":
            obj["child"] = child_val

        return obj

    # Choose one deviation type or none (mostly none to keep valid)
    deviation_type = draw(st.sampled_from([
        "missing_field",
        "wrong_type_field",
        "wrong_type_in_child",
        "missing_in_child",
        "wrong_enum_in_child",
        "none"
    ]))

    # Pick which field to affect if applicable
    fields = ["id", "amount", "name", "status", "tags", "child"]

    if deviation_type == "missing_field":
        missing_field = draw(st.sampled_from(fields))
        obj = draw(record(allow_missing_field=missing_field))
    elif deviation_type == "wrong_type_field":
        wrong_field = draw(st.sampled_from(fields))
        obj = draw(record(wrong_type_field=wrong_field))
    elif deviation_type == "wrong_type_in_child":
        wrong_field = draw(st.sampled_from(fields))
        obj = draw(record(wrong_type_in_child=wrong_field))
    elif deviation_type == "missing_in_child":
        missing_field = draw(st.sampled_from(fields))
        obj = draw(record(missing_in_child=missing_field))
    elif deviation_type == "wrong_enum_in_child":
        obj = draw(record(wrong_enum_in_child=True))
    else:
        # no deviation, fully valid record
        obj = draw(record())

    # Now serialize obj to JSON text manually (no json module)
    # We know all fields present or missing, values are int, str, None, list[str], or nested dict or None

    def serialize_value(v):
        if v is None:
            return "null"
        elif isinstance(v, bool):
            return "true" if v else "false"
        elif isinstance(v, int):
            return str(v)
        elif isinstance(v, str):
            return json_string(v)
        elif isinstance(v, list):
            # list of strings only (tags)
            return "[" + ",".join(serialize_value(x) for x in v) + "]"
        elif isinstance(v, dict):
            # nested record
            return serialize_obj(v)
        else:
            # Unexpected type (e.g. int for child wrong_type_field)
            # Serialize as JSON number or string accordingly
            # If int, str it
            return str(v)

    def serialize_obj(d):
        # d is dict with keys from schema, values as above
        # Serialize keys in fixed order for determinism
        parts = []
        for key in ["id", "amount", "name", "status", "tags", "child"]:
            if key in d:
                parts.append(json_string(key) + ":" + serialize_value(d[key]))
        return "{" + ",".join(parts) + "}"

    json_text = serialize_obj(obj)

    return json_text.encode("utf-8")