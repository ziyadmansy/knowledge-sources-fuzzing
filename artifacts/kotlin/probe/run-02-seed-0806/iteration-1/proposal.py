from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only for simplicity
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: produce JSON array text from list of JSON element texts
def json_array(elems):
    return '[' + ','.join(elems) + ']'

# Helper: produce JSON object text from list of (key, json_value_text)
def json_object(pairs):
    # keys are always strings, so quote them
    return '{' + ','.join(json_string(k) + ':' + v for k, v in pairs) + '}'

# Strategy for "status" enum values, including known and some unknown for divergence
status_known = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
status_unknown = st.sampled_from(['"pending"', '"disabled"', '"null"', '"ACTIVE"', '"InActive"'])
# Also null for testing Gson acceptance of null enum
status_null = st.just('null')

# Strategy for "id" field: integer or stringified integer, or malformed string
id_int = st.integers(min_value=0, max_value=2**31-1).map(str)
id_str_int = id_int.map(lambda s: json_string(s))
id_str_nonint = st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()).map(json_string)
id_num = id_int
id_choice = st.one_of(id_num.map(str), id_str_int)

# Strategy for "amount" field: string or number, or malformed number
amount_str = st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string)
amount_num = st.floats(allow_infinity=False, allow_nan=False, width=32).map(lambda f: repr(f) if f % 1 else str(int(f)))
amount_choice = st.one_of(amount_str, amount_num)

# Strategy for "name": string or null
name_str = st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string)
name_null = st.just('null')
name_choice = st.one_of(name_str, name_null)

# Strategy for "tags": array of strings, or array with non-string elements, or null
tag_str = st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string)
tag_nonstring = st.one_of(
    st.integers(min_value=-100, max_value=100).map(str),
    st.just('null'),
    st.booleans().map(lambda b: 'true' if b else 'false'),
)
# tags array variants:
# - all strings
# - some non-string elements (int, bool, null)
# - null
tags_all_strings = st.lists(tag_str, min_size=0, max_size=5).map(json_array)
tags_some_nonstring = st.lists(st.one_of(tag_str, tag_nonstring), min_size=1, max_size=5).map(json_array)
tags_null = st.just('null')
tags_choice = st.one_of(tags_all_strings, tags_some_nonstring, tags_null)

# Forward declaration for child record (one level recursion)
def record_json():
    # We'll define this later with bounded recursion
    return st.deferred(lambda: generated_record_json(allow_child=True))

# Strategy for "child": either null or a nested record (one level only)
child_null = st.just('null')

# Compose a record JSON text from fields, with options to tweak fields for divergence
@st.composite
def generated_record_json(draw, allow_child=True):
    # id: number or string number or malformed string (to trigger divergence)
    id_val = draw(st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),
        st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()).map(json_string),
        st.integers(min_value=0, max_value=2**31-1).map(lambda i: json_string(str(i))),
    ))
    # amount: string or number or malformed number (to trigger divergence)
    amount_val = draw(st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string),
        st.floats(allow_infinity=False, allow_nan=False, width=32).map(lambda f: repr(f) if f % 1 else str(int(f))),
        st.integers(min_value=0, max_value=100000).map(str),
    ))
    # name: string or null
    name_val = draw(name_choice)
    # status: known enum, unknown enum, or null (to trigger divergence)
    status_val = draw(st.one_of(status_known, status_unknown, status_null))
    # tags: array of strings, array with non-string elements, or null
    tags_val = draw(tags_choice)
    # child: null or nested record (one level only)
    if allow_child:
        child_val = draw(st.one_of(child_null, record_json()))
    else:
        child_val = draw(child_null)

    # Compose JSON object text with all six fields
    obj = json_object([
        ('id', id_val),
        ('amount', amount_val),
        ('name', name_val),
        ('status', status_val),
        ('tags', tags_val),
        ('child', child_val),
    ])
    return obj

@st.composite
def generated_json(draw) -> bytes:
    # Generate a top-level record JSON text with one level child recursion
    # This is the root document
    doc_text = draw(generated_record_json(allow_child=True))
    return doc_text.encode('utf-8')