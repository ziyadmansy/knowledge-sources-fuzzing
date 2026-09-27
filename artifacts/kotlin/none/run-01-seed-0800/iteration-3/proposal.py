from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (quote, backslash, control chars)
def json_string_escape(s: str) -> str:
    # Escape backslash and quote, and control chars \b \f \n \r \t
    # We only generate strings from limited char sets so this is enough.
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    s = s.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return s

# Strategy for JSON string literal (quoted, escaped)
json_string = st.text(
    alphabet=st.characters(
        blacklist_characters=['\\', '"', '\b', '\f', '\n', '\r', '\t'],
        min_codepoint=0x20,
        max_codepoint=0x7E,
    ),
    min_size=0,
    max_size=20,
).map(json_string_escape).map(lambda s: '"' + s + '"')

# Strategy for JSON null literal
json_null = st.just("null")

# Strategy for JSON boolean literal (not used in schema but useful for divergence)
json_bool = st.sampled_from(["true", "false"])

# Strategy for JSON integer literal (for "id")
# We produce integers as strings of digits, no leading zeros except zero itself
json_int = st.integers(min_value=0, max_value=2_000_000_000).map(str)

# Strategy for "amount" field: string, but try numeric-like strings and some edge cases
# We want to test strings that look like numbers, empty string, or weird strings
amount_string = st.one_of(
    # Numeric strings (integer or decimal)
    st.integers(min_value=0, max_value=1_000_000).map(str),
    st.floats(min_value=0, max_value=1_000_000, allow_infinity=False, allow_nan=False).map(lambda f: format(f, 'f').rstrip('0').rstrip('.') if '.' in format(f, 'f') else format(f, 'f')),
    st.just(""),  # empty string
    json_string,  # arbitrary string
).map(lambda s: s if s.startswith('"') else '"' + s + '"')

# Strategy for "name": string or null
name_field = st.one_of(json_null, json_string)

# Strategy for "status": one of "active", "inactive", "unknown"
status_values = ['"active"', '"inactive"', '"unknown"']
status_field = st.sampled_from(status_values)

# Strategy for "tags": array of strings (0 to 5 strings)
tags_field = st.lists(json_string, min_size=0, max_size=5).map(
    lambda lst: "[" + ",".join(lst) + "]"
)

# Forward declaration for child record (nullable)
# We'll define generated_json_record below and use it recursively with bounded depth

def generated_json_record(max_depth: int):
    if max_depth <= 0:
        # At max depth, child is always null
        child_field = json_null
    else:
        # child is either null or a nested record with one less depth
        child_field = st.one_of(json_null, generated_json_record(max_depth - 1))

    # To create divergence, we will sometimes produce subtle type errors or missing fields
    # But mostly produce well-formed fields with one or two small deviations

    # id field: integer as number or as string (to cause divergence)
    id_field = st.one_of(
        json_int,  # number as string (e.g. "123")
        json_string,  # number as string literal (e.g. "\"123\"")
        # Also try a number with leading zeros (invalid JSON number but accepted as string)
        st.integers(min_value=0, max_value=9999).map(lambda i: '"' + str(i).rjust(4, '0') + '"'),
    )

    # amount field: string, but sometimes a number literal (to cause divergence)
    amount_field = st.one_of(
        amount_string,
        # number literal (unquoted)
        st.floats(min_value=0, max_value=1_000_000, allow_infinity=False, allow_nan=False).map(lambda f: format(f, 'f').rstrip('0').rstrip('.') if '.' in format(f, 'f') else format(f, 'f')),
        # empty string quoted
        st.just('""'),
    )

    # name field: string or null, sometimes number or boolean to cause divergence
    name_field_div = st.one_of(
        name_field,
        json_int,
        json_bool,
    )

    # status field: correct enum string or wrong string or null or number to cause divergence
    status_field_div = st.one_of(
        status_field,
        json_string,
        json_null,
        json_int,
    )

    # tags field: array of strings or array of numbers or null or empty string (wrong type)
    tags_field_div = st.one_of(
        tags_field,
        # array of numbers
        st.lists(json_int, min_size=0, max_size=5).map(lambda lst: "[" + ",".join(lst) + "]"),
        json_null,
        st.just('""'),
    )

    # child field: either null or nested record or wrong type (string, number)
    child_field_div = st.one_of(
        child_field,
        json_string,
        json_int,
        json_null,
    )

    # Compose fields as JSON object string with fields in fixed order
    def compose_record(fields):
        # fields is dict of fieldname: json text
        # Compose JSON object string with commas
        parts = []
        for k in ["id", "amount", "name", "status", "tags", "child"]:
            parts.append('"' + k + '":' + fields[k])
        return "{" + ",".join(parts) + "}"

    return st.fixed_dictionaries({
        "id": id_field,
        "amount": amount_field,
        "name": name_field_div,
        "status": status_field_div,
        "tags": tags_field_div,
        "child": child_field_div,
    }).map(compose_record)

@st.composite
def generated_json(draw) -> bytes:
    # Generate a record with max recursion depth 1 (one level child)
    # This matches the schema description: one level of recursion normally
    record_text = draw(generated_json_record(1))
    # Return bytes (UTF-8)
    return record_text.encode("utf-8")