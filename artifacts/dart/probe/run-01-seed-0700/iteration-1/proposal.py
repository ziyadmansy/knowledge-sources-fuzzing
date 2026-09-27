from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ["active", "inactive", "unknown"]
    # We will produce a single-level nested "child" or null

    # Helper: produce a JSON string literal with proper escaping for quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for JSON string: backslash and quote
        # Also escape control chars \b \f \n \r \t for safety
        esc = s.replace('\\', '\\\\').replace('"', '\\"')
        esc = esc.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return '"' + esc + '"'

    # Helper: produce a JSON array of strings
    def json_string_array(arr):
        return '[' + ','.join(json_string(e) for e in arr) + ']'

    # Produce a valid "id" integer or a borderline invalid variant (e.g. float that looks like int)
    # But per known probes, scalar type mismatches are always rejected consistently.
    # So we try to produce either a valid int or a stringified int (which is rejected consistently).
    # To induce divergence, try missing fields or null for non-nullable fields.
    # But "id" is always present and integer per schema.
    # Let's produce either int or a string containing digits (which is rejected consistently).
    # So for "id" we produce always int to keep baseline well-formedness.

    # To induce divergence, we try to vary "name" and "child" presence and nullability,
    # and "status" enum values including borderline invalid ones (e.g. "active " with trailing space),
    # or missing fields (though schema says all fields always present, but maybe some implementations accept missing fields?).
    # We try to produce missing fields or null for non-nullable fields to test divergence.

    # But from known probes, all reject type mismatches on scalar fields consistently.
    # So try to produce "status" with a valid enum or a close invalid enum (like "active " or "Active").
    # Known probes say invalid enum values cause ArgumentError or DeserializationError consistently.
    # So try to produce "status" as null or missing to test divergence.

    # Known probes do not mention missing fields at top level.
    # So try to produce missing "status" or "id" to see if any implementation accepts it.

    # For "tags" array of strings, try empty array, array with empty string, or array with null (which should be rejected consistently).
    # Try duplicate keys at top level for "tags" or "id" to test divergence (known probes only mention nested duplicates).
    # But JSON spec forbids duplicate keys at same level, but some parsers accept it.
    # We can try to produce duplicate keys at top level to test divergence.

    # We will produce a baseline well-formed document, then with small variations:
    # - "status" with valid or invalid enum or null or missing
    # - "name" with string, null, or missing
    # - "child" with valid nested record, null, or missing
    # - "tags" with array of strings, empty array, or array with empty string
    # - duplicate keys at top level for "tags" or "id" (to test if any implementation rejects or accepts differently)
    # - missing fields (though schema says always present, but maybe some implementations accept missing fields)

    # Strategy for "id": always int (to keep baseline well-formed)
    id_val = draw(st.integers(min_value=0, max_value=10**9))

    # Strategy for "amount": string representing a decimal number (always string)
    # Try valid decimal strings or borderline invalid strings (e.g. empty string, or string with spaces)
    amount_val = draw(st.one_of(
        st.decimals(min_value=0, max_value=10**9, places=2).map(lambda d: format(d, 'f')),
        st.just(""),  # empty string borderline
        st.just(" 123.45 "),  # string with spaces
    ))

    # Strategy for "name": string or null or missing (to test divergence)
    # Known probes say all accept null for nullable "name"
    # Try missing "name" to test divergence
    name_present = draw(st.booleans())
    if name_present:
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
    else:
        name_val = None  # will omit field

    # Strategy for "status": valid enum, invalid enum, null, or missing
    status_choice = draw(st.integers(min_value=0, max_value=4))
    if status_choice == 0:
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_present = True
    elif status_choice == 1:
        # invalid enum close to valid ones
        status_val = draw(st.sampled_from(["active ", "Inactive", "UNKNOWN", "enabled", ""]))
        status_present = True
    elif status_choice == 2:
        status_val = None
        status_present = True
    else:
        status_val = None
        status_present = False  # omit field

    # Strategy for "tags": array of strings, empty array, array with empty string, or missing
    tags_present = draw(st.booleans())
    if tags_present:
        tags_val = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=3))
    else:
        tags_val = None  # omit field

    # Strategy for "child": null, valid nested record, or missing
    child_present = draw(st.integers(min_value=0, max_value=2))
    if child_present == 0:
        child_val = None
        child_present_flag = True
    elif child_present == 1:
        # valid nested record, no recursion beyond one level
        # nested record fields must be well-formed or borderline malformed to test divergence
        # For nested "child", produce only well-formed or with one small variation
        nested_id = draw(st.integers(min_value=0, max_value=10**9))
        nested_amount = draw(st.decimals(min_value=0, max_value=10**9, places=2).map(lambda d: format(d, 'f')))
        nested_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        nested_status = draw(st.sampled_from(STATUS_VALUES))
        nested_tags = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=3))
        # nested child is always null (no recursion beyond one level)
        nested_child = None

        # Build nested JSON string for child
        nested_fields = []
        nested_fields.append('"id":' + str(nested_id))
        nested_fields.append('"amount":' + json_string(format(nested_amount, 'f')))
        if nested_name is None:
            nested_fields.append('"name":null')
        else:
            nested_fields.append('"name":' + json_string(nested_name))
        nested_fields.append('"status":' + json_string(nested_status))
        nested_fields.append('"tags":' + json_string_array(nested_tags))
        nested_fields.append('"child":null')
        child_val = '{' + ','.join(nested_fields) + '}'
        child_present_flag = True
    else:
        child_val = None
        child_present_flag = False  # omit field

    # Compose top-level fields as strings
    fields = []

    # id always present
    fields.append('"id":' + str(id_val))

    # amount always present
    # amount_val is string, but may be empty or with spaces
    fields.append('"amount":' + json_string(amount_val))

    # name present or omitted
    if name_present:
        if name_val is None:
            fields.append('"name":null')
        else:
            fields.append('"name":' + json_string(name_val))

    # status present or omitted
    if status_present:
        if status_val is None:
            fields.append('"status":null')
        else:
            fields.append('"status":' + json_string(status_val))

    # tags present or omitted
    if tags_present:
        fields.append('"tags":' + json_string_array(tags_val))

    # child present or omitted
    if child_present_flag:
        if child_val is None:
            fields.append('"child":null')
        else:
            fields.append('"child":' + child_val)

    # To test duplicate keys at top level, randomly add a duplicate key for "tags" or "id"
    duplicate_key_choice = draw(st.integers(min_value=0, max_value=3))
    if duplicate_key_choice == 0 and tags_present:
        # duplicate "tags" key with different array (empty or non-empty)
        dup_tags_val = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=2))
        fields.append('"tags":' + json_string_array(dup_tags_val))
    elif duplicate_key_choice == 1:
        # duplicate "id" key with same or different int
        dup_id_val = draw(st.integers(min_value=0, max_value=10**9))
        fields.append('"id":' + str(dup_id_val))
    # else no duplicate keys

    # Shuffle fields to vary order
    from random import shuffle
    shuffle(fields)

    json_text = '{' + ','.join(fields) + '}'
    return json_text.encode('utf-8')