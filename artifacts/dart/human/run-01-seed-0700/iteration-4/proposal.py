from hypothesis import strategies as st

# Helper: JSON string with proper escaping for " and \ only (simplified)
# We avoid control chars for simplicity.
json_escaped_char = st.characters(
    blacklist_characters=['\\', '"', '\b', '\f', '\n', '\r', '\t'],
    min_codepoint=0x20,
    max_codepoint=0x7E,
)
json_string = json_escaped_char.filter(lambda c: c not in ['\\', '"']).flatmap(
    lambda first: st.text(json_escaped_char, max_size=10).map(lambda rest: first + rest)
).map(lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"')

# JSON null literal
json_null = st.just("null")

# JSON boolean literals (not used in schema, but useful for fuzzing)
json_bool = st.sampled_from(["true", "false"])

# JSON number literals as strings (to be inserted raw)
# We want to produce numbers that can be int or double representations.
# For id field, we want to test int vs double boundary.
# For amount, it's a string, so we produce JSON strings.

# Produce JSON number literals as strings:
# - integers in 64-bit range
# - integers outside 64-bit range (to become double in jsonDecode)
# - doubles with fractional part
json_int64_min = -(2**63)
json_int64_max = 2**63 - 1

def json_number_str(draw):
    # Choose int or float representation
    kind = draw(st.sampled_from(["int64_in", "int64_out", "double"]))
    if kind == "int64_in":
        # int64 in range
        n = draw(st.integers(min_value=json_int64_min, max_value=json_int64_max))
        return str(n)
    elif kind == "int64_out":
        # int outside int64 range, to become double in jsonDecode
        # Use large integers outside 64-bit range
        # Use positive or negative
        sign = draw(st.sampled_from(["", "-"]))
        base = draw(st.integers(min_value=2**63, max_value=2**70))
        return sign + str(base)
    else:
        # double with fractional part
        # Use decimal notation, no exponent
        whole = draw(st.integers(min_value=0, max_value=10**6))
        frac = draw(st.integers(min_value=1, max_value=999999))
        return f"{whole}.{frac}"

json_number = st.deferred(lambda: st.builds(json_number_str, st.just(None)))

# For "amount" field, which is a string, produce JSON string with numeric or non-numeric content
# We want to test if amount string content affects anything (likely not, but fuzz anyway)
amount_string = json_string

# For "name" field: nullable string or null
name_field = st.one_of(json_null, json_string)

# For "status" field: one of "active", "inactive", "unknown"
# Also try unrecognized strings to confirm rejection (but that won't cause divergence)
status_known = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
status_unknown = json_string.filter(lambda s: s not in ['"active"', '"inactive"', '"unknown"'])
# We want mostly known, but sometimes unknown to test rejection
status_field = st.one_of(status_known, status_unknown)

# For "tags" field: array of strings
# Also test missing tags (built_value accepts, others reject)
# We will produce either present or missing tags field at top level
tags_array = st.lists(json_string, max_size=5).map(lambda lst: "[" + ",".join(lst) + "]")

# For "child" field: nullable Record or null
# We allow one level of recursion only
# To avoid infinite recursion, we define record recursively with max depth 1

@st.composite
def record(draw, allow_missing_tags=False, depth=0):
    # id: int or double (as number literal)
    # We want to produce id as int or double to test divergence
    # Use json_number_str directly here for raw number literal
    id_val = draw(json_number_str())

    # amount: string
    amount_val = draw(amount_string)

    # name: nullable string
    name_val = draw(name_field)

    # status: known or unknown string
    status_val = draw(status_field)

    # tags: present or missing (only missing at top-level or if allow_missing_tags)
    # To maximize divergence, allow missing tags only at top-level (depth=0)
    tags_present = True
    if allow_missing_tags and depth == 0:
        tags_present = draw(st.booleans())
    tags_val = draw(tags_array) if tags_present else None

    # child: null or nested record (depth 0 -> depth 1 max)
    if depth == 0:
        child_val = draw(st.one_of(json_null, record(allow_missing_tags=False, depth=1)))
    else:
        # depth 1: child must be null (no further recursion)
        child_val = draw(json_null)

    # Compose JSON object text manually
    # Fields order: id, amount, name, status, tags (optional), child
    parts = []
    parts.append('"id":' + id_val)
    parts.append('"amount":' + amount_val)
    parts.append('"name":' + name_val)
    parts.append('"status":' + status_val)
    if tags_val is not None:
        parts.append('"tags":' + tags_val)
    parts.append('"child":' + child_val)

    json_obj = "{" + ",".join(parts) + "}"
    return json_obj

@st.composite
def generated_json(draw) -> bytes:
    # Generate a top-level record, allowing missing tags to trigger divergence
    obj_text = draw(record(allow_missing_tags=True, depth=0))
    return obj_text.encode("utf-8")