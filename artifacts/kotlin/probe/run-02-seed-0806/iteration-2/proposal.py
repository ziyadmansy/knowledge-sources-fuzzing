from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only for simplicity
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings, allowing nulls or non-strings if needed
def json_array_of_strings_or_other(draw, allow_null=False, allow_non_string=False):
    # Elements can be string, or if allowed null, null, or if allowed non-string, number or bool
    elems = []
    # Compose element strategy
    elem_strat = st.text(min_size=0, max_size=10).map(json_string)
    if allow_null:
        elem_strat = st.one_of(elem_strat, st.just("null"))
    if allow_non_string:
        # non-string elements: number (int) or bool
        non_str = st.one_of(
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
        )
        elem_strat = st.one_of(elem_strat, non_str)
    # array length 0..5
    return st.lists(elem_strat, max_size=5).map(lambda lst: "[" + ",".join(lst) + "]")

# Helper: JSON enum for status, with options for unknown or null
def json_status(draw, allow_unknown=False, allow_null=False):
    base = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
    if allow_unknown:
        base = st.one_of(base, st.text(min_size=1, max_size=10).map(json_string).filter(lambda x: x not in ['"active"', '"inactive"', '"unknown"']))
    if allow_null:
        base = st.one_of(base, st.just("null"))
    return base

# Helper: JSON value for "name" field: string or null
def json_name(draw):
    return st.one_of(st.none().map(lambda _: "null"), st.text(min_size=0, max_size=20).map(json_string))

# Helper: JSON value for "id" field: int or string of int, or invalid types for divergence
def json_id(draw, allow_number=True, allow_string=True, allow_invalid=False):
    # valid int range for id: 0..1_000_000
    valid_int = st.integers(min_value=0, max_value=1_000_000)
    # string of int
    str_int = valid_int.map(lambda i: json_string(str(i)))
    # invalid types: bool, float string, empty string, array, object
    invalid = st.one_of(
        st.booleans().map(lambda b: "true" if b else "false"),
        st.floats(allow_infinity=False, allow_nan=False).map(lambda f: str(f)),
        st.just('""'),
        st.just("[]"),
        st.just("{}"),
    )
    parts = []
    if allow_number:
        parts.append(valid_int.map(str))
    if allow_string:
        parts.append(str_int)
    if allow_invalid:
        parts.append(invalid)
    return st.one_of(parts)

# Helper: JSON value for "amount" field: string or number or invalid (for divergence)
def json_amount(draw, allow_string=True, allow_number=True, allow_invalid=False):
    # amount is string normally, but Gson/Moshi/Jackson accept number coercion, kotlinx rejects number
    # valid amount strings: digits or decimal with optional leading zeros
    amount_str = st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c == '.' for c in s)).map(json_string)
    amount_num = st.floats(min_value=0, max_value=1_000_000, allow_infinity=False, allow_nan=False).map(lambda f: str(f) if f % 1 else str(int(f)))
    invalid = st.one_of(
        st.booleans().map(lambda b: "true" if b else "false"),
        st.just("null"),
        st.just("[]"),
        st.just("{}"),
        st.just('""'),
    )
    parts = []
    if allow_string:
        parts.append(amount_str)
    if allow_number:
        parts.append(amount_num)
    if allow_invalid:
        parts.append(invalid)
    return st.one_of(parts)

# Helper: JSON value for "child" field: null or nested record or empty object (for divergence)
def json_child(draw, depth=0, max_depth=1):
    # At max depth, child must be null or empty object (to test empty object acceptance)
    if depth >= max_depth:
        # empty object or null
        return st.one_of(st.just("null"), st.just("{}"))
    else:
        # nested record or null or empty object (for divergence)
        return st.one_of(
            st.just("null"),
            generated_record(draw, depth=depth+1, max_depth=max_depth),
            st.just("{}"),
        )

# Compose a full record JSON string with controlled divergence on one or two fields
@st.composite
def generated_record(draw, depth=0, max_depth=1):
    # id: test number or string or invalid
    id_json = draw(json_id(allow_number=True, allow_string=True, allow_invalid=True))
    # amount: string or number or invalid
    amount_json = draw(json_amount(allow_string=True, allow_number=True, allow_invalid=True))
    # name: string or null
    name_json = draw(json_name())
    # status: enum, with possibility of unknown or null for divergence
    # We'll allow unknown only sometimes to trigger divergence
    allow_unknown = draw(st.booleans())
    allow_null_status = draw(st.booleans())
    status_json = draw(json_status(allow_unknown=allow_unknown, allow_null=allow_null_status))
    # tags: array of strings, sometimes with nulls or non-strings for divergence
    allow_null_tags = draw(st.booleans())
    allow_non_string_tags = draw(st.booleans())
    tags_json = draw(json_array_of_strings_or_other(allow_null=allow_null_tags, allow_non_string=allow_non_string_tags))
    # child: null, nested record, or empty object (empty object accepted only by Gson)
    child_json = draw(json_child(depth=depth, max_depth=max_depth))

    # Compose JSON object string with fields in fixed order for readability
    parts = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
        '"child":' + child_json,
    ]
    return "{" + ",".join(parts) + "}"

@st.composite
def generated_json(draw) -> bytes:
    # Generate a record with max_depth=1 (one level recursion)
    s = draw(generated_record(max_depth=1))
    return s.encode("utf-8")