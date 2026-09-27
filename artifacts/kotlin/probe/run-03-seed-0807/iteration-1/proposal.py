from hypothesis import strategies as st

# We build JSON text manually, carefully controlling types and presence of fields.
# We use bounded recursion depth to avoid infinite nesting.
# We vary one or two fields at a time from well-formed baseline, focusing on known divergence points.

# Known divergence points to exploit:
# - amount: string or number accepted by Gson/Moshi/Jackson, but kotlinx rejects number
# - name: string or number accepted by Gson/Moshi/Jackson, kotlinx rejects non-string non-null
# - status: invalid enum accepted as null by Gson, rejected by others
# - tags: must be array; Gson/Moshi/Jackson accept nulls and non-string elements, kotlinx rejects
# - child: Gson accepts empty object {}, others reject missing required fields
# - unknown fields: Gson/Moshi ignore, kotlinx/Jackson reject
# - nulls in amount, tags in child: Gson accepts, others reject
# - enum null or invalid: Gson accepts as null, others reject
# We produce documents mostly well-formed but with one or two fields tweaked to trigger divergence.

# Base valid values for fields:
id_int = st.integers(min_value=0, max_value=10**6)
id_str = id_int.map(str)

amount_str = st.text(min_size=1, max_size=10).filter(lambda s: all(c not in '"\\' for c in s))  # simple string without quotes or backslash
amount_num = st.floats(allow_infinity=False, allow_nan=False, width=32).map(lambda f: str(f) if f % 1 else str(int(f)))

name_str = st.one_of(st.none(), st.text(min_size=1, max_size=10).filter(lambda s: all(c not in '"\\' for c in s)))
name_num = st.integers(min_value=-1000, max_value=1000).map(str)

status_valid = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
status_invalid = st.sampled_from(['"enabled"', '"ACTIVE"', 'null', '123', 'true', 'false', '""'])

# tags: array of strings normally; divergence on nulls and non-string elements
tag_str = st.text(min_size=1, max_size=10).filter(lambda s: all(c not in '"\\' for c in s))
tag_num = st.integers(min_value=-1000, max_value=1000).map(str)
tag_null = st.just('null')

# unknown field key and value
unknown_key = st.text(min_size=1, max_size=5).filter(lambda s: all(c not in '"\\' for c in s))
unknown_value = st.one_of(
    st.just('123'),
    st.just('"unknown"'),
    st.just('null'),
    st.just('true'),
    st.just('false'),
    st.just('{}'),
    st.just('[]'),
)

# recursion depth limit
MAX_DEPTH = 1

def json_string(s: str) -> str:
    # Return JSON string literal with quotes, no escaping needed since we filter input
    return '"' + s + '"'

def json_array(elems):
    return '[' + ','.join(elems) + ']'

def json_object(pairs):
    # pairs is list of (key, value) strings, keys already quoted
    return '{' + ','.join(k + ':' + v for k, v in pairs) + '}'

@st.composite
def gen_tags(draw, allow_nonstring=False, allow_null=False):
    # Produce tags array text
    # allow_nonstring: include numbers as elements
    # allow_null: include null as element
    elems = []
    # choose length 0..3
    length = draw(st.integers(min_value=0, max_value=3))
    for _ in range(length):
        choice = 0
        if allow_nonstring and allow_null:
            choice = draw(st.integers(min_value=0, max_value=2))
        elif allow_nonstring:
            choice = draw(st.integers(min_value=0, max_value=1))
        elif allow_null:
            choice = draw(st.integers(min_value=0, max_value=1))
        else:
            choice = 0
        if choice == 0:
            # string element
            s = draw(tag_str)
            elems.append(json_string(s))
        elif choice == 1 and allow_nonstring:
            # number element as string (JSON number)
            n = draw(tag_num)
            elems.append(n)
        else:
            # null element
            elems.append('null')
    return json_array(elems)

@st.composite
def gen_status(draw, allow_invalid=False, allow_null=False):
    if allow_invalid:
        # choose invalid or valid or null
        choice = draw(st.integers(min_value=0, max_value=2))
        if choice == 0:
            return draw(status_valid)
        elif choice == 1:
            return draw(status_invalid)
        else:
            return 'null'
    elif allow_null:
        # valid or null
        choice = draw(st.booleans())
        if choice:
            return draw(status_valid)
        else:
            return 'null'
    else:
        return draw(status_valid)

@st.composite
def gen_amount(draw, allow_number=True, allow_null=False):
    # amount normally string, but Gson/Moshi/Jackson accept number, kotlinx rejects number
    # Gson accepts null in nested child, others reject
    choice = 0
    if allow_null:
        choice = draw(st.integers(min_value=0, max_value=2 if allow_number else 1))
    else:
        choice = draw(st.integers(min_value=0, max_value=1 if allow_number else 0))
    if choice == 0:
        s = draw(amount_str)
        return json_string(s)
    elif choice == 1 and allow_number:
        return draw(amount_num)
    else:
        return 'null'

