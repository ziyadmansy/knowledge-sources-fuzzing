from hypothesis import strategies as st

# Helper: JSON string escaping for Hypothesis-generated strings
def json_string(s: str) -> str:
    # Minimal escaping for JSON string output:
    # Escape backslash, double quote, and control chars \b \f \n \r \t
    # Hypothesis strings won't contain control chars by default, but be safe.
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    s = s.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return '"' + s + '"'

# Compose JSON text for a string value from Hypothesis string
json_str = st.text(min_size=0, max_size=20).map(json_string)

# Compose JSON text for an integer literal (decimal, no quotes)
# We want to produce integers in and out of 64-bit range to trigger differences
# 64-bit signed int range: -2**63 .. 2**63-1
# We'll produce some in range, some just out of range, and some doubles that jsonDecode will parse as double.
int64_min = -(2**63)
int64_max = 2**63 - 1

# Produce integer literals as strings, sometimes out of 64-bit range
int_literal = st.one_of(
    st.integers(min_value=int64_min, max_value=int64_max).map(str),
    # Out of 64-bit range, but still integer literal (will be parsed as double by jsonDecode)
    st.integers(min_value=int64_min - 10**6, max_value=int64_min - 1).map(str),
    st.integers(min_value=int64_max + 1, max_value=int64_max + 10**6).map(str),
)

# Produce a JSON number literal that is either an integer or a double with .0 suffix
# This is to test the difference between manual/built_value (require int) and json_serializable/freezed (accept double.toInt())
json_number_literal = st.one_of(
    int_literal,
    # doubles that represent integers but parsed as double by jsonDecode
    st.integers(min_value=int64_min, max_value=int64_max).map(lambda i: str(i) + ".0"),
)

# Produce JSON array of strings text, e.g. ["a","b","c"]
# We want to produce arrays of strings, possibly empty.
json_array_of_strings = st.lists(json_str, min_size=0, max_size=5).map(
    lambda lst: "[" + ",".join(lst) + "]"
)

# Produce JSON null literal text
json_null = st.just("null")

# Produce JSON enum "status" string literal: one of "active", "inactive", "unknown"
json_status = st.sampled_from(['"active"', '"inactive"', '"unknown"'])

# Produce JSON string or null for "name"
json_name = st.one_of(json_str, json_null)

# Forward declaration for recursion: record text
# We'll define a recursive strategy with bounded depth (max 1 level of recursion for "child")

@st.composite
def json_record(draw, depth=0):
    # id: integer or double number literal (to test int vs double acceptance)
    id_val = draw(json_number_literal)

    # amount: string (non-null)
    amount_val = draw(json_str)

    # name: string or null
    name_val = draw(json_name)

    # status: one of enum strings
    status_val = draw(json_status)

    # tags: array of strings or missing (to test built_value accepting missing tags)
    # We produce either present tags (array) or missing tags (omit field)
    # To maximize disagreement, produce mostly present tags, sometimes missing
    tags_present = draw(st.booleans())
    if tags_present:
        tags_val = draw(json_array_of_strings)
    else:
        tags_val = None  # omit field

    # child: null or nested record (only one level recursion)
    if depth == 0:
        # 50% chance null, 50% chance nested record with depth=1
        child_present = draw(st.booleans())
        if child_present:
            child_val = draw(json_record(depth=1))
        else:
            child_val = "null"
    else:
        # At depth 1, only null allowed (no further recursion)
        child_val = "null"

    # Compose fields as JSON text key:value pairs
    # We must produce a syntactically valid JSON object text

    # Compose fields list
    fields = []

    # id field (required)
    fields.append('"id":' + id_val)

    # amount field (required)
    fields.append('"amount":' + amount_val)

    # name field (nullable)
    fields.append('"name":' + name_val)

    # status field (required)
    fields.append('"status":' + status_val)

    # tags field (optional)
    if tags_val is not None:
        fields.append('"tags":' + tags_val)

    # child field (nullable)
    fields.append('"child":' + child_val)

    # Shuffle fields order to avoid bias (optional)
    # Hypothesis does not provide shuffle for lists, but we can do a random permutation by sorting by a random key
    # Draw a list of floats for sorting keys
    sort_keys = draw(st.lists(st.floats(min_value=0, max_value=1), min_size=len(fields), max_size=len(fields)))
    fields_sorted = [f for _, f in sorted(zip(sort_keys, fields))]

    # Compose JSON object text
    obj_text = "{" + ",".join(fields_sorted) + "}"

    return obj_text

@st.composite
def generated_json(draw) -> bytes:
    # Draw a record JSON text
    text = draw(json_record())

    # Return as UTF-8 bytes
    return text.encode("utf-8")