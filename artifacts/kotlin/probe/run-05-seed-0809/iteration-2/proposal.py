from hypothesis import strategies as st

# Constants for enum and tags element types
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
# We will produce tags elements as strings or numbers or null to trigger coercion/rejection differences
# but mostly strings and numbers, null only rarely.
# Also, tags array length small to keep document size small.

# Helper: produce a JSON string literal from a Python string (escaping quotes and backslashes)
def json_string_literal(s: str) -> str:
    # minimal escaping for quotes and backslash
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    # We produce a JSON text representing the record schema with one-level recursion.
    # We vary one or two fields from well-formed baseline to trigger divergences.
    # We try to cover known divergence points from probes and hints.

    # Base well-formed values
    # id: int or string convertible to int (string decimal digits)
    id_int = draw(st.integers(min_value=0, max_value=1000))
    id_as_string = draw(st.booleans())
    if id_as_string:
        id_json = json_string_literal(str(id_int))
    else:
        id_json = str(id_int)

    # amount: string normally, but can be number (Gson, Moshi, Jackson accept; kotlinx rejects)
    # or string convertible to number
    # We pick one of:
    # - string decimal number (e.g. "123.45")
    # - number (e.g. 123.45)
    # - string non-number (e.g. "abc") (kotlin rejects)
    amount_type = draw(st.sampled_from(['string_number', 'number', 'string_non_number']))
    if amount_type == 'string_number':
        # string decimal number
        amount_val = draw(st.floats(min_value=0, max_value=10000, allow_infinity=False, allow_nan=False))
        amount_json = json_string_literal(f"{amount_val:.2f}")
    elif amount_type == 'number':
        amount_val = draw(st.floats(min_value=0, max_value=10000, allow_infinity=False, allow_nan=False))
        # JSON number literal
        # Use repr to avoid scientific notation if possible
        amount_json = repr(amount_val)
    else:
        # string non-number
        amount_val = draw(st.text(min_size=1, max_size=5).filter(lambda s: not s.replace('.', '', 1).isdigit()))
        amount_json = json_string_literal(amount_val)

    # name: string or null normally
    # Also test number (Gson, Moshi, Jackson accept coercion; kotlinx rejects)
    # or null (all accept except Moshi, kotlinx, Jackson reject null status but name null is allowed)
    # We pick one of: string, null, number
    name_type = draw(st.sampled_from(['string', 'null', 'number']))
    if name_type == 'string':
        name_val = draw(st.text(min_size=0, max_size=10))
        name_json = json_string_literal(name_val)
    elif name_type == 'null':
        name_json = 'null'
    else:
        # number
        name_num = draw(st.integers(min_value=0, max_value=1000))
        name_json = str(name_num)

    # status: enum string "active", "inactive", "unknown"
    # or invalid enum string (Moshi, kotlinx, Jackson reject; Gson accepts with null)
    # or null (Gson accepts with null; others reject)
    status_type = draw(st.sampled_from(['valid_enum', 'invalid_enum', 'null']))
    if status_type == 'valid_enum':
        status_json = draw(st.sampled_from(STATUS_VALUES))
    elif status_type == 'invalid_enum':
        # invalid enum string, e.g. "pending"
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']))
        status_json = json_string_literal(invalid_status)
    else:
        status_json = 'null'

    # tags: array of strings normally
    # Known divergences:
    # - tags as string (all reject)
    # - tags as array with numeric elements (Gson, Moshi, Jackson accept coercion; kotlinx rejects)
    # - tags as array with null elements (Gson, Moshi, Jackson accept; kotlinx rejects)
    # - tags as array with mixed types (Gson, Moshi, Jackson accept; kotlinx rejects)
    # We pick one of:
    # - well-formed array of strings
    # - array with numbers
    # - array with nulls
    # - array mixed strings, numbers, nulls
    # - tags as string (invalid)
    tags_type = draw(st.sampled_from(['array_strings', 'array_numbers', 'array_nulls', 'array_mixed', 'string']))

    if tags_type == 'string':
        # invalid: tags as string
        tags_json = json_string_literal(draw(st.text(min_size=1, max_size=10)))
    else:
        # array
        # length 0..3 to keep small
        tags_len = draw(st.integers(min_value=0, max_value=3))
        tags_elements = []
        for _ in range(tags_len):
            if tags_type == 'array_strings':
                s = draw(st.text(min_size=1, max_size=5))
                tags_elements.append(json_string_literal(s))
            elif tags_type == 'array_numbers':
                n = draw(st.integers(min_value=0, max_value=1000))
                tags_elements.append(str(n))
            elif tags_type == 'array_nulls':
                tags_elements.append('null')
            else:  # array_mixed
                elem_type = draw(st.sampled_from(['string', 'number', 'null']))
                if elem_type == 'string':
                    s = draw(st.text(min_size=1, max_size=5))
                    tags_elements.append(json_string_literal(s))
                elif elem_type == 'number':
                    n = draw(st.integers(min_value=0, max_value=1000))
                    tags_elements.append(str(n))
                else:
                    tags_elements.append('null')
        tags_json = '[' + ','.join(tags_elements) + ']'

    # child: null or nested record (one level only)
    # Known divergences:
    # - child null accepted by all
    # - child empty object {} accepted by Gson only
    # - child missing fields rejected by all except Gson
    # We pick one of:
    # - null
    # - empty object {}
    # - well-formed nested record with same rules but no recursion (child.child=null always)
    child_type = draw(st.sampled_from(['null', 'empty_object', 'nested']))

    if child_type == 'null':
        child_json = 'null'
    elif child_type == 'empty_object':
        child_json = '{}'
    else:
        # nested record, no recursion (child.child=null)
        # For nested record, to keep complexity low, use well-formed values mostly,
        # but vary id as int or string, amount as string number or number,
        # name as string or null,
        # status as valid enum,
        # tags as array of strings,
        # child=null
        nid_int = draw(st.integers(min_value=0, max_value=1000))
        nid_as_string = draw(st.booleans())
        if nid_as_string:
            nid_json = json_string_literal(str(nid_int))
        else:
            nid_json = str(nid_int)

        namount_val = draw(st.floats(min_value=0, max_value=10000, allow_infinity=False, allow_nan=False))
        namount_type = draw(st.sampled_from(['string_number', 'number']))
        if namount_type == 'string_number':
            namount_json = json_string_literal(f"{namount_val:.2f}")
        else:
            namount_json = repr(namount_val)

        nname_type = draw(st.sampled_from(['string', 'null']))
        if nname_type == 'string':
            nname_val = draw(st.text(min_size=0, max_size=10))
            nname_json = json_string_literal(nname_val)
        else:
            nname_json = 'null'

        nstatus_json = draw(st.sampled_from(STATUS_VALUES))

        # tags array strings, length 0..2
        ntags_len = draw(st.integers(min_value=0, max_value=2))
        ntags_elements = [json_string_literal(draw(st.text(min_size=1, max_size=5))) for _ in range(ntags_len)]
        ntags_json = '[' + ','.join(ntags_elements) + ']'

        # child null
        nchild_json = 'null'

        child_json = (
            '{'
            + '"id":' + nid_json + ','
            + '"amount":' + namount_json + ','
            + '"name":' + nname_json + ','
            + '"status":' + nstatus_json + ','
            + '"tags":' + ntags_json + ','
            + '"child":' + nchild_json +
            '}'
        )

    # Compose full JSON object
    # Fields order fixed for consistency
    json_text = (
        '{'
        + '"id":' + id_json + ','
        + '"amount":' + amount_json + ','
        + '"name":' + name_json + ','
        + '"status":' + status_json + ','
        + '"tags":' + tags_json + ','
        + '"child":' + child_json
        + '}'
    )

    return json_text.encode('utf-8')