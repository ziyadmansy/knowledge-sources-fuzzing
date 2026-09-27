from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper: produce a JSON string literal with controlled escaping
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        # Also escape control chars to avoid breaking JSON
        s = s.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return '"' + s + '"'

    # Helper: produce a JSON array of strings
    def json_array_of_strings(lst):
        return '[' + ','.join(json_string(x) for x in lst) + ']'

    # Recursive generator for the "child" field, bounded depth
    def record_json(depth: int) -> st.SearchStrategy[str]:
        if depth <= 0:
            # At max depth, child is always null
            child_strat = st.just('null')
        else:
            # child is either null or another record (one level less)
            child_strat = st.one_of(st.just('null'), record_json(depth - 1))

        # id: integer, but we will sometimes produce wrong types or boundary values
        # amount: string, but sometimes wrong type or malformed string
        # name: string or null, sometimes wrong type or missing
        # status: one of three strings, sometimes wrong string or wrong type
        # tags: array of strings, sometimes empty, sometimes wrong type or malformed strings

        # id field: mostly integer as string, sometimes float or stringified int, sometimes string instead of int
        id_int = st.integers(min_value=0, max_value=2**31 - 1)
        # Introduce some type variation for id: int, stringified int, float, or string nonsense
        id_type = draw(st.sampled_from(['int', 'string_int', 'float', 'string_nonsense']))
        if id_type == 'int':
            id_val = str(draw(id_int))
        elif id_type == 'string_int':
            id_val = json_string(str(draw(id_int)))
        elif id_type == 'float':
            # float as number, e.g. 1.0 or 0.0
            id_val = str(float(draw(id_int)))
        else:
            # string nonsense
            id_val = json_string(draw(st.text(min_size=1, max_size=5)))

        # amount field: normally string representing decimal number, sometimes number, sometimes malformed string
        # We'll produce strings mostly, but sometimes number or wrong type
        amount_type = draw(st.sampled_from(['string_decimal', 'number', 'string_nonsense', 'null']))
        if amount_type == 'string_decimal':
            # decimal string, possibly with leading zeros or signs
            sign = draw(st.sampled_from(['', '-', '+']))
            int_part = draw(st.integers(min_value=0, max_value=9999))
            frac_part = draw(st.one_of(st.just(''), st.text(min_size=1, max_size=4, alphabet='0123456789')))
            if frac_part:
                amount_val = json_string(sign + str(int_part) + '.' + frac_part)
            else:
                amount_val = json_string(sign + str(int_part))
        elif amount_type == 'number':
            # number literal (int or float)
            amount_val = str(draw(st.floats(allow_nan=False, allow_infinity=False, width=32)))
        elif amount_type == 'string_nonsense':
            amount_val = json_string(draw(st.text(min_size=1, max_size=5)))
        else:
            amount_val = 'null'  # invalid per schema but test divergence

        # name field: string or null normally, sometimes missing or wrong type
        # We always include name field (per schema), but sometimes null, sometimes string, sometimes number or boolean
        name_type = draw(st.sampled_from(['string', 'null', 'number', 'boolean']))
        if name_type == 'string':
            # string with possible unicode or escapes
            name_val = json_string(draw(st.text(min_size=0, max_size=10)))
        elif name_type == 'null':
            name_val = 'null'
        elif name_type == 'number':
            name_val = str(draw(st.integers(min_value=-100, max_value=100)))
        else:
            name_val = draw(st.sampled_from(['true', 'false']))

        # status field: one of three strings normally, sometimes wrong string or wrong type
        status_type = draw(st.sampled_from(['valid', 'invalid_string', 'number', 'null']))
        if status_type == 'valid':
            status_val = draw(st.sampled_from(statuses))
        elif status_type == 'invalid_string':
            status_val = json_string(draw(st.text(min_size=1, max_size=7).filter(lambda x: x not in ['active','inactive','unknown'])))
        elif status_type == 'number':
            status_val = str(draw(st.integers(min_value=0, max_value=10)))
        else:
            status_val = 'null'

        # tags field: array of strings normally, sometimes empty array, sometimes array with non-string, sometimes null or number
        tags_type = draw(st.sampled_from(['valid', 'empty', 'non_string', 'null', 'number']))
        if tags_type == 'valid':
            tags_list = draw(st.lists(st.text(min_size=0, max_size=5), min_size=1, max_size=5))
            tags_val = json_array_of_strings(tags_list)
        elif tags_type == 'empty':
            tags_val = '[]'
        elif tags_type == 'non_string':
            # mix strings and numbers or booleans
            elems = []
            n = draw(st.integers(min_value=1, max_value=4))
            for _ in range(n):
                t = draw(st.sampled_from(['string', 'number', 'boolean']))
                if t == 'string':
                    elems.append(json_string(draw(st.text(min_size=0, max_size=5))))
                elif t == 'number':
                    elems.append(str(draw(st.integers(min_value=-10, max_value=10))))
                else:
                    elems.append(draw(st.sampled_from(['true', 'false'])))
            tags_val = '[' + ','.join(elems) + ']'
        elif tags_type == 'null':
            tags_val = 'null'
        else:
            tags_val = str(draw(st.floats(allow_nan=False, allow_infinity=False)))

        # child field: either null or nested record (one less depth)
        child_val = draw(child_strat)

        # Compose JSON object string with all fields in order
        # Always include all fields, no missing keys (per schema)
        json_obj = (
            '{'
            + '"id":' + id_val + ','
            + '"amount":' + amount_val + ','
            + '"name":' + name_val + ','
            + '"status":' + status_val + ','
            + '"tags":' + tags_val + ','
            + '"child":' + child_val
            + '}'
        )
        return json_obj

    # Draw top-level record with max depth 1 (one level recursion)
    json_text = draw(record_json(depth=1))
    return json_text.encode('utf-8')