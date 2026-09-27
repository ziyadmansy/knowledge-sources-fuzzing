from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only for simplicity
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text for the record schema with controlled variations
    to provoke divergence among Gson, Moshi, kotlinx.serialization, and Jackson.
    """

    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]
    # For "status" field, sometimes use invalid or null to test enum handling divergence
    STATUS_INVALIDS = ["invalid", "null", "123", "true", ""]

    # Generate "id" as int or stringified int (both accepted by all)
    id_int = draw(st.integers(min_value=0, max_value=10**6))
    id_as_number = draw(st.booleans())
    id_json = str(id_int) if id_as_number else json_string(str(id_int))

    # Generate "amount" as string normally, but sometimes as number (Gson/Moshi/Jackson accept number, kotlinx rejects)
    amount_str = draw(st.text(min_size=1, max_size=10))
    amount_as_number = draw(st.booleans())
    if amount_as_number:
        # Try to parse amount_str as a number, else fallback to string
        try:
            # Try int first
            amount_num = int(amount_str)
            amount_json = str(amount_num)
        except Exception:
            try:
                amount_num = float(amount_str)
                amount_json = str(amount_num)
            except Exception:
                amount_json = json_string(amount_str)
    else:
        amount_json = json_string(amount_str)

    # Generate "name" as string or null normally, but sometimes as number or boolean (Gson/Moshi/Jackson accept non-string, kotlinx rejects)
    name_type = draw(st.sampled_from(["string", "null", "number", "boolean"]))
    if name_type == "string":
        name_val = draw(st.one_of(st.none(), st.text(max_size=10)))
        if name_val is None:
            name_json = "null"
        else:
            name_json = json_string(name_val)
    elif name_type == "null":
        name_json = "null"
    elif name_type == "number":
        name_json = str(draw(st.integers(min_value=-1000, max_value=1000)))
    else:  # boolean
        name_json = "true" if draw(st.booleans()) else "false"

    # Generate "status" as valid enum, invalid enum, or null (Gson accepts null/invalid as null, others reject)
    status_choice = draw(st.sampled_from(["valid", "invalid", "null"]))
    if status_choice == "valid":
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_json = json_string(status_val)
    elif status_choice == "invalid":
        status_json = json_string(draw(st.sampled_from(STATUS_INVALIDS)))
    else:
        status_json = "null"

    # Generate "tags" as array normally, but sometimes non-array (all reject non-array)
    tags_type = draw(st.sampled_from(["array", "non-array"]))
    if tags_type == "array":
        # Elements: strings normally, but sometimes non-string (Gson/Moshi/Jackson accept non-string elements, kotlinx rejects)
        tags_len = draw(st.integers(min_value=0, max_value=3))
        tags_elements = []
        for _ in range(tags_len):
            elem_type = draw(st.sampled_from(["string", "number", "boolean"]))
            if elem_type == "string":
                elem = json_string(draw(st.text(max_size=5)))
            elif elem_type == "number":
                elem = str(draw(st.integers(min_value=-100, max_value=100)))
            else:
                elem = "true" if draw(st.booleans()) else "false"
            tags_elements.append(elem)
        tags_json = "[" + ",".join(tags_elements) + "]"
    else:
        # Non-array: string, number, boolean, object, null
        non_array_type = draw(st.sampled_from(["string", "number", "boolean", "object", "null"]))
        if non_array_type == "string":
            tags_json = json_string(draw(st.text(max_size=5)))
        elif non_array_type == "number":
            tags_json = str(draw(st.integers(min_value=-100, max_value=100)))
        elif non_array_type == "boolean":
            tags_json = "true" if draw(st.booleans()) else "false"
        elif non_array_type == "object":
            # empty object
            tags_json = "{}"
        else:
            tags_json = "null"

    # Generate "child" as null, missing, empty object (Gson accepts empty object, others reject),
    # or nested record (one level only)
    child_type = draw(st.sampled_from(["null", "missing", "empty_object", "nested"]))
    if child_type == "null":
        child_json = "null"
        child_field = f'"child":{child_json}'
    elif child_type == "missing":
        child_field = None
    elif child_type == "empty_object":
        child_json = "{}"
        child_field = f'"child":{child_json}'
    else:
        # nested record: generate fields with some variations but no further recursion
        # For nested "child", "child" field is optional for Gson/Moshi/Jackson, but kotlinx rejects missing fields
        # We'll generate a minimal nested record with all fields present and valid types
        nested_id_int = draw(st.integers(min_value=0, max_value=10**6))
        nested_id_json = str(nested_id_int)
        nested_amount_json = json_string(draw(st.text(min_size=1, max_size=10)))
        nested_name_json = json_string(draw(st.one_of(st.none(), st.text(max_size=10))) or "")
        nested_status_json = json_string(draw(st.sampled_from(STATUS_VALUES)))
        nested_tags_len = draw(st.integers(min_value=0, max_value=2))
        nested_tags_elements = [json_string(draw(st.text(max_size=5))) for _ in range(nested_tags_len)]
        nested_tags_json = "[" + ",".join(nested_tags_elements) + "]"
        # Nested child field: null (to avoid deep recursion)
        nested_child_json = "null"
        nested_child_field = f'"child":{nested_child_json}'

        nested_fields = [
            f'"id":{nested_id_json}',
            f'"amount":{nested_amount_json}',
            f'"name":{nested_name_json}',
            f'"status":{nested_status_json}',
            f'"tags":{nested_tags_json}',
            nested_child_field,
        ]
        nested_record_json = "{" + ",".join(nested_fields) + "}"
        child_field = f'"child":{nested_record_json}'

    # Compose root record fields
    fields = [
        f'"id":{id_json}',
        f'"amount":{amount_json}',
        f'"name":{name_json}',
        f'"status":{status_json}',
        f'"tags":{tags_json}',
    ]
    if child_field is not None:
        fields.append(child_field)

    # Optionally add an extra unknown field (Gson/Moshi accept, kotlinx/Jackson reject)
    add_extra_field = draw(st.booleans())
    if add_extra_field:
        extra_field_name = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"\\')))
        extra_field_value = json_string(draw(st.text(max_size=5)))
        fields.append(f'"{extra_field_name}":{extra_field_value}')

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")