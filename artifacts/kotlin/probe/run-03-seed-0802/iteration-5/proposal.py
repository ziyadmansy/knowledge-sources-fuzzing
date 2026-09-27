from hypothesis import strategies as st

# Constants for the "status" field
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce JSON string literal from Python string (escape quotes and backslashes)
def json_string_literal(s: str) -> str:
    # minimal escaping for " and \ to keep JSON valid
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text for the record schema with subtle variations to trigger
    divergences among Gson, Moshi, kotlinx.serialization, and Jackson Kotlin module.
    """

    # --- id field ---
    # id can be integer or string containing integer (all accept both)
    id_as_number = draw(st.booleans())
    id_value = draw(st.integers(min_value=0, max_value=10**9))
    if id_as_number:
        id_json = str(id_value)
    else:
        id_json = json_string_literal(str(id_value))

    # --- amount field ---
    # Known divergence: Gson, Moshi, Jackson accept string or number; kotlinx rejects number.
    # We'll sometimes produce number, sometimes string.
    amount_as_number = draw(st.booleans())
    # amount is string or number (number converted to string by some)
    # Use decimal numbers as string or number
    amount_number_value = draw(st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False))
    # Format floats to JSON number (no quotes)
    amount_number_json = (
        str(int(amount_number_value))
        if amount_number_value.is_integer()
        else ('%.6f' % amount_number_value).rstrip('0').rstrip('.')
    )
    if amount_as_number:
        amount_json = amount_number_json
    else:
        # string form, use decimal with 2 digits fixed for readability
        amount_json = json_string_literal('%.2f' % amount_number_value)

    # --- name field ---
    # Divergence: Gson, Moshi accept string or number (converted to string);
    # kotlinx rejects number; Jackson accepts number converted to string.
    # Also accept null.
    name_choice = draw(st.sampled_from(['string', 'number', 'null']))
    if name_choice == 'string':
        # random string or empty string
        name_str = draw(st.text(min_size=0, max_size=10))
        name_json = json_string_literal(name_str)
    elif name_choice == 'number':
        # number as int or float
        name_num = draw(st.one_of(st.integers(min_value=-1000, max_value=1000),
                                  st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
        if isinstance(name_num, int) or (isinstance(name_num, float) and name_num.is_integer()):
            name_json = str(int(name_num))
        else:
            name_json = ('%.6f' % name_num).rstrip('0').rstrip('.')
    else:
        # null
        name_json = 'null'

    # --- status field ---
    # Must be one of "active", "inactive", "unknown" or null.
    # Gson accepts unknown string as null; others reject unknown string.
    # Gson accepts null; others reject null.
    # We'll produce:
    # - valid known string
    # - unknown string (to trigger Gson accept as null, others reject)
    # - null (Gson accepts, others reject)
    status_variant = draw(st.sampled_from(['valid', 'unknown_string', 'null']))
    if status_variant == 'valid':
        status_json = draw(st.sampled_from(STATUS_VALUES))
    elif status_variant == 'unknown_string':
        # produce a string not in allowed set
        # use a fixed unknown string to maximize reproducibility
        status_json = json_string_literal("invalid_status")
    else:
        status_json = 'null'

    # --- tags field ---
    # Must be array.
    # All reject non-array.
    # Gson, Moshi, Jackson accept non-string elements by converting to string or allowing null.
    # kotlinx rejects non-string or null elements.
    # We'll produce arrays with elements that are:
    # - all strings (valid for all)
    # - some non-string elements (to cause divergence)
    # - empty array (valid)
    tags_array_type = draw(st.sampled_from(['all_strings', 'mixed_nonstring', 'empty']))
    if tags_array_type == 'empty':
        tags_json = '[]'
    else:
        # size 1..4
        tags_len = draw(st.integers(min_value=1, max_value=4))
        if tags_array_type == 'all_strings':
            tags_elements = [json_string_literal(draw(st.text(min_size=0, max_size=10))) for _ in range(tags_len)]
        else:
            # mixed_nonstring: some elements are strings, some are numbers or null
            tags_elements = []
            for _ in range(tags_len):
                elem_type = draw(st.sampled_from(['string', 'number', 'null']))
                if elem_type == 'string':
                    tags_elements.append(json_string_literal(draw(st.text(min_size=0, max_size=10))))
                elif elem_type == 'number':
                    num = draw(st.integers(min_value=-1000, max_value=1000))
                    tags_elements.append(str(num))
                else:
                    tags_elements.append('null')
        tags_json = '[' + ','.join(tags_elements) + ']'

    # --- child field ---
    # child is null or nested record (one level recursion).
    # Nested record follows same schema but recursion depth limited to 1.
    # Gson tolerates empty object {} as child; others reject missing required fields.
    # We'll produce:
    # - null
    # - valid nested record (all fields present, well-formed)
    # - empty object {}
    # - nested record with one field wrong type (to trigger divergence)
    child_variant = draw(st.sampled_from(['null', 'valid', 'empty_object', 'nested_wrong_type']))

    def gen_nested_record():
        # Nested record with all fields present and well-formed.
        # Use only well-formed values to avoid broad rejection.
        nested_id = draw(st.one_of(
            st.integers(min_value=0, max_value=10**9).map(str),
            st.integers(min_value=0, max_value=10**9).map(lambda x: json_string_literal(str(x)))
        ))
        nested_amount = draw(st.one_of(
            st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False).map(
                lambda f: str(int(f)) if f.is_integer() else ('%.6f' % f).rstrip('0').rstrip('.')),
            st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False).map(
                lambda f: json_string_literal('%.2f' % f))
        ))
        nested_name = draw(st.one_of(
            st.none().map(lambda _: 'null'),
            st.text(min_size=0, max_size=10).map(json_string_literal)
        ))
        nested_status = draw(st.sampled_from(STATUS_VALUES))
        nested_tags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3)).map(
            lambda lst: '[' + ','.join(json_string_literal(s) for s in lst) + ']'
        )
        # child of nested child is null (no further recursion)
        nested_child = 'null'

        nested_fields = [
            '"id":' + nested_id,
            '"amount":' + nested_amount,
            '"name":' + nested_name,
            '"status":' + nested_status,
            '"tags":' + nested_tags,
            '"child":' + nested_child
        ]
        return '{' + ','.join(nested_fields) + '}'

    if child_variant == 'null':
        child_json = 'null'
    elif child_variant == 'empty_object':
        child_json = '{}'
    elif child_variant == 'valid':
        child_json = gen_nested_record()
    else:
        # nested_wrong_type: produce nested record but with one field wrong type
        # Pick one field to have wrong type (e.g. amount as number instead of string, or tags as non-array)
        nested = draw(st.just(None))  # placeholder to use draw context
        # We'll build nested record fields manually with one wrong type field
        # Pick field to break: id, amount, name, status, tags, child
        wrong_field = draw(st.sampled_from(['id', 'amount', 'name', 'status', 'tags', 'child']))

        # Build fields normally first
        nested_id = draw(st.one_of(
            st.integers(min_value=0, max_value=10**9).map(str),
            st.integers(min_value=0, max_value=10**9).map(lambda x: json_string_literal(str(x)))
        ))
        nested_amount = draw(st.one_of(
            st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False).map(
                lambda f: json_string_literal('%.2f' % f)),
            st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False).map(
                lambda f: str(int(f)) if f.is_integer() else ('%.6f' % f).rstrip('0').rstrip('.'))
        ))
        nested_name = draw(st.one_of(
            st.none().map(lambda _: 'null'),
            st.text(min_size=0, max_size=10).map(json_string_literal)
        ))
        nested_status = draw(st.sampled_from(STATUS_VALUES))
        nested_tags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3)).map(
            lambda lst: '[' + ','.join(json_string_literal(s) for s in lst) + ']'
        )
        nested_child = 'null'

        # Now override one field with wrong type
        if wrong_field == 'id':
            # id as boolean (wrong type)
            nested_id = 'true'
        elif wrong_field == 'amount':
            # amount as boolean (wrong type)
            nested_amount = 'false'
        elif wrong_field == 'name':
            # name as boolean (wrong type)
            nested_name = 'true'
        elif wrong_field == 'status':
            # status as number (wrong type)
            nested_status = '123'
        elif wrong_field == 'tags':
            # tags as string (wrong type)
            nested_tags = json_string_literal("not_an_array")
        else:  # child
            # child as string (wrong type)
            nested_child = json_string_literal("not_null_or_object")

        nested_fields = [
            '"id":' + nested_id,
            '"amount":' + nested_amount,
            '"name":' + nested_name,
            '"status":' + nested_status,
            '"tags":' + nested_tags,
            '"child":' + nested_child
        ]
        child_json = '{' + ','.join(nested_fields) + '}'

    # --- Unknown extra fields ---
    # Gson and Moshi accept unknown extra fields; kotlinx and Jackson reject.
    # Add zero or one unknown extra field at top level or nested child (if object).
    # This can increase divergence.
    add_unknown_field = draw(st.booleans())
    unknown_field_name = '"extra_field"'
    unknown_field_value = json_string_literal("extra_value")

    # Compose base fields
    base_fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
        '"child":' + child_json
    ]

    # Insert unknown field either at top level or inside child if child is object
    if add_unknown_field:
        place_in_child = draw(st.booleans())
        if place_in_child and child_json.startswith('{') and child_json != '{}':
            # Insert unknown field inside child object (before closing })
            # child_json is {...}, insert before last }
            child_json_with_extra = child_json[:-1] + ',' + unknown_field_name + ':' + unknown_field_value + '}'
            # Replace child_json in base_fields
            base_fields = [
                f if not f.startswith('"child":') else '"child":' + child_json_with_extra
                for f in base_fields
            ]
        else:
            # Insert unknown field at top level
            base_fields.append(unknown_field_name + ':' + unknown_field_value)

    # Compose final JSON object
    json_text = '{' + ','.join(base_fields) + '}'

    return json_text.encode('utf-8')