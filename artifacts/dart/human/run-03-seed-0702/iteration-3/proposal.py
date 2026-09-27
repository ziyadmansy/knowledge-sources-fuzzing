from hypothesis import strategies as st

# Constants for fields with constrained values
STATUS_VALUES = ['active', 'inactive', 'unknown']

# Helper to produce JSON string literals with proper escaping for minimal ASCII subset
# We keep it simple: only escape backslash and double quote, and control chars as \uXXXX
def json_string(s: str) -> str:
    # Escape backslash and double quote
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    # Escape control chars (U+0000 to U+001F)
    def esc_char(c):
        if ord(c) < 0x20:
            return '\\u%04x' % ord(c)
        else:
            return c
    return '"' + ''.join(esc_char(c) for c in s) + '"'

# Strategy for JSON string values (for "amount", "name", and tags elements)
# Use ASCII printable chars except control chars and quotes/backslash to keep escaping simple
json_string_chars = st.characters(
    whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs', 'Po', 'Ps', 'Pe'),
    blacklist_characters=['"', '\\']
)

json_string_strategy = json_string_chars.filter(lambda c: c not in ['"', '\\']).flatmap(
    lambda first: st.text(json_string_chars, min_size=0, max_size=10).map(lambda rest: first + rest)
).map(json_string)

# Strategy for "amount" field: always a JSON string, allow numeric-looking strings and others
amount_strategy = st.one_of(
    # Numeric strings (integer or decimal)
    st.integers(min_value=-10**10, max_value=10**10).map(str).map(json_string),
    st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False).map(lambda f: ('%.10g' % f)).map(json_string),
    # Arbitrary short strings
    json_string_strategy
)

# Strategy for "name" field: nullable string
name_strategy = st.one_of(
    st.just('null'),
    json_string_strategy
)

# Strategy for "status" field: one of the three allowed strings, plus some invalid strings for fuzzing
# But invalid strings are rejected by all four, so no disagreement there.
# So only produce valid status strings here.
status_strategy = st.sampled_from(STATUS_VALUES).map(json_string)

# Strategy for "tags" field: array of strings (possibly empty)
tags_strategy = st.lists(json_string_strategy, min_size=0, max_size=5).map(
    lambda lst: '[' + ','.join(lst) + ']'
)

# Strategy for "id" field:
# We want to exploit the difference:
# manual and built_value require true int (jsonDecode produces int for integer literals in 64-bit range)
# json_serializable and freezed accept double and convert to int via toInt()
# jsonDecode produces double for integer literals outside 64-bit range
# So produce either:
# - a JSON integer literal in 64-bit range (accepted by all)
# - a JSON number literal that is a double representing an integer outside 64-bit range (accepted by json_serializable/freezed but rejected by manual/built_value)
# - a JSON number literal that is a double but not integral (rejected by all)
# We want to maximize disagreement, so produce either:
# - int64-range integer literal (all accept)
# - double integer outside int64 range (only json_serializable/freezed accept)
# - double non-integer (all reject)
# But all reject non-integer double, so no disagreement there.
# So produce either int64 integer or double integer outside int64 range.
# int64 range: -2**63 .. 2**63-1
INT64_MIN = -2**63
INT64_MAX = 2**63 - 1

# JSON number literal as string (no quotes)
def json_number_literal(n: int | float) -> str:
    # For int, just str
    if isinstance(n, int):
        return str(n)
    # For float, use repr with minimal digits
    else:
        # Use repr but ensure decimal point or exponent present
        s = repr(n)
        if 'e' not in s and '.' not in s:
            s += '.0'
        return s

id_strategy = st.one_of(
    # int64-range integer literal (accepted by all)
    st.integers(min_value=INT64_MIN, max_value=INT64_MAX).map(json_number_literal),
    # double integer outside int64 range (accepted only by json_serializable/freezed)
    st.one_of(
        st.integers(min_value=INT64_MAX + 1, max_value=INT64_MAX + 10**6),
        st.integers(min_value=INT64_MIN - 10**6, max_value=INT64_MIN - 1)
    ).map(float).map(json_number_literal),
)

# Strategy for "child" field: nullable Record or null
# To avoid deep recursion, limit to one level of recursion only
# So child is either null or a record with child=null
# We'll define a helper for record without child recursion

@st.composite
def record_without_child(draw):
    # id
    id_val = draw(id_strategy)
    # amount
    amount_val = draw(amount_strategy)
    # name
    name_val = draw(name_strategy)
    # status
    status_val = draw(status_strategy)
    # tags
    tags_val = draw(tags_strategy)
    # child is null here
    child_val = 'null'
    # Compose JSON object string
    # Fields order: id, amount, name, status, tags, child
    obj = (
        '{'
        f'"id":{id_val},'
        f'"amount":{amount_val},'
        f'"name":{name_val},'
        f'"status":{status_val},'
        f'"tags":{tags_val},'
        f'"child":{child_val}'
        '}'
    )
    return obj

@st.composite
def record(draw):
    # id
    id_val = draw(id_strategy)
    # amount
    amount_val = draw(amount_strategy)
    # name
    name_val = draw(name_strategy)
    # status
    status_val = draw(status_strategy)
    # tags
    tags_val = draw(tags_strategy)
    # child: either null or record_without_child
    child_val = draw(st.one_of(
        st.just('null'),
        record_without_child()
    ))
    obj = (
        '{'
        f'"id":{id_val},'
        f'"amount":{amount_val},'
        f'"name":{name_val},'
        f'"status":{status_val},'
        f'"tags":{tags_val},'
        f'"child":{child_val}'
        '}'
    )
    return obj

# To maximize disagreement, also produce some documents missing the "tags" field
# built_value accepts missing tags as empty list, others reject
# So produce either full record or record missing "tags"
@st.composite
def generated_json(draw) -> bytes:
    # Decide if tags field is present or missing
    tags_present = draw(st.booleans())
    # id
    id_val = draw(id_strategy)
    # amount
    amount_val = draw(amount_strategy)
    # name
    name_val = draw(name_strategy)
    # status
    status_val = draw(status_strategy)
    # child: either null or record_without_child
    child_val = draw(st.one_of(
        st.just('null'),
        record_without_child()
    ))
    # Compose fields list
    fields = [
        f'"id":{id_val}',
        f'"amount":{amount_val}',
        f'"name":{name_val}',
        f'"status":{status_val}',
    ]
    if tags_present:
        tags_val = draw(tags_strategy)
        fields.append(f'"tags":{tags_val}')
    # else omit tags field

    fields.append(f'"child":{child_val}')

    # Shuffle fields order to avoid bias (optional)
    # But order is not significant in JSON objects
    # Hypothesis has no built-in shuffle, so keep order fixed for simplicity

    obj = '{' + ','.join(fields) + '}'
    return obj.encode('utf-8')