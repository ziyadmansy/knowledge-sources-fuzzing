from hypothesis import strategies as st

# Constants for fixed values
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce JSON string literal from Hypothesis string, escaping quotes and backslashes
def json_string_literal(s: str) -> str:
    # Escape backslash and double quotes for JSON string literal
    # Also escape control chars minimally (newline, tab)
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')
    return '"' + s + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, conforming to the record schema,
    but with subtle variations to provoke divergence among the four Dart deserializers.
    """

    # --- Primitive fields ---

    # id: integer (required)
    # To provoke subtle divergence, try integers and also floats as strings (should be rejected)
    # But all reject type mismatch for id, so keep it integer only.
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    id_json = str(id_val)

    # amount: string (any string accepted)
    # To provoke divergence, try numeric strings, empty string, or arbitrary strings
    amount_str = draw(st.one_of(
        st.text(min_size=0, max_size=10),
        st.integers(min_value=0, max_value=999999).map(str),
        st.just(""),  # empty string allowed
        st.just("NaN"),
        st.just("-123.45"),
    ))
    amount_json = json_string_literal(amount_str)

    # name: string or null or missing
    # name is optional; if missing, all decode as null
    # To provoke divergence, sometimes omit, sometimes null, sometimes string
    name_choice = draw(st.sampled_from(['omit', 'null', 'string']))
    if name_choice == 'omit':
        name_json = None
    elif name_choice == 'null':
        name_json = 'null'
    else:
        # string or empty string
        name_val = draw(st.text(min_size=0, max_size=20))
        name_json = json_string_literal(name_val)

    # status: one of "active", "inactive", "unknown"
    # To provoke divergence, try valid values only (all reject invalid)
    # But also try to provoke rejection by adding whitespace inside string (should be rejected)
    # or adding escape sequences (should be rejected)
    # But all reject unknown values or null or empty string
    # So mostly pick valid values, but sometimes add trailing space (should be rejected)
    status_val = draw(st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.just('"active "'),  # trailing space, invalid
        st.just('"inactive\n"'),  # newline inside string, invalid
    ))

    # tags: array of strings, or null or object (only built_value accepts null/object as empty list)
    # tags containing non-string elements or string itself is rejected by all
    # To provoke divergence, sometimes produce null, sometimes object, sometimes array of strings
    tags_type = draw(st.sampled_from(['array', 'null', 'object']))

    if tags_type == 'array':
        # array of strings (possibly empty)
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
        # All reject non-string elements, so keep strings only
        # Build JSON array literal
        tags_json = '[' + ','.join(json_string_literal(t) for t in tags_list) + ']'
    elif tags_type == 'null':
        # null (accepted only by built_value)
        tags_json = 'null'
    else:
        # object (accepted only by built_value)
        # produce a simple object with string keys and string values
        obj_keys = draw(st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=3, unique=True))
        obj_items = []
        for k in obj_keys:
            v = draw(st.text(min_size=0, max_size=5))
            obj_items.append(json_string_literal(k) + ':' + json_string_literal(v))
        tags_json = '{' + ','.join(obj_items) + '}'

    # child: null or valid record (one level recursion)
    # To provoke divergence, sometimes null, sometimes valid record, sometimes malformed record
    # But all reject child as array or empty object
    # Also all reject missing required fields or type mismatches in child
    # So produce either null or a valid record with subtle variations

    def gen_child_record():
        # id integer
        cid = draw(st.integers(min_value=0, max_value=2**31-1))
        cid_json = str(cid)

        # amount string
        camount = draw(st.text(min_size=0, max_size=10))
        camount_json = json_string_literal(camount)

        # name optional
        cname_choice = draw(st.sampled_from(['omit', 'null', 'string']))
        if cname_choice == 'omit':
            cname_json = None
        elif cname_choice == 'null':
            cname_json = 'null'
        else:
            cname_val = draw(st.text(min_size=0, max_size=20))
            cname_json = json_string_literal(cname_val)

        # status valid only
        cstatus = draw(st.sampled_from(STATUS_VALUES))

        # tags: only array of strings or null or object (same as top-level)
        ctags_type = draw(st.sampled_from(['array', 'null', 'object']))
        if ctags_type == 'array':
            ctags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=3))
            ctags_json = '[' + ','.join(json_string_literal(t) for t in ctags_list) + ']'
        elif ctags_type == 'null':
            ctags_json = 'null'
        else:
            cobj_keys = draw(st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=2, unique=True))
            cobj_items = []
            for k in cobj_keys:
                v = draw(st.text(min_size=0, max_size=5))
                cobj_items.append(json_string_literal(k) + ':' + json_string_literal(v))
            ctags_json = '{' + ','.join(cobj_items) + '}'

        # child: null only (no recursion beyond one level)
        cchild_json = 'null'

        # Build child record JSON object fields
        child_fields = [
            '"id":' + cid_json,
            '"amount":' + camount_json,
        ]
        if cname_json is not None:
            child_fields.append('"name":' + cname_json)
        # else omit name field

        child_fields.extend([
            '"status":' + cstatus,
            '"tags":' + ctags_json,
            '"child":' + cchild_json,
        ])

        return '{' + ','.join(child_fields) + '}'

    child_choice = draw(st.sampled_from(['null', 'record']))
    if child_choice == 'null':
        child_json = 'null'
    else:
        child_json = gen_child_record()

    # Compose top-level JSON object fields
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
    ]
    if name_json is not None:
        fields.append('"name":' + name_json)
    # else omit name field

    fields.extend([
        '"status":' + status_val,
        '"tags":' + tags_json,
        '"child":' + child_json,
    ])

    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')