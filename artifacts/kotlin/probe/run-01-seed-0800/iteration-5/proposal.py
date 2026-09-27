from hypothesis import strategies as st

# Constants for enum values and field names
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
STATUS_INVALIDS = ['"invalid"', 'null', '123', 'true', 'false', '""']
# We include null as string "null" here to test Gson acceptance of null enum.

# Helper to produce JSON string literal from Python string (escape quotes and backslashes)
def json_string_literal(s: str) -> str:
    # Minimal escaping for JSON string literal
    # Replace \ with \\, " with \"
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON documents as bytes, aiming to produce behavioral divergence
    between Gson, Moshi, kotlinx.serialization, and Jackson Kotlin module.
    """

    # Strategy for "id": accept string or number (int)
    # Known: all accept numeric fields as string or number
    id_as_number = draw(st.booleans())
    if id_as_number:
        id_val = draw(st.integers(min_value=0, max_value=10**9))
        id_json = str(id_val)
    else:
        # string numeric
        id_val = draw(st.integers(min_value=0, max_value=10**9))
        id_json = json_string_literal(str(id_val))

    # Strategy for "amount": string normally, but sometimes number to trigger divergence
    # Known: Gson, Moshi, Jackson accept number for amount; kotlinx rejects
    amount_as_number = draw(st.booleans())
    if amount_as_number:
        # amount as number (integer or float)
        # Use integer or float string convertible to string
        amount_num = draw(st.one_of(st.integers(min_value=0, max_value=10**6), st.floats(min_value=0, max_value=10**6, allow_nan=False, allow_infinity=False)))
        if isinstance(amount_num, float):
            # Format float with minimal decimals
            amount_json = repr(amount_num)
        else:
            amount_json = str(amount_num)
    else:
        # amount as string (normal)
        amount_str = draw(st.text(min_size=1, max_size=10))
        amount_json = json_string_literal(amount_str)

    # Strategy for "name": string or null normally, but sometimes non-string (number or bool) to trigger divergence
    # Known: Gson, Moshi, Jackson accept non-string converting to string; kotlinx rejects
    name_type = draw(st.sampled_from(['string', 'null', 'number', 'bool']))
    if name_type == 'string':
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        if name_val is None:
            name_json = 'null'
        else:
            name_json = json_string_literal(name_val)
    elif name_type == 'null':
        name_json = 'null'
    elif name_type == 'number':
        # number as int or float
        n = draw(st.one_of(st.integers(min_value=-1000, max_value=1000), st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
        if isinstance(n, float):
            name_json = repr(n)
        else:
            name_json = str(n)
    else:  # bool
        b = draw(st.booleans())
        name_json = 'true' if b else 'false'

    # Strategy for "status": mostly valid enum, sometimes invalid or null to trigger divergence
    # Known: Gson accepts invalid enum as null; others reject invalid or null
    status_choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
    if status_choice == 'valid':
        status_json = draw(st.sampled_from(STATUS_VALUES))
    elif status_choice == 'invalid':
        status_json = draw(st.sampled_from(STATUS_INVALIDS))
    else:  # null
        status_json = 'null'

    # Strategy for "tags": always array, but element types vary
    # Known: all reject non-array tags
    # Gson, Moshi, Jackson accept non-string elements by converting to string; kotlinx rejects
    # So produce array with elements either all strings or mixed types
    tags_array_type = draw(st.sampled_from(['all_strings', 'mixed_types']))
    if tags_array_type == 'all_strings':
        tags_len = draw(st.integers(min_value=0, max_value=5))
        tags_elements = []
        for _ in range(tags_len):
            s = draw(st.text(min_size=0, max_size=10))
            tags_elements.append(json_string_literal(s))
    else:
        # mixed types: string, number, bool, null
        tags_len = draw(st.integers(min_value=1, max_value=5))
        tags_elements = []
        for _ in range(tags_len):
            t = draw(st.sampled_from(['string', 'number', 'bool', 'null']))
            if t == 'string':
                s = draw(st.text(min_size=0, max_size=10))
                tags_elements.append(json_string_literal(s))
            elif t == 'number':
                n = draw(st.one_of(st.integers(min_value=-1000, max_value=1000), st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
                if isinstance(n, float):
                    tags_elements.append(repr(n))
                else:
                    tags_elements.append(str(n))
            elif t == 'bool':
                b = draw(st.booleans())
                tags_elements.append('true' if b else 'false')
            else:
                tags_elements.append('null')
    tags_json = '[' + ','.join(tags_elements) + ']'

    # Strategy for "child": null, missing, empty object, or nested record with one level recursion
    # Known:
    # - Gson accepts empty object for child, filling missing fields with defaults/nulls; others reject
    # - Gson and Moshi accept missing optional child in nested records; kotlinx rejects missing fields; Jackson accepts missing child
    # - All accept nested child with correct fields
    # We produce either null, missing, empty object, or nested record with one level child=null or missing
    child_type = draw(st.sampled_from(['null', 'missing', 'empty_object', 'nested']))
    if child_type == 'null':
        child_json = 'null'
        include_child = True
    elif child_type == 'missing':
        include_child = False
        child_json = None
    elif child_type == 'empty_object':
        child_json = '{}'
        include_child = True
    else:
        # nested child record, with fields similar to root but no further recursion (child=null or missing)
        # Compose nested child fields with minimal variation to trigger divergence
        # For nested child, "child" field can be null or missing (Gson/Moshi accept missing, kotlinx rejects, Jackson accepts)
        nested_child_child_type = draw(st.sampled_from(['null', 'missing']))
        # id for nested child: string or number
        nested_id_as_number = draw(st.booleans())
        if nested_id_as_number:
            nested_id_val = draw(st.integers(min_value=0, max_value=10**9))
            nested_id_json = str(nested_id_val)
        else:
            nested_id_val = draw(st.integers(min_value=0, max_value=10**9))
            nested_id_json = json_string_literal(str(nested_id_val))
        # amount: string only (to keep nested simple)
        nested_amount_str = draw(st.text(min_size=1, max_size=10))
        nested_amount_json = json_string_literal(nested_amount_str)
        # name: string or null only (to keep nested simple)
        nested_name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        if nested_name_val is None:
            nested_name_json = 'null'
        else:
            nested_name_json = json_string_literal(nested_name_val)
        # status: valid enum only (to keep nested simple)
        nested_status_json = draw(st.sampled_from(STATUS_VALUES))
        # tags: array of strings only (to keep nested simple)
        nested_tags_len = draw(st.integers(min_value=0, max_value=3))
        nested_tags_elements = [json_string_literal(draw(st.text(min_size=0, max_size=10))) for _ in range(nested_tags_len)]
        nested_tags_json = '[' + ','.join(nested_tags_elements) + ']'

        # Compose nested child JSON fields
        nested_fields = [
            '"id":' + nested_id_json,
            '"amount":' + nested_amount_json,
            '"name":' + nested_name_json,
            '"status":' + nested_status_json,
            '"tags":' + nested_tags_json,
        ]
        if nested_child_child_type == 'null':
            nested_fields.append('"child":null')
        else:
            # missing child field
            pass

        child_json = '{' + ','.join(nested_fields) + '}'
        include_child = True

    # Compose root JSON fields
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
    ]
    if include_child:
        fields.append('"child":' + child_json)

    # Occasionally add extra unknown fields to root to trigger divergence (Gson and Moshi accept, kotlinx and Jackson reject)
    add_extra_field = draw(st.booleans())
    if add_extra_field:
        # Add one extra unknown field with string value
        extra_field_name = draw(st.text(min_size=1, max_size=10))
        extra_field_value = draw(st.text(min_size=0, max_size=10))
        extra_field_json = json_string_literal(extra_field_name) + ':' + json_string_literal(extra_field_value)
        fields.append(extra_field_json)

    # Shuffle fields to vary order (helps fuzzing)
    fields = draw(st.permutations(fields))

    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')