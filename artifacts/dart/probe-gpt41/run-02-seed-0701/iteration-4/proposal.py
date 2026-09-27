from hypothesis import strategies as st

# Helper: JSON string escaping for Hypothesis-generated strings
def json_string(s: str) -> str:
    # Minimal escaping for JSON string: backslash and double quote
    # Also escape control chars \b \f \n \r \t for safety
    # Hypothesis strings are unicode, so also escape other control chars <0x20
    def esc(ch):
        o = ord(ch)
        if ch == '"':
            return r'\"'
        if ch == '\\':
            return r'\\'
        if ch == '\b':
            return r'\b'
        if ch == '\f':
            return r'\f'
        if ch == '\n':
            return r'\n'
        if ch == '\r':
            return r'\r'
        if ch == '\t':
            return r'\t'
        if o < 0x20:
            return '\\u%04x' % o
        return ch
    return '"' + ''.join(esc(c) for c in s) + '"'

# Predefined enum values for "status"
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# We want to produce JSON text bytes, so we build strings and encode later.
# But Hypothesis expects bytes output, so we will return .encode('utf-8') at the end.

# Strategy to produce a valid "id" field value as integer or near-boundary invalid (string)
# But from known probes, type mismatches cause uniform rejection.
# To maximize divergence, we mostly keep "id" as integer (required).
id_strategy = st.integers(min_value=0, max_value=2**31-1).map(str)

# "amount" is string, always present, non-null
# We can try valid strings, or occasionally inject numeric-looking strings or empty strings
amount_strategy = st.text(min_size=1, max_size=10).map(json_string)

# "name" is nullable string or null, missing treated as null by all
# We produce either null or string
name_strategy = st.one_of(st.just("null"), st.text(min_size=0, max_size=10).map(json_string))

# "status" is enum string, no null, no invalid values allowed
# To maximize divergence, we sometimes produce invalid enum strings or null
# But invalid enum always rejected similarly, so we mostly produce valid enum strings
# Occasionally produce null or invalid to trigger different exception types
status_valid = st.sampled_from(STATUS_VALUES)
status_invalid = st.text(min_size=1, max_size=10).filter(lambda s: s.lower() not in {"active","inactive","unknown"})
status_strategy = st.one_of(
    status_valid,
    status_invalid.map(json_string),
    st.just("null"),
)

# "tags" is array of strings, non-null except built_value accepts null as empty list
# To maximize divergence, sometimes produce null, sometimes array of strings
tags_string = st.text(min_size=0, max_size=10).map(json_string)
tags_array = st.lists(tags_string, min_size=0, max_size=5).map(lambda lst: "[" + ",".join(lst) + "]")
tags_strategy = st.one_of(
    st.just("null"),
    tags_array,
)

# "child" is either null or a nested Record (one level recursion)
# To keep recursion bounded, we produce null or a nested record with no further child (child=null)
# We will produce child as null or a record with child=null (depth=1)
# We reuse the record strategy with depth control

# Forward declaration for recursion
def record_strategy(depth=0):
    # depth 0 means top-level, max depth 1 for child
    # Compose fields as JSON text pieces
    # We produce a dict of fields as strings, then join with commas and braces
    # We vary presence of "name" (missing or present), presence of "child" (null or nested)
    # We vary "tags" null or array, "status" valid or invalid, etc.
    # To maximize divergence, we produce mostly well-formed except 1 or 2 fields off.

    # id
    id_val = id_strategy

    # amount
    amount_val = amount_strategy

    # name: present with null or string, or missing (empty)
    # Missing "name" is accepted by all as null, so to maximize divergence we sometimes omit it
    name_present = st.booleans()
    # If present, choose null or string
    name_val = name_strategy

    # status: valid, invalid, or null
    status_val = status_strategy

    # tags: null or array of strings
    tags_val = tags_strategy

    # child: null or nested record (depth+1)
    if depth >= 1:
        # no further recursion, child always null
        child_val = st.just("null")
    else:
        # child null or nested record with depth=1
        child_val = st.one_of(
            st.just("null"),
            record_strategy(depth=depth+1)
        )

    # Compose fields with possible omission of "name"
    # Also, to maximize divergence, sometimes omit "child" or "tags" or "status" (extra fields tolerated)
    # But missing required fields cause uniform rejection, so only omit "name" safely

    # We produce a dict of fieldname -> json text
    # Then join with commas inside {}

    # To maximize divergence, we vary presence of "name" and sometimes produce invalid enum or null status or null tags

    # Compose a strategy that yields dict of fields as strings
    def build_record(id_s, amount_s, name_p, name_s, status_s, tags_s, child_s):
        fields = []
        fields.append('"id":' + id_s)
        fields.append('"amount":' + amount_s)
        if name_p:
            fields.append('"name":' + name_s)
        # status always present (required)
        fields.append('"status":' + status_s)
        # tags always present (required)
        fields.append('"tags":' + tags_s)
        # child always present (required)
        fields.append('"child":' + child_s)
        # Add an extra field sometimes to check tolerance
        # But extra fields do not cause divergence, so optional
        return "{" + ",".join(fields) + "}"

    return st.tuples(id_val, amount_val, name_present, name_val, status_val, tags_val, child_val).map(
        lambda t: build_record(*t)
    )

@st.composite
def generated_json(draw) -> bytes:
    # Draw a record at top-level
    rec = draw(record_strategy(depth=0))
    return rec.encode("utf-8")