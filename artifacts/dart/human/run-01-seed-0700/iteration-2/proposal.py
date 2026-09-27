from hypothesis import strategies as st

# Helper: JSON string literal with proper escaping of " and \ only (minimal)
def json_string(s: str) -> str:
    # Escape backslash and double quote
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings
def json_string_array(strs):
    return '[' + ','.join(json_string(s) for s in strs) + ']'

# Helper: JSON null literal
json_null = "null"

# Helper: JSON boolean literal (not used here but could be)
json_true = "true"
json_false = "false"

# Helper: JSON number literal from int or float
def json_number(n):
    # For int, just str
    # For float, use repr to get decimal notation
    if isinstance(n, int):
        return str(n)
    else:
        # Use repr to get a JSON-compatible float literal (e.g. 1.0, 1e10)
        return repr(n)

# Strategy for "status" field: one of "active", "inactive", "unknown"
status_values = st.sampled_from(["active", "inactive", "unknown"])

# Strategy for "name": string or null
# Use simple ASCII strings without control chars or quotes to simplify escaping
name_values = st.one_of(st.none(), st.text(alphabet=st.characters(blacklist_characters=['"', '\\', '\n', '\r']), min_size=0, max_size=10))

# Strategy for "tags": array of strings
tags_values = st.lists(st.text(alphabet=st.characters(blacklist_characters=['"', '\\', '\n', '\r']), min_size=0, max_size=10), max_size=5)

# Strategy for "id": integers or doubles near int64 boundaries to exploit known differences
# int64 range: -9223372036854775808 to 9223372036854775807
# We'll generate:
# - valid int64 ints
# - integers outside int64 range (to be encoded as double by jsonDecode)
# - doubles that are integral but outside int64 range
# - doubles that are fractional (should be rejected by manual and built_value)
id_int64_min = -9223372036854775808
id_int64_max = 9223372036854775807

# Generate id as either:
# - int in int64 range
# - int just below int64 min (to be double)
# - int just above int64 max (to be double)
# - float integral outside int64 range
# - float fractional inside int64 range
id_strategy = st.one_of(
    st.integers(min_value=id_int64_min, max_value=id_int64_max),
    st.just(id_int64_min - 1),
    st.just(id_int64_max + 1),
    st.floats(min_value=id_int64_min - 1000, max_value=id_int64_min - 0.1, allow_infinity=False, allow_nan=False).filter(lambda f: f.is_integer()),
    st.floats(min_value=id_int64_max + 0.1, max_value=id_int64_max + 1000, allow_infinity=False, allow_nan=False).filter(lambda f: f.is_integer()),
    st.floats(min_value=id_int64_min, max_value=id_int64_max, allow_infinity=False, allow_nan=False).filter(lambda f: not f.is_integer()),
)

# Strategy for "amount": string, but also try some edge cases that might confuse parsers
# Use decimal-looking strings, empty string, or strings with spaces
amount_strategy = st.one_of(
    st.text(alphabet=st.characters(blacklist_characters=['"', '\\', '\n', '\r']), min_size=1, max_size=10),
    st.just(""),  # empty string
    st.just(" 123 "),  # spaces around digits
    st.just("0"),
    st.just("-0"),
    st.just("1.23"),
)

# Strategy for "child": either null or a nested record (one level only)
# To avoid infinite recursion, child record will have child=null always
# We'll reuse the main record strategy but with child=null forced
@st.composite
def child_record(draw):
    # id, amount, name, status, tags, child=null
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_values)
    status_val = draw(status_values)
    tags_val = draw(tags_values)
    # Compose JSON text for child record
    # All fields present always (except child=null)
    parts = [
        '"id":' + json_number(id_val),
        '"amount":' + json_string(amount_val),
        '"name":' + (json_null if name_val is None else json_string(name_val)),
        '"status":' + json_string(status_val),
        '"tags":' + json_string_array(tags_val),
        '"child":null'
    ]
    return '{' + ','.join(parts) + '}'

