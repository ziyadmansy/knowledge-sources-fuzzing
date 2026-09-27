from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper: produce a JSON string literal from a Python string (with minimal escaping)
    # We only escape backslash and double quote and control chars for safety.
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars (U+0000 to U+001F)
        def esc_char(c):
            o = ord(c)
            if c == '"':
                return r'\"'
            elif c == '\\':
                return r'\\'
            elif o <= 0x1F:
                # Use \u00XX escape
                return '\\u%04x' % o
            else:
                return c
        return '"' + ''.join(esc_char(c) for c in s) + '"'

    # Helper: produce JSON text for a field with given name and JSON value text
    def field(name: str, value_json: str) -> str:
        return json_string(name) + ':' + value_json

    # Primitive JSON values as text
    # id: integer
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    id_json = str(id_val)

    # amount: string, but we will sometimes produce non-string to cause divergence
    # Strategy: mostly string, sometimes int or bool or null or array or object to cause divergence
    amount_type = draw(st.sampled_from(['string', 'int', 'bool', 'null', 'array', 'object']))
    if amount_type == 'string':
        # string with some edge cases: empty, numeric-looking, unicode, escapes
        amount_str = draw(st.one_of(
            st.text(min_size=0, max_size=20),
            st.just(""),
            st.just("0"),
            st.just("123.45"),
            st.just("true"),
            st.just("null"),
            st.just("\"\\"),  # string with quote and backslash to test escaping
        ))
        amount_json = json_string(amount_str)
    elif amount_type == 'int':
        amount_json = str(draw(st.integers(min_value=-1000, max_value=1000)))
    elif amount_type == 'bool':
        amount_json = draw(st.sampled_from(['true', 'false']))
    elif amount_type == 'null':
        amount_json = 'null'
    elif amount_type == 'array':
        # array of strings or numbers or mixed
        arr_len = draw(st.integers(min_value=0, max_value=3))
        arr_elems = []
        for _ in range(arr_len):
            v = draw(st.one_of(
                st.text(min_size=0, max_size=5).map(json_string),
                st.integers(min_value=-10, max_value=10).map(str),
                st.sampled_from(['true','false','null'])
            ))
            arr_elems.append(v)
        amount_json = '[' + ','.join(arr_elems) + ']'
    else:  # object
        # simple object with one or two string fields
        obj_len = draw(st.integers(min_value=0, max_value=2))
        obj_fields = []
        for i in range(obj_len):
            k = draw(st.text(min_size=1, max_size=5))
            v = draw(st.text(min_size=0, max_size=5))
            obj_fields.append(json_string(k) + ':' + json_string(v))
        amount_json = '{' + ','.join(obj_fields) + '}'

    # name: string or null, but sometimes wrong type or missing to cause divergence
    # We'll produce either a string, null, or a wrong type (int, bool, array, object)
    name_type = draw(st.sampled_from(['string', 'null', 'int', 'bool', 'array', 'object', 'missing']))
    if name_type == 'string':
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        if name_val is None:
            name_json = 'null'
        else:
            name_json = json_string(name_val)
        name_field = field('name', name_json)
    elif name_type == 'null':
        name_field = field('name', 'null')
    elif name_type == 'int':
        name_field = field('name', str(draw(st.integers(min_value=-1000, max_value=1000))))
    elif name_type == 'bool':
        name_field = field('name', draw(st.sampled_from(['true', 'false'])))
    elif name_type == 'array':
        arr_len = draw(st.integers(min_value=0, max_value=3))
        arr_elems = []
        for _ in range(arr_len):
            v = draw(st.one_of(
                st.text(min_size=0, max_size=5).map(json_string),
                st.integers(min_value=-10, max_value=10).map(str),
                st.sampled_from(['true','false','null'])
            ))
            arr_elems.append(v)
        name_field = field('name', '[' + ','.join(arr_elems) + ']')
    elif name_type == 'object':
        obj_len = draw(st.integers(min_value=0, max_value=2))
        obj_fields = []
        for i in range(obj_len):
            k = draw(st.text(min_size=1, max_size=5))
            v = draw(st.text(min_size=0, max_size=5))
            obj_fields.append(json_string(k) + ':' + json_string(v))
        name_field = field('name', '{' + ','.join(obj_fields) + '}')
    else:  # missing
        name_field = None

    # status: one of "active", "inactive", "unknown"
    # But sometimes wrong type or wrong string to cause divergence
    status_type = draw(st.sampled_from(['valid', 'wrong_string', 'int', 'bool', 'null', 'missing']))
    if status_type == 'valid':
        status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        status_json = json_string(status_val)
        status_field = field('status', status_json)
    elif status_type == 'wrong_string':
        # string but not one of the three allowed
        wrong_str = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ('active','inactive','unknown')))
        status_field = field('status', json_string(wrong_str))
    elif status_type == 'int':
        status_field = field('status', str(draw(st.integers(min_value=0, max_value=10))))
    elif status_type == 'bool':
        status_field = field('status', draw(st.sampled_from(['true', 'false'])))
    elif status_type == 'null':
        status_field = field('status', 'null')
    else:  # missing
        status_field = None

    # tags: array of strings, but sometimes wrong type or missing or empty
    tags_type = draw(st.sampled_from(['valid', 'empty', 'wrong_type', 'missing']))
    if tags_type == 'valid':
        tags_len = draw(st.integers(min_value=1, max_value=5))
        tags_elems = [json_string(draw(st.text(min_size=0, max_size=10))) for _ in range(tags_len)]
        tags_json = '[' + ','.join(tags_elems) + ']'
        tags_field = field('tags', tags_json)
    elif tags_type == 'empty':
        tags_field = field('tags', '[]')
    elif tags_type == 'wrong_type':
        # produce a non-array: string, int, bool, null, object
        wrong_choice = draw(st.sampled_from(['string', 'int', 'bool', 'null', 'object']))
        if wrong_choice == 'string':
            tags_field = field('tags', json_string(draw(st.text(min_size=0, max_size=10))))
        elif wrong_choice == 'int':
            tags_field = field('tags', str(draw(st.integers(min_value=-10, max_value=10))))
        elif wrong_choice == 'bool':
            tags_field = field('tags', draw(st.sampled_from(['true', 'false'])))
        elif wrong_choice == 'null':
            tags_field = field('tags', 'null')
        else:
            obj_len = draw(st.integers(min_value=0, max_value=2))
            obj_fields = []
            for i in range(obj_len):
                k = draw(st.text(min_size=1, max_size=5))
                v = draw(st.text(min_size=0, max_size=5))
                obj_fields.append(json_string(k) + ':' + json_string(v))
            tags_field = field('tags', '{' + ','.join(obj_fields) + '}')
    else:  # missing
        tags_field = None

    # child: either null or a nested record (one level only), or wrong type or missing
    child_type = draw(st.sampled_from(['null', 'record', 'wrong_type', 'missing']))

    def make_child_record():
        # child record must have all six fields present and well-formed, but we can vary slightly
        # For child, keep it simpler: always well-formed but vary name null or string, tags empty or 1 elem
        cid = draw(st.integers(min_value=0, max_value=2**31-1))
        camount = draw(st.text(min_size=0, max_size=10))
        cname = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        cstatus = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        ctags_len = draw(st.integers(min_value=0, max_value=2))
        ctags = [json_string(draw(st.text(min_size=0, max_size=5))) for _ in range(ctags_len)]
        cchild = 'null'  # no recursion beyond one level

        parts = [
            field('id', str(cid)),
            field('amount', json_string(camount)),
            field('name', 'null' if cname is None else json_string(cname)),
            field('status', json_string(cstatus)),
            field('tags', '[' + ','.join(ctags) + ']'),
            field('child', cchild),
        ]
        return '{' + ','.join(parts) + '}'

    if child_type == 'null':
        child_field = field('child', 'null')
    elif child_type == 'record':
        child_field = field('child', make_child_record())
    elif child_type == 'wrong_type':
        # produce a non-object, e.g. string, int, bool, array, null (but null is covered)
        wrong_choice = draw(st.sampled_from(['string', 'int', 'bool', 'array']))
        if wrong_choice == 'string':
            child_field = field('child', json_string(draw(st.text(min_size=0, max_size=10))))
        elif wrong_choice == 'int':
            child_field = field('child', str(draw(st.integers(min_value=-10, max_value=10))))
        elif wrong_choice == 'bool':
            child_field = field('child', draw(st.sampled_from(['true', 'false'])))
        else:
            arr_len = draw(st.integers(min_value=0, max_value=3))
            arr_elems = [json_string(draw(st.text(min_size=0, max_size=5))) for _ in range(arr_len)]
            child_field = field('child', '[' + ','.join(arr_elems) + ']')
    else:  # missing
        child_field = None

    # Compose fields, omitting those marked missing
    fields = [field('id', id_json), field('amount', amount_json)]
    if name_field is not None:
        fields.append(name_field)
    if status_field is not None:
        fields.append(status_field)
    if tags_field is not None:
        fields.append(tags_field)
    if child_field is not None:
        fields.append(child_field)

    # Shuffle fields order to add variation
    fields = draw(st.permutations(fields))

    json_text = '{' + ','.join(fields) + '}'
    return json_text.encode('utf-8')