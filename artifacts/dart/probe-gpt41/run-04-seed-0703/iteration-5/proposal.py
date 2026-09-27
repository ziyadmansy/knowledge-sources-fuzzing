from hypothesis import strategies as st

# Constants for fixed enums and null
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
NULL = "null"

# Helper to produce a JSON string literal from a Python string (escaping " and \)
def json_string_literal(s: str) -> str:
    # minimal escaping for " and \
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to provoke divergence between four Dart JSON deserializers.
    """

    # --- Primitive fields strategies ---

    # id: integer only (no floats or strings)
    id_val = draw(st.integers(min_value=-(2**31), max_value=2**31-1))

    # amount: string (always present, non-null)
    # Use strings that look numeric or edge cases to provoke subtle differences
    amount_val = draw(
        st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
            st.sampled_from(["0", "0.0", "-0", "123.456", "1e10", "NaN", "Infinity", "-Infinity"]),
        )
    )
    amount_json = json_string_literal(amount_val)

    # name: string or null, or missing (missing only for testing)
    # We want to test missing name (accepted by all as null) and present name (string or null)
    # To provoke divergence, sometimes omit, sometimes null, sometimes string
    name_option = draw(st.sampled_from(["present_string", "present_null", "missing"]))
    if name_option == "present_string":
        # string or empty string
        name_val = draw(st.text(min_size=0, max_size=20).filter(lambda s: '"' not in s and '\\' not in s))
        name_json = json_string_literal(name_val)
        name_field = f'"name":{name_json}'
    elif name_option == "present_null":
        name_field = f'"name":{NULL}'
    else:
        # missing name field
        name_field = None

    # status: one of the three valid strings, or invalid variants to provoke divergence
    # All reject null or invalid status, but built_value throws DeserializationError, others ArgumentError
    # To provoke divergence, sometimes use valid, sometimes invalid, sometimes null
    status_option = draw(
        st.sampled_from(
            [
                "valid",
                "null",
                "empty_string",
                "invalid_string",
            ]
        )
    )
    if status_option == "valid":
        status_val = draw(st.sampled_from(STATUS_VALUES))
    elif status_option == "null":
        status_val = NULL
    elif status_option == "empty_string":
        status_val = '""'
    else:
        # invalid string not in enum
        invalid_status = draw(
            st.text(min_size=1, max_size=10).filter(
                lambda s: s not in ["active", "inactive", "unknown"] and '"' not in s and '\\' not in s
            )
        )
        status_val = json_string_literal(invalid_status)

    status_field = f'"status":{status_val}'

    # tags: array of strings, or null (only built_value accepts null as []), or missing (only built_value accepts missing as [])
    # To provoke divergence, vary presence, null, empty array, array with strings, array with non-string (should be rejected by all)
    # We avoid non-string in tags because all reject it identically (no divergence)
    tags_option = draw(st.sampled_from(["present_array", "present_null", "missing"]))

    if tags_option == "present_array":
        # array of strings, possibly empty
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s), max_size=5))
        tags_json = "[" + ",".join(json_string_literal(t) for t in tags_list) + "]"
        tags_field = f'"tags":{tags_json}'
    elif tags_option == "present_null":
        tags_field = f'"tags":{NULL}'
    else:
        # missing tags field
        tags_field = None

    # child: null or nested record (one level only)
    # To provoke divergence, vary child presence, null, or malformed child (missing fields or wrong types)
    # But malformed child is rejected by all identically, so mostly test null or well-formed child with subtle variations
    child_option = draw(st.sampled_from(["null", "present_well_formed", "present_missing_field", "present_wrong_type"]))

    def gen_child():
        # child record must have all six fields, but we can vary one field to be missing or wrong type to provoke divergence
        # We produce a well-formed child or one with one subtle error

        # id: integer only
        child_id = draw(st.integers(min_value=-(2**31), max_value=2**31-1))

        # amount: string
        child_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
        child_amount_json = json_string_literal(child_amount)

        # name: string or null (always present here)
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s)))
        if child_name is None:
            child_name_json = NULL
        else:
            child_name_json = json_string_literal(child_name)

        # status: valid enum only here (to avoid all rejecting)
        child_status_json = draw(st.sampled_from(STATUS_VALUES))

        # tags: array of strings (empty or not)
        child_tags_list = draw(st.lists(st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s), max_size=3))
        child_tags_json = "[" + ",".join(json_string_literal(t) for t in child_tags_list) + "]"

        # child.child: always null (no deeper recursion)
        child_child_json = NULL

        # Build fields dict
        fields = {
            "id": str(child_id),
            "amount": child_amount_json,
            "name": child_name_json,
            "status": child_status_json,
            "tags": child_tags_json,
            "child": child_child_json,
        }

        # Possibly remove or corrupt one field if requested
        return fields

    if child_option == "null":
        child_field = f'"child":{NULL}'
    elif child_option == "present_well_formed":
        child_fields = gen_child()
        child_field = (
            '"child":{'
            + ",".join(f'"{k}":{v}' for k, v in child_fields.items())
            + "}"
        )
    elif child_option == "present_missing_field":
        # Remove one required field from child to provoke divergence
        child_fields = gen_child()
        remove_key = draw(st.sampled_from(["id", "amount", "status", "tags"]))
        del child_fields[remove_key]
        child_field = (
            '"child":{'
            + ",".join(f'"{k}":{v}' for k, v in child_fields.items())
            + "}"
        )
    else:  # present_wrong_type
        # Corrupt one field type in child (e.g. id as string, amount as number, status as null)
        child_fields = gen_child()
        corrupt_key = draw(st.sampled_from(["id", "amount", "status", "tags"]))
        if corrupt_key == "id":
            # id as string (should be rejected by all)
            child_fields["id"] = json_string_literal("not_an_int")
        elif corrupt_key == "amount":
            # amount as number (invalid type)
            child_fields["amount"] = "123"
        elif corrupt_key == "status":
            # status null (invalid)
            child_fields["status"] = NULL
        else:  # tags
            # tags as null (only built_value accepts)
            child_fields["tags"] = NULL
        child_field = (
            '"child":{'
            + ",".join(f'"{k}":{v}' for k, v in child_fields.items())
            + "}"
        )

    # Compose top-level fields list
    fields = [
        f'"id":{id_val}',
        f'"amount":{amount_json}',
        status_field,
        child_field,
    ]
    if name_field is not None:
        fields.append(name_field)
    if tags_field is not None:
        fields.append(tags_field)

    # Shuffle fields order to avoid positional bias
    fields = draw(st.permutations(fields))

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")