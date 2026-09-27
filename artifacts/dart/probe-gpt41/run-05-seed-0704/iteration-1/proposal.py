from hypothesis import strategies as st

# Constants for allowed status values
STATUS_VALUES = ["active", "inactive", "unknown"]

# Helper to produce JSON string literal from Python string (escape minimal set)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote minimally for JSON string
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing a Record with fields:
    {
      "id": <integer>,
      "amount": <string>,
      "name": <string or null or missing>,
      "status": <one of allowed strings or null or missing>,
      "tags": <array of strings or missing or object (to trigger divergence)>,
      "child": <Record or null or missing or invalid type (to trigger divergence)>
    }
    Strategy tries to produce documents that are almost well-formed with one or two fields
    varied to provoke divergence among four Dart JSON deserializers.
    """

    # --- id: always integer (required, no variation) ---
    id_val = draw(st.integers(min_value=0, max_value=1000000))

    # --- amount: always string (required, no variation) ---
    amount_val = draw(st.text(min_size=1, max_size=20))

    # --- name: string or null or missing (missing triggers divergence) ---
    # 80% present, 20% missing to provoke divergence on missing name
    name_present = draw(st.booleans().map(lambda b: b if b else False))  # bias to present
    # Actually bias 90% present, 10% missing
    name_present = draw(st.booleans().filter(lambda b: b or draw(st.booleans())))

    if name_present:
        # 80% string, 20% null (both accepted)
        name_val = draw(st.one_of(st.none(), st.text(max_size=20)))
        name_field = '"name":' + ( "null" if name_val is None else json_string_literal(name_val) )
    else:
        name_field = None  # missing

    # --- status: one of allowed strings, or null, or missing, or invalid string ---
    # To provoke divergence:
    # - missing (all reject except maybe D? known: no)
    # - null (known: A rejects _TypeError, B/C ArgumentError, D DeserializationError)
    # - invalid string (known: A/B/C ArgumentError, D DeserializationError)
    # - valid string (normal)
    status_choice = draw(st.sampled_from(["valid", "null", "invalid", "missing"]))
    if status_choice == "valid":
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_field = '"status":' + json_string_literal(status_val)
    elif status_choice == "null":
        status_field = '"status":null'
    elif status_choice == "invalid":
        # invalid string not in allowed set
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES))
        status_field = '"status":' + json_string_literal(invalid_status)
    else:  # missing
        status_field = None

    # --- tags: array of strings, or missing, or object (to provoke divergence) ---
    # Known: missing and object accepted only by D_built_value, rejected by others
    tags_choice = draw(st.sampled_from(["valid", "missing", "object", "invalid_list"]))
    if tags_choice == "valid":
        # valid list of strings (0 to 5 strings)
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10), max_size=5))
        # encode as JSON array of strings
        tags_field = '"tags":[' + ",".join(json_string_literal(s) for s in tags_list) + ']'
    elif tags_choice == "missing":
        tags_field = None
    elif tags_choice == "object":
        # object instead of list, triggers divergence
        # minimal object: empty or one string field
        obj_key = draw(st.text(min_size=1, max_size=5))
        obj_val = draw(st.text(min_size=1, max_size=5))
        tags_field = '"tags":{' + json_string_literal(obj_key) + ":" + json_string_literal(obj_val) + '}'
    else:  # invalid_list: list with non-string element (e.g. null or int)
        # Known: all reject, no divergence, but keep for coverage
        invalid_elem = draw(st.one_of(st.none(), st.integers()))
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10), max_size=3))
        # Insert invalid element at random position
        pos = draw(st.integers(min_value=0, max_value=len(tags_list)))
        tags_list = tags_list[:pos] + [invalid_elem] + tags_list[pos:]
        # Encode list with invalid element
        def encode_elem(e):
            if e is None:
                return "null"
            elif isinstance(e, int):
                return str(e)
            else:
                return json_string_literal(e)
        tags_field = '"tags":[' + ",".join(encode_elem(e) for e in tags_list) + ']'

    # --- child: null, valid nested record, missing, or invalid type (string or empty object) ---
    # To keep recursion bounded, limit depth to 1 (no grandchildren)
    # 70% null, 10% missing, 10% valid nested, 10% invalid type
    child_choice = draw(st.sampled_from(["null", "missing", "valid", "invalid_string", "invalid_empty_obj"]))
    if child_choice == "null":
        child_field = '"child":null'
    elif child_choice == "missing":
        child_field = None
    elif child_choice == "valid":
        # valid nested record with no further child (child=null)
        # id int, amount string, name string or null, status valid string, tags valid list, child null
        nested_id = draw(st.integers(min_value=0, max_value=1000000))
        nested_amount = draw(st.text(min_size=1, max_size=20))
        nested_name = draw(st.one_of(st.none(), st.text(max_size=20)))
        nested_status = draw(st.sampled_from(STATUS_VALUES))
        nested_tags = draw(st.lists(st.text(min_size=1, max_size=10), max_size=3))
        # Compose nested JSON string
        nested_name_field = '"name":' + ("null" if nested_name is None else json_string_literal(nested_name))
        nested_tags_field = '"tags":[' + ",".join(json_string_literal(s) for s in nested_tags) + ']'
        nested_child_field = '"child":null'
        nested_json = (
            '{'
            + f'"id":{nested_id},'
            + f'"amount":{json_string_literal(nested_amount)},'
            + nested_name_field + ','
            + f'"status":{json_string_literal(nested_status)},'
            + nested_tags_field + ','
            + nested_child_field
            + '}'
        )
        child_field = '"child":' + nested_json
    elif child_choice == "invalid_string":
        # child is a string (invalid type)
        child_field = '"child":' + json_string_literal("invalid_child_string")
    else:  # invalid_empty_obj
        # child is empty object (invalid)
        child_field = '"child":{}'

    # Compose fields list, omitting missing fields
    fields = [
        f'"id":{id_val}',
        f'"amount":{json_string_literal(amount_val)}',
    ]
    if name_field is not None:
        fields.append(name_field)
    if status_field is not None:
        fields.append(status_field)
    if tags_field is not None:
        fields.append(tags_field)
    if child_field is not None:
        fields.append(child_field)

    # Shuffle fields order to avoid bias
    fields = draw(st.permutations(fields))

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")