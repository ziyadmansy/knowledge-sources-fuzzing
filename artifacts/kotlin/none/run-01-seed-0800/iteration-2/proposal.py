from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for the schema
    STATUS_VALUES = ['active', 'inactive', 'unknown']

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Escape backslash and double quote for JSON string
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        # Also escape control characters minimally (newline, tab)
        s = s.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return '"' + s + '"'

    # Recursive generator for the "child" field, max depth 1 (child.child always null)
    # To keep the recursion bounded, pass depth parameter
    def record_json(draw, depth=0) -> str:
        # id: integer, but to induce divergence, sometimes produce integer as string or float as string or missing
        # amount: string, but sometimes number or null or missing
        # name: string or null, sometimes missing or wrong type
        # status: one of three strings, sometimes wrong string, missing, or null
        # tags: array of strings, sometimes empty, sometimes with wrong types, sometimes missing
        # child: record or null, sometimes missing or wrong type

        # To maximize divergence, we vary one or two fields at a time, mostly well-formed but with subtle errors.

        # Strategy for id field:
        # Mostly integer as number, sometimes integer as string, sometimes float as number, sometimes string float, sometimes missing
        id_type = draw(st.sampled_from(['int', 'int_str', 'float', 'float_str', 'missing']))
        if id_type == 'int':
            id_val = str(draw(st.integers(min_value=0, max_value=10**9)))
            id_json = id_val
        elif id_type == 'int_str':
            id_val = draw(st.integers(min_value=0, max_value=10**9))
            id_json = json_string_literal(str(id_val))
        elif id_type == 'float':
            # float close to int, e.g. 123.0 or 123.45
            f = draw(st.floats(min_value=0, max_value=10**9, allow_nan=False, allow_infinity=False))
            id_json = repr(f)
        elif id_type == 'float_str':
            f = draw(st.floats(min_value=0, max_value=10**9, allow_nan=False, allow_infinity=False))
            id_json = json_string_literal(str(f))
        else:  # missing
            id_json = None

        # amount: string normally, sometimes number, sometimes null, sometimes missing
        amount_type = draw(st.sampled_from(['string', 'number', 'null', 'missing']))
        if amount_type == 'string':
            # string that looks like a number or arbitrary string
            amount_val = draw(st.one_of(
                st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
                st.from_regex(r'-?\d+(\.\d+)?', fullmatch=True)
            ))
            amount_json = json_string_literal(amount_val)
        elif amount_type == 'number':
            # number as JSON number
            amount_val = draw(st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
            amount_json = repr(amount_val)
        elif amount_type == 'null':
            amount_json = 'null'
        else:
            amount_json = None

        # name: string or null normally, sometimes number, sometimes missing
        name_type = draw(st.sampled_from(['string', 'null', 'number', 'missing']))
        if name_type == 'string':
            name_val = draw(st.one_of(
                st.none().map(lambda _: None),  # to allow null as well, but we handle null separately
                st.text(min_size=0, max_size=20).filter(lambda s: '"' not in s and '\\' not in s)
            ))
            if name_val is None:
                name_json = 'null'
            else:
                name_json = json_string_literal(name_val)
        elif name_type == 'null':
            name_json = 'null'
        elif name_type == 'number':
            name_val = draw(st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
            name_json = repr(name_val)
        else:
            name_json = None

        # status: one of "active", "inactive", "unknown" normally,
        # sometimes wrong string, sometimes null, sometimes missing
        status_type = draw(st.sampled_from(['valid', 'invalid_string', 'null', 'missing']))
        if status_type == 'valid':
            status_val = draw(st.sampled_from(STATUS_VALUES))
            status_json = json_string_literal(status_val)
        elif status_type == 'invalid_string':
            # string not in allowed set
            invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES and '"' not in s and '\\' not in s))
            status_json = json_string_literal(invalid_status)
        elif status_type == 'null':
            status_json = 'null'
        else:
            status_json = None

        # tags: array of strings normally, sometimes empty array, sometimes array with non-string, sometimes null, sometimes missing
        tags_type = draw(st.sampled_from(['valid', 'empty', 'non_string', 'null', 'missing']))
        if tags_type == 'valid':
            # array of 1-5 strings
            tags_list = draw(st.lists(st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s), min_size=1, max_size=5))
            tags_json = '[' + ','.join(json_string_literal(t) for t in tags_list) + ']'
        elif tags_type == 'empty':
            tags_json = '[]'
        elif tags_type == 'non_string':
            # array with at least one non-string element (int or null)
            n = draw(st.integers(min_value=1, max_value=5))
            elems = []
            for _ in range(n):
                elem_type = draw(st.sampled_from(['string', 'int', 'null']))
                if elem_type == 'string':
                    s = draw(st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
                    elems.append(json_string_literal(s))
                elif elem_type == 'int':
                    i = draw(st.integers(min_value=0, max_value=1000))
                    elems.append(str(i))
                else:
                    elems.append('null')
            tags_json = '[' + ','.join(elems) + ']'
        elif tags_type == 'null':
            tags_json = 'null'
        else:
            tags_json = None

        # child: record or null normally, sometimes missing, sometimes wrong type (string or number)
        child_type = draw(st.sampled_from(['record', 'null', 'missing', 'string', 'number']))
        if depth >= 1:
            # At depth 1, child must be null or missing (no further recursion)
            child_type = draw(st.sampled_from(['null', 'missing']))

        if child_type == 'record':
            child_json = record_json(draw, depth=depth+1)
        elif child_type == 'null':
            child_json = 'null'
        elif child_type == 'missing':
            child_json = None
        elif child_type == 'string':
            s = draw(st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
            child_json = json_string_literal(s)
        else:  # number
            n = draw(st.integers(min_value=0, max_value=1000))
            child_json = str(n)

        # Compose fields, skipping those that are None (missing)
        fields = []
        if id_json is not None:
            fields.append('"id":' + id_json)
        if amount_json is not None:
            fields.append('"amount":' + amount_json)
        if name_json is not None:
            fields.append('"name":' + name_json)
        if status_json is not None:
            fields.append('"status":' + status_json)
        if tags_json is not None:
            fields.append('"tags":' + tags_json)
        if child_json is not None:
            fields.append('"child":' + child_json)

        json_obj = '{' + ','.join(fields) + '}'
        return json_obj

    # Draw the top-level record JSON string
    json_text = record_json(draw, depth=0)
    # Return as bytes (UTF-8)
    return json_text.encode('utf-8')