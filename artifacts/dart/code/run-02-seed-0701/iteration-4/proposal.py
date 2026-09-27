from hypothesis import strategies as st

# Helper: JSON string literal with proper escaping of backslash and double quote
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote and control chars minimally
    # Hypothesis strings are unicode, but JSON strings must escape control chars
    # We'll escape backslash, double quote, and control chars < 0x20
    def esc_char(c):
        o = ord(c)
        if c == '\\':
            return '\\\\'
        if c == '"':
            return '\\"'
        if o < 0x20:
            # Use \u00XX escape
            return '\\u%04x' % o
        return c
    return '"' + ''.join(esc_char(c) for c in s) + '"'


# Compose a JSON string literal strategy from Hypothesis text
json_string = st.text(
    alphabet=st.characters(
        blacklist_characters=['\\', '"', '\b', '\f', '\n', '\r', '\t'],
        min_codepoint=0x20,
        max_codepoint=0x10FFFF,
    ),
    min_size=0,
    max_size=20,
).map(json_string_literal)


# JSON number literal for int or float (only integral floats allowed for some)
# We produce integral floats like "1.0" to trigger manual rejection but others accept
# Also produce integers as plain digits
json_int = st.integers(min_value=-(2**31), max_value=2**31-1).map(str)
json_integral_float = st.integers(min_value=-(2**31), max_value=2**31-1).map(lambda i: f"{i}.0")

# JSON string for amount (must be string, no coercion)
# Use strings that look like numbers or arbitrary strings
amount_string = st.one_of(
    st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'], max_codepoint=0x10FFFF)).map(json_string_literal),
    # Also some numeric strings
    st.integers(min_value=0, max_value=9999999).map(lambda i: json_string_literal(str(i))),
)

# status enum exact strings
status_values = st.sampled_from(['active', 'inactive', 'unknown'])

# tags: non-empty array of strings (all implementations reject missing or null tags)
# We produce arrays with all strings, but sometimes inject a non-string element to cause rejection
# But to maximize divergence, mostly produce valid tags arrays with strings
tags_string = st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'], max_codepoint=0x10FFFF)).map(json_string_literal)
tags_array_valid = st.lists(tags_string, min_size=1, max_size=5).map(lambda lst: '[' + ','.join(lst) + ']')

# Occasionally produce tags with one non-string element (number or null) to cause rejection
tags_array_one_bad = st.lists(tags_string, min_size=0, max_size=4).flatmap(
    lambda lst: st.one_of(
        st.just(lst + ['123']),  # number as string literal "123" is string, so no
        st.just(lst + ['null']),  # literal null string is string, no
        # Instead inject a JSON number literal without quotes to cause rejection
        st.just(lst + ['123']),  # but 123 without quotes is number, so we must build it differently
    )
)
# But we cannot produce invalid JSON by mixing string literals and raw numbers in the same list easily here
# So we produce only valid tags arrays with strings to avoid all rejecting identically

# name: string or null or missing (missing treated as null by all)
# built_value omits null name on serialization but accepts null if present
# We produce name present with null, present with string, or missing
name_string = st.one_of(json_string, st.just('null'))
name_present = st.one_of(name_string, json_string)
name_field = st.one_of(
    name_present.map(lambda v: f'"name":{v}'),
    st.just(''),  # missing name field
)

# child: null or nested record or missing (missing treated as null)
# built_value requires null or valid BvRecord if present
# If child present but not object/map, all reject
# We produce child as null, missing, or nested record (one level recursion)
# To avoid infinite recursion, limit depth to 1

# Forward declaration for record string (to allow recursion)
def record_json(depth=0):
    # id: int or integral float (to cause manual rejection)
    # We produce either int or integral float for id to cause divergence
    id_field = st.one_of(json_int, json_integral_float).map(lambda v: f'"id":{v}')

    # amount: string (no coercion)
    amount_field = amount_string.map(lambda v: f'"amount":{v}')

    # status: exact enum string
    status_field = status_values.map(lambda v: f'"status":"{v}"')

    # tags: always present, array of strings (valid)
    tags_field = tags_array_valid.map(lambda v: f'"tags":{v}')

    # name: string or null or missing
    # To maximize divergence, sometimes omit name, sometimes present null, sometimes string
    name_field_local = st.one_of(
        name_string.map(lambda v: f'"name":{v}'),
        st.just(''),  # missing
    )

    # child: null, missing, or nested record (only if depth == 0)
    if depth == 0:
        # child present with null or nested record
        child_null = st.just('"child":null')
        child_missing = st.just('')
        child_nested = record_json(depth=1).map(lambda v: f'"child":{v}')
        child_field = st.one_of(child_null, child_missing, child_nested)
    else:
        # depth 1: child must be null or missing (no further nesting)
        child_field = st.one_of(st.just('"child":null'), st.just(''))

    # Compose fields, always include id, amount, status, tags
    # name and child may be missing (empty string)
    # To maximize divergence, sometimes omit name or child fields
    fields = st.tuples(id_field, amount_field, name_field_local, status_field, tags_field, child_field)

    def build_obj(fields):
        id_f, amount_f, name_f, status_f, tags_f, child_f = fields
        # Filter out empty strings (missing fields)
        parts = [id_f, amount_f]
        if name_f != '':
            parts.append(name_f)
        parts.append(status_f)
        parts.append(tags_f)
        if child_f != '':
            parts.append(child_f)
        return '{' + ','.join(parts) + '}'

    return fields.map(build_obj)

@st.composite
def generated_json(draw) -> bytes:
    # Draw a record JSON string with depth 0
    s = draw(record_json(depth=0))
    # Return bytes
    return s.encode('utf-8')