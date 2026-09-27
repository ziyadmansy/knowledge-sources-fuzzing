from hypothesis import strategies as st

# Helper: JSON string escaping for Hypothesis-generated strings
def json_string_escape(s: str) -> str:
    # Minimal escaping for JSON strings: backslash, quote, control chars
    # Hypothesis strings are unicode, so escape control chars and backslash, quote
    # We'll do a simple replace chain
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\b', '\\b')
    s = s.replace('\f', '\\f')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    # Other control chars (U+0000 to U+001F) replaced with \u00XX
    def esc_char(c):
        if ord(c) < 0x20:
            return '\\u%04x' % ord(c)
        else:
            return c
    s = ''.join(esc_char(c) for c in s)
    return s

# Compose a JSON string literal from a Hypothesis string
def json_string(draw, base=st.text(min_size=0, max_size=20)):
    s = draw(base)
    return '"' + json_string_escape(s) + '"'

# Compose a JSON array of strings (for "tags")
# We want to vary element types to trigger divergences:
# - all string elements (valid)
# - some non-string elements (int, bool, null) to trigger rejection by kotlinx
# - some null elements (accepted by Gson, Moshi, Jackson; rejected by kotlinx)
# We'll produce arrays with 0 to 5 elements.
tags_element = st.one_of(
    st.text(min_size=0, max_size=10).map(lambda s: '"' + json_string_escape(s) + '"'),
    st.integers(min_value=-100, max_value=100).map(str),
    st.booleans().map(lambda b: "true" if b else "false"),
    st.just("null"),
)

@st.composite
def tags_array(draw):
    length = draw(st.integers(min_value=0, max_value=5))
    # To maximize divergence, sometimes all strings, sometimes mixed
    # 50% chance all strings, else mixed
    all_strings = draw(st.booleans())
    if all_strings:
        elems = [draw(st.text(min_size=0, max_size=10)).map(json_string_escape) for _ in range(length)]
        # elems is list of strings, but we need JSON string literals
        # Actually elems are strings, so map to JSON string literals
        elems = [draw(st.text(min_size=0, max_size=10)) for _ in range(length)]
        elems = ['"' + json_string_escape(e) + '"' for e in elems]
    else:
        elems = [draw(tags_element) for _ in range(length)]
    return '[' + ','.join(elems) + ']'

# Compose "status" field values:
# Valid enum strings: "active", "inactive", "unknown"
# Invalid strings to cause Moshi, kotlinx, Jackson reject but Gson accept with null
# Also test null (only Gson accepts null for status)
status_valid = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
status_invalid = st.sampled_from(['"Active"', '"INACTIVE"', '"unkown"', '"disabled"', '"null"', '"123"', '123', 'null'])
status_null = st.just('null')

@st.composite
def status_field(draw):
    # 70% valid, 15% invalid string, 15% null
    choice = draw(st.floats(min_value=0, max_value=1))
    if choice < 0.7:
        return draw(status_valid)
    elif choice < 0.85:
        return draw(status_invalid)
    else:
        return 'null'

# Compose "id" field values:
# Accept integer or string convertible to integer
# Also try string non-integer to cause rejection
id_int = st.integers(min_value=0, max_value=10000).map(str)
id_str_int = st.integers(min_value=0, max_value=10000).map(lambda i: '"' + str(i) + '"')
id_str_nonint = st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()).map(lambda s: '"' + json_string_escape(s) + '"')

@st.composite
def id_field(draw):
    choice = draw(st.floats(min_value=0, max_value=1))
    if choice < 0.4:
        return draw(id_int)
    elif choice < 0.8:
        return draw(id_str_int)
    else:
        return draw(id_str_nonint)

# Compose "amount" field values:
# Gson, Moshi, Jackson accept string or number (converted to string)
# kotlinx rejects number
amount_str = st.text(min_size=0, max_size=10).map(lambda s: '"' + json_string_escape(s) + '"')
amount_num = st.one_of(
    st.integers(min_value=-10000, max_value=10000).map(str),
    st.floats(min_value=-10000, max_value=10000).filter(lambda f: not (f != f or f == float('inf') or f == float('-inf'))).map(lambda f: repr(f))
)

@st.composite
def amount_field(draw):
    # 50% string, 50% number
    if draw(st.booleans()):
        return draw(amount_str)
    else:
        return draw(amount_num)

# Compose "name" field values:
# Gson, Jackson accept string, number, boolean (converted to string)
# Moshi, kotlinx accept only string or null
# All accept null
name_str = st.text(min_size=0, max_size=10).map(lambda s: '"' + json_string_escape(s) + '"')
name_num = st.one_of(
    st.integers(min_value=-10000, max_value=10000).map(str),
    st.floats(min_value=-10000, max_value=10000).filter(lambda f: not (f != f or f == float('inf') or f == float('-inf'))).map(lambda f: repr(f))
)
name_bool = st.booleans().map(lambda b: "true" if b else "false")
name_null = st.just("null")

@st.composite
def name_field(draw):
    choice = draw(st.floats(min_value=0, max_value=1))
    if choice < 0.5:
        # string or null (50%)
        if draw(st.booleans()):
            return draw(name_str)
        else:
            return "null"
    elif choice < 0.75:
        # number or boolean (25%)
        if draw(st.booleans()):
            return draw(name_num)
        else:
            return draw(name_bool)
    else:
        # null (25%)
        return "null"

# Compose "child" field values:
# null or nested record (one level recursion)
# Empty object accepted only by Gson, rejected by others
# Nested child with invalid enum or null status triggers divergence
# Nested child with numeric amount triggers divergence with kotlinx
# We'll limit recursion depth to 1 (child's child is always null)
@st.composite
def child_field(draw):
    # 50% null, 50% nested record
    if draw(st.booleans()):
        return "null"
    else:
        # Compose nested record with depth=1, child's child is null
        nested = draw(record_json(depth=1))
        return nested

# Compose a record JSON string with bounded recursion depth
@st.composite
def record_json(draw, depth=0):
    # id
    idv = draw(id_field())
    # amount
    amountv = draw(amount_field())
    # name
    namev = draw(name_field())
    # status
    statusv = draw(status_field())
    # tags
    tagsv = draw(tags_array())
    # child
    if depth >= 1:
        childv = "null"
    else:
        # 50% chance empty object child (to test empty object acceptance)
        if draw(st.booleans()):
            childv = "{}"
        else:
            childv = draw(child_field())
    # Compose JSON object string
    # Fields always present, order fixed
    json_obj = (
        '{'
        + '"id":' + idv + ','
        + '"amount":' + amountv + ','
        + '"name":' + namev + ','
        + '"status":' + statusv + ','
        + '"tags":' + tagsv + ','
        + '"child":' + childv
        + '}'
    )
    return json_obj

@st.composite
def generated_json(draw) -> bytes:
    s = draw(record_json())
    return s.encode("utf-8")