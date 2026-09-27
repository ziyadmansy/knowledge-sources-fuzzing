from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_ENUMS = ['"active"', '"inactive"', '"unknown"']
    # Also allow some invalid enum values to trigger divergence
    INVALID_ENUMS = ['"invalid"', '"ACTIVE"', '"in-active"', '123', 'null']

    # Helper: produce a JSON string literal from an ASCII string (no escaping)
    def json_string(s: str) -> str:
        # For simplicity, assume s has no special chars needing escaping
        return '"' + s + '"'

    # Helper: produce JSON text for "id" field: integer or stringified integer
    def gen_id():
        # id can be integer or string of integer
        as_int = draw(st.integers(min_value=0, max_value=10**6))
        as_str = json_string(str(as_int))
        # Pick int or string
        return draw(st.sampled_from([str(as_int), as_str]))

    # Helper: produce JSON text for "amount" field: string or number
    def gen_amount():
        # amount is string normally, but Gson/Moshi/Jackson accept number (converted to string)
        # kotlinx rejects number
        # So generate either string or number (int or float)
        # To maximize divergence, sometimes produce number, sometimes string
        # Also allow empty string or numeric string
        as_str = draw(st.one_of(
            st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),  # ASCII printable
            st.just(""),
            st.just("0"),
            st.just("123.45"),
            st.just("-0.99"),
        ))
        as_str_json = json_string(as_str)
        as_num = draw(st.one_of(
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False).map(lambda f: format(f, '.2f')),
        ))
        return draw(st.sampled_from([as_str_json, as_num]))

    # Helper: produce JSON text for "name" field: string, null, or number (number triggers divergence)
    def gen_name():
        # name can be string or null
        # Gson and Moshi accept number as string; kotlinx rejects number; Jackson accepts number as string
        # So generate string, null, or number
        choice = draw(st.sampled_from(['string', 'null', 'number']))
        if choice == 'string':
            s = draw(st.one_of(
                st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
                st.just(""),
            ))
            return json_string(s)
        elif choice == 'null':
            return 'null'
        else:
            # number as int or float
            n = draw(st.one_of(
                st.integers(min_value=-1000, max_value=1000).map(str),
                st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False).map(lambda f: format(f, '.2f')),
            ))
            return n

    # Helper: produce JSON text for "status" field: valid enum, invalid enum, or null
    def gen_status():
        # Gson accepts unknown enum as null; others reject
        # Gson accepts null; others reject null for non-nullable enum
        choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
        if choice == 'valid':
            return draw(st.sampled_from(STATUS_ENUMS))
        elif choice == 'invalid':
            return draw(st.sampled_from(INVALID_ENUMS))
        else:
            return 'null'

    # Helper: produce JSON text for "tags" field: array of strings normally
    # Gson, Moshi, Jackson accept non-string elements converting to strings; kotlinx rejects
    # Also reject non-array (all reject non-array)
    def gen_tags():
        # Decide if array or not (mostly array, sometimes non-array to trigger rejection)
        is_array = draw(st.booleans())
        if not is_array:
            # Non-array: produce a number or string or null or object (all reject)
            return draw(st.sampled_from(['null', '123', 'true', 'false', '{}', '""']))
        else:
            # Array: produce array of elements, elements can be string or number or null
            # To trigger divergence, sometimes include non-string elements
            length = draw(st.integers(min_value=0, max_value=5))
            elems = []
            for _ in range(length):
                elem_type = draw(st.sampled_from(['string', 'number', 'null']))
                if elem_type == 'string':
                    s = draw(st.one_of(
                        st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
                        st.just(""),
                    ))
                    elems.append(json_string(s))
                elif elem_type == 'number':
                    n = draw(st.one_of(
                        st.integers(min_value=-1000, max_value=1000).map(str),
                        st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False).map(lambda f: format(f, '.2f')),
                    ))
                    elems.append(n)
                else:
                    elems.append('null')
            return '[' + ','.join(elems) + ']'

    # Helper: produce JSON text for "child" field: null or nested record (one level recursion)
    # Recursion bounded to one level only
    def gen_child(level=0):
        # child can be null or record
        choice = draw(st.sampled_from(['null', 'record']))
        if choice == 'null':
            return 'null'
        else:
            # nested record with same rules, but no further recursion (level=1 max)
            # To avoid infinite recursion, only allow null child at level 1
            # Build nested record fields similarly but with level=1
            id_field = gen_id()
            amount_field = gen_amount()
            name_field = gen_name()
            status_field = gen_status()
            tags_field = gen_tags()
            # child at level 1 must be null to avoid deeper recursion
            child_field = 'null'
            # Compose JSON object text
            fields = [
                '"id":' + id_field,
                '"amount":' + amount_field,
                '"name":' + name_field,
                '"status":' + status_field,
                '"tags":' + tags_field,
                '"child":' + child_field,
            ]
            # To trigger divergence on unknown fields, sometimes add unknown field for child record
            add_unknown = draw(st.booleans())
            if add_unknown:
                # Gson and Moshi accept unknown fields; kotlinx and Jackson reject
                fields.append('"unknown_field_child":123')
            # Shuffle fields to test duplicate fields and ordering
            # Also sometimes duplicate a field to test last-wins
            fields = draw(st.lists(st.sampled_from(fields), min_size=len(fields), max_size=len(fields)+1))
            # Possibly duplicate a random field once
            if draw(st.booleans()):
                dup_field = draw(st.sampled_from(fields))
                fields.append(dup_field)
            # Shuffle fields
            fields = draw(st.permutations(fields))
            return '{' + ','.join(fields) + '}'

    # Compose top-level record fields
    id_field = gen_id()
    amount_field = gen_amount()
    name_field = gen_name()
    status_field = gen_status()
    tags_field = gen_tags()
    child_field = gen_child(level=0)

    # Compose fields list
    fields = [
        '"id":' + id_field,
        '"amount":' + amount_field,
        '"name":' + name_field,
        '"status":' + status_field,
        '"tags":' + tags_field,
        '"child":' + child_field,
    ]

    # Sometimes add unknown top-level field to trigger divergence on unknown fields
    add_unknown_top = draw(st.booleans())
    if add_unknown_top:
        fields.append('"unknown_top": "value"')

    # Sometimes duplicate a field to test last-wins
    if draw(st.booleans()):
        dup_field = draw(st.sampled_from(fields))
        fields.append(dup_field)

    # Shuffle fields to vary order
    fields = draw(st.permutations(fields))

    json_text = '{' + ','.join(fields) + '}'
    return json_text.encode('utf-8')