@st.composite
def gen_name(draw, allow_number=True, allow_null=True):
    # name can be string or null normally
    # Gson/Moshi/Jackson accept number converted to string; kotlinx rejects non-string non-null
    choice = 0
    if allow_null and allow_number:
        choice = draw(st.integers(min_value=0, max_value=2))
    elif allow_null:
        choice = draw(st.integers(min_value=0, max_value=1))
    elif allow_number:
        choice = draw(st.integers(min_value=0, max_value=1))
    else:
        choice = 0
    if choice == 0:
        # string or null
        if allow_null:
            if draw(st.booleans()):
                return 'null'
        s = draw(name_str.filter(lambda x: x is not None))
        return json_string(s)
    elif choice == 1 and allow_number:
        # number as JSON number (not string)
        n = draw(st.integers(min_value=-1000, max_value=1000))
        return str(n)
    else:
        return 'null'

@st.composite
def gen_id(draw):
    # id can be int or string
    if draw(st.booleans()):
        return str(draw(id_int))
    else:
        return json_string(draw(id_str))

@st.composite
def gen_child(draw, depth=0):
    # child is null or nested record (one level recursion normally)
    # Gson accepts empty object {}, others reject missing required fields
    # Gson accepts null amount and null tags in child; others reject
    # Gson accepts empty object recursively
    if depth >= MAX_DEPTH:
        # only null or empty object (to test Gson acceptance)
        choice = draw(st.integers(min_value=0, max_value=2))
        if choice == 0:
            return 'null'
        elif choice == 1:
            # empty object {}
            return '{}'
        else:
            # well-formed child with all fields present
            return draw(gen_record(depth=depth+1))
    else:
        # produce well-formed or empty or null child
        choice = draw(st.integers(min_value=0, max_value=2))
        if choice == 0:
            return 'null'
        elif choice == 1:
            return '{}'
        else:
            return draw(gen_record(depth=depth+1))

@st.composite
def gen_unknown_field(draw):
    k = draw(unknown_key)
    v = draw(unknown_value)
    return (json_string(k), v)

@st.composite
def gen_record(draw, depth=0):
    # Compose a record JSON text with fields:
    # id, amount, name, status, tags, child
    # We vary one or two fields from well-formed baseline to trigger divergences.
    # Also sometimes add unknown fields to test ignoring vs rejecting.

    # id: int or string
    id_val = draw(gen_id())

    # amount: string normally, sometimes number or null in child
    # allow number in top-level to trigger kotlinx rejection
    allow_amount_number = True if depth == 0 else True  # Gson accepts null in child, so allow null in child
    allow_amount_null = True if depth > 0 else False
    amount_val = draw(gen_amount(allow_number=allow_amount_number, allow_null=allow_amount_null))

    # name: string or null normally, sometimes number to trigger kotlinx rejection
    name_val = draw(gen_name(allow_number=True, allow_null=True))

    # status: valid enum normally, sometimes invalid or null to trigger Gson acceptance vs others reject
    allow_invalid_status = draw(st.booleans()) if depth == 0 else False
    allow_null_status = draw(st.booleans()) if depth == 0 else False
    status_val = draw(gen_status(allow_invalid=allow_invalid_status, allow_null=allow_null_status))

    # tags: array of strings normally, sometimes with null or non-string elements to trigger kotlinx rejection
    allow_tags_nonstring = draw(st.booleans()) if depth == 0 else False
    allow_tags_null = draw(st.booleans()) if depth == 0 else False
    tags_val = draw(gen_tags(allow_nonstring=allow_tags_nonstring, allow_null=allow_tags_null))

    # child: null or nested record or empty object
    child_val = draw(gen_child(depth=depth))

    # unknown fields: add unknown field at top-level sometimes to trigger rejection by kotlinx/Jackson
    add_unknown = draw(st.booleans()) if depth == 0 else False
    unknown_fields = []
    if add_unknown:
        uf = draw(gen_unknown_field())
        unknown_fields.append(uf)

    # Compose fields list
    fields = [
        ('"id"', id_val),
        ('"amount"', amount_val),
        ('"name"', name_val),
        ('"status"', status_val),
        ('"tags"', tags_val),
        ('"child"', child_val),
    ]
    fields.extend(unknown_fields)

    # Shuffle fields to vary order
    fields = draw(st.permutations(fields))

    return json_object(fields)

@st.composite
def generated_json(draw) -> bytes:
    # Generate a single top-level record JSON text as bytes
    s = draw(gen_record(depth=0))
    return s.encode('utf-8')