# Main record strategy with optional child (null or nested)
@st.composite
def record(draw):
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_values)
    status_val = draw(status_values)
    tags_val = draw(tags_values)

    # Decide if child is null or nested
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json = "null"
    else:
        child_json = draw(child_record())

    # Compose JSON text for main record
    parts = [
        '"id":' + json_number(id_val),
        '"amount":' + json_string(amount_val),
        '"name":' + (json_null if name_val is None else json_string(name_val)),
        '"status":' + json_string(status_val),
        '"tags":' + json_string_array(tags_val),
        '"child":' + child_json
    ]
    return '{' + ','.join(parts) + '}'

# Strategy to produce documents with one subtle deviation to provoke divergence:
# - Sometimes omit "tags" field (to trigger built_value accepting but others rejecting)
# - Sometimes replace a field with wrong type or null where non-nullable
# - Sometimes use out-of-range id as double
# - Sometimes use fractional id double
# - Sometimes use unknown status string (should be rejected by all)
# - Sometimes use missing nullable fields (name or child) (should be accepted by all)
# We'll produce mostly valid documents with one small deviation.

@st.composite
def generated_json(draw) -> bytes:
    # Base record fields
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_values)
    status_val = draw(status_values)
    tags_val = draw(tags_values)
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json = "null"
    else:
        child_json = draw(child_record())

    # Start with all fields present
    fields = {
        "id": json_number(id_val),
        "amount": json_string(amount_val),
        "name": (json_null if name_val is None else json_string(name_val)),
        "status": json_string(status_val),
        "tags": json_string_array(tags_val),
        "child": child_json,
    }

    # Choose one deviation type or none (mostly none to keep valid)
    deviation = draw(st.sampled_from([
        "omit_tags",           # omit tags field (built_value accepts, others reject)
        "tags_wrong_type",     # tags as string instead of array (all reject)
        "id_double_fractional",# id as fractional double inside int64 range (manual,built_value reject, others accept)
        "id_double_out_of_range", # id as double outside int64 range (manual,built_value reject or saturate, others accept)
        "status_unknown",      # unknown status string (all reject)
        "name_missing",        # omit nullable name (all accept)
        "child_missing",       # omit nullable child (all accept)
        "amount_null",         # amount null (non-nullable, all reject)
        "id_null",             # id null (non-nullable, all reject)
        "no_deviation"         # no deviation, all valid
    ]))

    if deviation == "omit_tags":
        # Remove tags field
        del fields["tags"]
    elif deviation == "tags_wrong_type":
        # tags as string (invalid type)
        fields["tags"] = json_string("not-an-array")
    elif deviation == "id_double_fractional":
        # id as fractional double inside int64 range
        # Pick a fractional double in range
        frac_id = draw(st.floats(min_value=id_int64_min, max_value=id_int64_max, allow_infinity=False, allow_nan=False).filter(lambda f: not f.is_integer()))
        fields["id"] = json_number(frac_id)
    elif deviation == "id_double_out_of_range":
        # id as double outside int64 range, fractional or integral
        # Pick either fractional or integral double outside range
        out_of_range_double = draw(st.one_of(
            st.floats(min_value=id_int64_max + 0.1, max_value=id_int64_max + 1000, allow_infinity=False, allow_nan=False),
            st.floats(min_value=id_int64_min - 1000, max_value=id_int64_min - 0.1, allow_infinity=False, allow_nan=False),
        ))
        fields["id"] = json_number(out_of_range_double)
    elif deviation == "status_unknown":
        # status unknown string (not in enum)
        fields["status"] = json_string("not_a_status")
    elif deviation == "name_missing":
        # omit nullable name field
        del fields["name"]
    elif deviation == "child_missing":
        # omit nullable child field
        del fields["child"]
    elif deviation == "amount_null":
        # amount null (non-nullable)
        fields["amount"] = json_null
    elif deviation == "id_null":
        # id null (non-nullable)
        fields["id"] = json_null
    elif deviation == "no_deviation":
        pass

    # Compose JSON object text
    # Fields order fixed for readability
    keys_order = ["id", "amount", "name", "status", "tags", "child"]
    parts = []
    for k in keys_order:
        if k in fields:
            parts.append(f'"{k}":{fields[k]}')
    json_text = '{' + ','.join(parts) + '}'

    # Return bytes
    return json_text.encode("utf-8")