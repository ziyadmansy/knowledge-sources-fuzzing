from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only for safety
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings (elements already JSON strings)
def json_array_of_strings(elems) -> str:
    return '[' + ','.join(elems) + ']'

# Helper: JSON object from list of (key, value) pairs (keys are strings, values are JSON text)
def json_object(pairs) -> str:
    # pairs: list of (str, str)
    return '{' + ','.join(json_string(k) + ':' + v for k, v in pairs) + '}'

# Strategy to produce a valid "status" string or an invalid one (to trigger enum rejection)
status_valid = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
status_invalid = st.text(min_size=1, max_size=10).filter(lambda s: s not in ('active','inactive','unknown')).map(json_string)
# Also allow null for status to test null acceptance/rejection
status_null = st.just('null')

# Strategy for "id": integer or stringified integer (both accepted)
id_int = st.integers(min_value=0, max_value=2**31-1).map(str)
id_num = id_int.map(str)  # numeric as string
id_num_as_num = id_int.map(str)  # numeric as number (no quotes)
# We'll produce either numeric (no quotes) or string (quoted) for id
id_strategy = st.one_of(
    id_int.map(lambda i: str(i)),  # number (unquoted)
    id_int.map(lambda i: json_string(str(i)))  # string (quoted)
)

# Strategy for "amount": string normally, but also numeric (number) to test coercion
amount_str = st.text(min_size=0, max_size=10).map(json_string)
amount_num = st.integers(min_value=0, max_value=10**6).map(str)  # numeric unquoted
amount_strategy = st.one_of(amount_str, amount_num)

# Strategy for "name": string or null normally, but also number or boolean coerced to string
name_string = st.one_of(st.none().map(lambda _: 'null'), st.text(min_size=0, max_size=10).map(json_string))
name_number = st.integers(min_value=-1000, max_value=1000).map(str)
name_boolean = st.sampled_from(['true', 'false'])
name_strategy = st.one_of(name_string, name_number, name_boolean)

# Strategy for "status": valid enum string, invalid enum string, or null
status_strategy = st.one_of(status_valid, status_invalid, status_null)

# Strategy for "tags": array of strings normally, but also arrays with nulls or non-string elements
tag_string = st.text(min_size=0, max_size=10).map(json_string)
tag_null = st.just('null')
tag_number = st.integers(min_value=-10, max_value=10).map(str)
tag_boolean = st.sampled_from(['true', 'false'])
tags_element = st.one_of(tag_string, tag_null, tag_number, tag_boolean)
tags_array = st.lists(tags_element, min_size=0, max_size=5).map(json_array_of_strings)
# Also allow non-array for tags to test rejection
tags_non_array = st.one_of(
    st.text(min_size=1, max_size=10).map(json_string),
    st.integers(min_value=0, max_value=100).map(str),
    st.just('null'),
    st.sampled_from(['true', 'false'])
)
tags_strategy = st.one_of(tags_array, tags_non_array)

# Recursive child record strategy with bounded depth (max 1 level)
# We'll produce either null or a child object with fields
@st.composite
def child_record(draw, depth=0):
    if depth >= 1:
        # Only null or empty object (to test empty child)
        choice = draw(st.sampled_from(['null', '{}']))
        return choice
    else:
        # Compose child fields similarly to top-level, but simpler to avoid explosion
        id_val = draw(id_strategy)
        amount_val = draw(amount_strategy)
        name_val = draw(name_strategy)
        status_val = draw(status_strategy)
        tags_val = draw(tags_strategy)
        # For child.child, only null or empty object to test nested empty child
        child_child_val = draw(st.one_of(st.just('null'), st.just('{}')))
        # Compose child object
        pairs = [
            ('id', id_val),
            ('amount', amount_val),
            ('name', name_val),
            ('status', status_val),
            ('tags', tags_val),
            ('child', child_child_val)
        ]
        return json_object(pairs)

@st.composite
def generated_json(draw) -> bytes:
    # Compose top-level fields
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_strategy)
    status_val = draw(status_strategy)
    tags_val = draw(tags_strategy)
    child_val = draw(child_record(depth=0))

    # Compose top-level object
    pairs = [
        ('id', id_val),
        ('amount', amount_val),
        ('name', name_val),
        ('status', status_val),
        ('tags', tags_val),
        ('child', child_val)
    ]

    # Occasionally add an extra top-level field to test extra fields acceptance/rejection
    add_extra = draw(st.booleans())
    if add_extra:
        extra_key = draw(st.text(min_size=1, max_size=5).filter(lambda s: s not in {'id','amount','name','status','tags','child'}))
        extra_val = draw(st.one_of(
            st.text(min_size=0, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=100).map(str),
            st.just('null'),
            st.sampled_from(['true', 'false']),
            st.just('{}'),
            st.just('[]')
        ))
        pairs.append((extra_key, extra_val))

    json_text = json_object(pairs)
    return json_text.encode('utf-8')