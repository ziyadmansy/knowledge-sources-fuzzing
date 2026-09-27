from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ['active', 'inactive', 'unknown']

    # id: either int (manual only accepts int, others accept integral float)
    # We produce either int or integral float (e.g. 1 or 1.0) to cause divergence.
    # Also try some floats with fractional part to cause rejection by all.
    id_type = draw(st.sampled_from(['int', 'integral_float', 'float_fractional']))
    if id_type == 'int':
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_str = str(id_val)
    elif id_type == 'integral_float':
        # integral float like 1.0, 42.0
        int_part = draw(st.integers(min_value=0, max_value=1000))
        id_str = f"{int_part}.0"
    else:
        # float with fractional part, e.g. 1.5, likely rejected by all
        float_val = draw(st.floats(min_value=0.1, max_value=1000, allow_infinity=False, allow_nan=False))
        # Format with decimal point, no exponent
        id_str = f"{float_val:.6f}".rstrip('0').rstrip('.')
        if '.' not in id_str:
            id_str += '.1'  # ensure fractional part

    # amount: must be string exactly, no coercion
    # To cause divergence, produce string or number (number rejected by all)
    amount_type = draw(st.sampled_from(['string', 'number']))
    if amount_type == 'string':
        # Non-empty ascii string, no quotes or control chars
        amount_val = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
        amount_str = '"' + amount_val + '"'
    else:
        # number (float or int) as JSON number, rejected by all
        amount_num = draw(st.one_of(st.integers(min_value=0, max_value=1000), st.floats(min_value=0.1, max_value=1000, allow_infinity=False, allow_nan=False)))
        if isinstance(amount_num, int):
            amount_str = str(amount_num)
        else:
            amount_str = f"{amount_num:.6f}".rstrip('0').rstrip('.')
            if '.' not in amount_str:
                amount_str += '.1'

    # name: string or null or missing (missing treated as null by all)
    # built_value omits null on serialization but accepts null if present
    # To cause divergence, sometimes omit name, sometimes null, sometimes string
    name_choice = draw(st.sampled_from(['string', 'null', 'missing']))
    if name_choice == 'string':
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\'))))
        # name_val can be null or string, but manual and others accept null, built_value omits null on serialization
        # To maximize divergence, produce string only here
        name_val = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
        name_str = '"' + name_val + '"'
        name_field = f'"name":{name_str}'
    elif name_choice == 'null':
        name_field = '"name":null'
    else:
        # missing name field
        name_field = None

    # status: one of enum strings, or unknown string to cause error
    # Manual throws raw ArgumentError on unknown strings
    # json_serializable/freezed throw CheckedFromJsonException
    # built_value throws ArgumentError wrapped in BuiltValueNestedFieldError if nested
    # To cause divergence, produce either valid enum or invalid string
    status_choice = draw(st.sampled_from(['valid', 'invalid']))
    if status_choice == 'valid':
        status_val = draw(st.sampled_from(STATUS_VALUES))
    else:
        # invalid string: different casing or unknown string
        invalid_status_candidates = ['Active', 'INACTIVE', 'unknowns', 'invalid', '']
        status_val = draw(st.sampled_from(invalid_status_candidates))
    status_field = f'"status":"{status_val}"'

    # tags: array of strings, non-null, non-empty elements
    # all reject missing or null tags
    # To cause divergence, produce array with one non-string element or empty string element or valid strings
    tags_type = draw(st.sampled_from(['valid_strings', 'non_string_element', 'empty_string_element']))
    if tags_type == 'valid_strings':
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')), min_size=1, max_size=5))
        tags_json = '[' + ','.join('"' + t + '"' for t in tags_list) + ']'
    elif tags_type == 'non_string_element':
        # Insert one integer element among strings to cause rejection by all
        n = draw(st.integers(min_value=1, max_value=4))
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')), min_size=n, max_size=n))
        # Insert integer 42 at random position
        pos = draw(st.integers(min_value=0, max_value=n))
        parts = []
        for i in range(n+1):
            if i == pos:
                parts.append('42')
            elif i < n:
                parts.append('"' + tags_list[i] + '"')
        tags_json = '[' + ','.join(parts) + ']'
    else:
        # empty string element among strings
        n = draw(st.integers(min_value=1, max_value=5))
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')), min_size=n-1, max_size=n-1))
        pos = draw(st.integers(min_value=0, max_value=n-1))
        parts = []
        for i in range(n):
            if i == pos:
                parts.append('""')
            else:
                idx = i if i < pos else i - 1
                parts.append('"' + tags_list[idx] + '"')
        tags_json = '[' + ','.join(parts) + ']'

    tags_field = f'"tags":{tags_json}'

    # child: null or nested object or invalid type (e.g. string)
    # built_value requires null or valid BvRecord
    # all reject if child present but not object or null
    # To cause divergence, produce child null, valid nested, or invalid type (string)
    child_type = draw(st.sampled_from(['null', 'valid', 'invalid_type']))
    if child_type == 'null':
        child_field = '"child":null'
    elif child_type == 'valid':
        # nested record with no further recursion (one level only)
        # To avoid complexity, nested record with valid minimal fields
        # id: int or integral float (try both)
        nested_id_type = draw(st.sampled_from(['int', 'integral_float']))
        if nested_id_type == 'int':
            nested_id_val = draw(st.integers(min_value=0, max_value=1000))
            nested_id_str = str(nested_id_val)
        else:
            nested_int_part = draw(st.integers(min_value=0, max_value=1000))
            nested_id_str = f"{nested_int_part}.0"
        # amount: string
        nested_amount_val = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
        nested_amount_str = '"' + nested_amount_val + '"'
        # name: null
        nested_name_field = '"name":null'
        # status: valid enum
        nested_status_val = draw(st.sampled_from(STATUS_VALUES))
        nested_status_field = f'"status":"{nested_status_val}"'
        # tags: valid strings array
        nested_tags_list = draw(st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')), min_size=1, max_size=3))
        nested_tags_json = '[' + ','.join('"' + t + '"' for t in nested_tags_list) + ']'
        nested_tags_field = f'"tags":{nested_tags_json}'
        # child: null (no further recursion)
        nested_child_field = '"child":null'

        nested_fields = [
            f'"id":{nested_id_str}',
            f'"amount":{nested_amount_str}',
            nested_name_field,
            nested_status_field,
            nested_tags_field,
            nested_child_field,
        ]
        nested_obj = '{' + ','.join(nested_fields) + '}'
        child_field = f'"child":{nested_obj}'
    else:
        # invalid type: string instead of object or null
        invalid_child_val = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
        child_field = f'"child":"{invalid_child_val}"'

    # Compose top-level fields
    fields = [f'"id":{id_str}', f'"amount":{amount_str}']
    if name_field is not None:
        fields.append(name_field)
    fields.append(status_field)
    fields.append(tags_field)
    fields.append(child_field)

    json_obj = '{' + ','.join(fields) + '}'

    return json_obj.encode('utf-8')