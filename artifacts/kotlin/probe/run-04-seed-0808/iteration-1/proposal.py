from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper to produce JSON string literal from Python str (minimal escaping)
    # Only escape backslash and double quote and control chars \b\f\n\r\t as \uXXXX
    def json_string(s: str) -> str:
        def esc_char(c):
            o = ord(c)
            if c == '"':
                return '\\"'
            if c == '\\':
                return '\\\\'
            if c == '\b':
                return '\\b'
            if c == '\f':
                return '\\f'
            if c == '\n':
                return '\\n'
            if c == '\r':
                return '\\r'
            if c == '\t':
                return '\\t'
            if o < 0x20:
                return '\\u%04x' % o
            return c
        return '"' + ''.join(esc_char(c) for c in s) + '"'

    # Known enum values and some invalid ones for testing
    valid_statuses = ['"active"', '"inactive"', '"unknown"']
    invalid_statuses = ['"invalid"', '"Active"', '123', 'null']

    # id field: int or string of int (string always decimal digits)
    # Known: all accept int or string for id, string converted to int
    def gen_id():
        # 90% int, 10% string of int
        as_int = draw(st.integers(min_value=0, max_value=10**9))
        as_str = str(as_int)
        use_str = draw(st.booleans())
        if use_str:
            return as_str, json_string(as_str)
        else:
            return as_int, str(as_int)

    # amount field: string or number
    # Known: Gson, Moshi, Jackson accept string or number (convert number to string)
    #        kotlinx rejects number
    # We want to try both string and number here to create divergence
    def gen_amount():
        # 50% string, 50% number
        use_str = draw(st.booleans())
        if use_str:
            # string can be any string, including numeric strings or others
            s = draw(st.text(min_size=0, max_size=10))
            return s, json_string(s)
        else:
            # number: integer or float, positive or zero
            # Use int or float to increase chance of divergence
            is_float = draw(st.booleans())
            if is_float:
                f = draw(st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False))
                # Format float with minimal digits, no exponent
                # Use repr to get full precision, but remove trailing zeros
                fs = repr(f)
                if 'e' in fs or 'E' in fs:
                    # convert exponent to decimal notation if possible
                    fs = format(f, 'f').rstrip('0').rstrip('.')
                else:
                    fs = fs.rstrip('0').rstrip('.') if '.' in fs else fs
                if fs == '':
                    fs = '0'
                return fs, fs
            else:
                i = draw(st.integers(min_value=0, max_value=10**9))
                return str(i), str(i)

    # name field: string or null or number (number accepted by Gson, Moshi, Jackson as string; rejected by kotlinx)
    def gen_name():
        choice = draw(st.integers(min_value=0, max_value=3))
        if choice == 0:
            # string or empty string
            s = draw(st.text(min_size=0, max_size=10))
            return s, json_string(s)
        elif choice == 1:
            # null
            return None, 'null'
        elif choice == 2:
            # number as string (int)
            n = draw(st.integers(min_value=0, max_value=10**9))
            return str(n), str(n)
        else:
            # number as float string
            f = draw(st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False))
            fs = repr(f)
            if 'e' in fs or 'E' in fs:
                fs = format(f, 'f').rstrip('0').rstrip('.')
            else:
                fs = fs.rstrip('0').rstrip('.') if '.' in fs else fs
            if fs == '':
                fs = '0'
            return fs, fs

    # status field: enum string (valid or invalid), or null (Gson accepts null, others reject)
    def gen_status():
        choice = draw(st.integers(min_value=0, max_value=4))
        if choice == 0:
            # valid enum string
            s = draw(st.sampled_from(valid_statuses))
            return s[1:-1], s
        elif choice == 1:
            # invalid enum string (Gson accepts as null, others reject)
            s = draw(st.sampled_from(invalid_statuses))
            # if s is a string literal, strip quotes for value, keep quotes for JSON
            if s.startswith('"') and s.endswith('"'):
                return s[1:-1], s
            else:
                return s, s
        elif choice == 2:
            # null (Gson accepts null, others reject)
            return None, 'null'
        else:
            # missing field (simulate by returning None and special marker)
            # But we must always produce all six fields, so we do not omit fields here
            # Instead produce valid enum to avoid missing field
            s = draw(st.sampled_from(valid_statuses))
            return s[1:-1], s

    # tags field: array of strings normally
    # Known: all reject non-array; Gson, Moshi, Jackson accept arrays with non-string elements converting to strings;
    #        kotlinx rejects non-string elements in array
    # We try both pure string arrays and arrays with mixed types (int, bool, null)
    def gen_tags():
        # 50% pure string array, 50% mixed array
        pure_strings = draw(st.booleans())
        length = draw(st.integers(min_value=0, max_value=5))
        if pure_strings:
            strs = draw(st.lists(st.text(min_size=0, max_size=10), min_size=length, max_size=length))
            json_elems = [json_string(s) for s in strs]
            return strs, '[' + ','.join(json_elems) + ']'
        else:
            # mixed elements: string, int, bool, null
            elems = []
            json_elems = []
            for _ in range(length):
                t = draw(st.sampled_from(['string', 'int', 'bool', 'null']))
                if t == 'string':
                    s = draw(st.text(min_size=0, max_size=10))
                    elems.append(s)
                    json_elems.append(json_string(s))
                elif t == 'int':
                    i = draw(st.integers(min_value=-(10**9), max_value=10**9))
                    elems.append(i)
                    json_elems.append(str(i))
                elif t == 'bool':
                    b = draw(st.booleans())
                    elems.append(b)
                    json_elems.append('true' if b else 'false')
                else:
                    elems.append(None)
                    json_elems.append('null')
            return elems, '[' + ','.join(json_elems) + ']'

    # child field: null or nested record (one level recursion max)
    # To avoid infinite recursion, only one level deep
    # Compose a nested record with same rules but no further nesting
    def gen_child():
        has_child = draw(st.booleans())
        if not has_child:
            return None, 'null'
        else:
            # nested record, but child.child is always null to limit recursion
            # reuse all above generators but child.child fixed null
            id_val, id_json = gen_id()
            amount_val, amount_json = gen_amount()
            name_val, name_json = gen_name()
            status_val, status_json = gen_status()
            tags_val, tags_json = gen_tags()
            # child.child is null
            child_child_val = None
            child_child_json = 'null'

            # Compose child JSON text
            child_fields = [
                '"id":' + id_json,
                '"amount":' + amount_json,
                '"name":' + name_json,
                '"status":' + status_json,
                '"tags":' + tags_json,
                '"child":' + child_child_json,
            ]
            child_json = '{' + ','.join(child_fields) + '}'
            child_val = {
                "id": id_val,
                "amount": amount_val,
                "name": name_val,
                "status": status_val,
                "tags": tags_val,
                "child": child_child_val,
            }
            return child_val, child_json

    # Compose top-level record
    id_val, id_json = gen_id()
    amount_val, amount_json = gen_amount()
    name_val, name_json = gen_name()
    status_val, status_json = gen_status()
    tags_val, tags_json = gen_tags()
    child_val, child_json = gen_child()

    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
        '"child":' + child_json,
    ]
    json_text = '{' + ','.join(fields) + '}'
    return json_text.encode('utf-8')