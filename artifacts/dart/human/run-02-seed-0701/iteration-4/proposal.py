from hypothesis import strategies as st

# Helper: JSON string escaping for a limited subset (no control chars, no escapes needed)
# We'll restrict to ASCII letters/digits/spaces and a few punctuation marks safe in JSON strings.
_json_string_chars = st.characters(
    whitelist_categories=('Ll', 'Lu', 'Nd', 'Zs'),
    whitelist_characters=' -_.,'
)

_json_string = _json_string_chars.filter(lambda s: s not in ['\\', '"']).map(lambda s: s)

# JSON string with quotes
def json_string(draw):
    # Generate a short string (0-10 chars) of safe chars
    s = draw(st.text(_json_string_chars, min_size=0, max_size=10))
    # Escape double quotes and backslashes minimally (none allowed here)
    # We do not allow these chars, so no escaping needed
    return '"' + s + '"'

# JSON array of strings
def json_string_array(draw, min_len=0, max_len=5):
    arr = draw(st.lists(_json_string, min_size=min_len, max_size=max_len))
    # Compose JSON array text
    return '[' + ','.join('"' + s + '"' for s in arr) + ']'

# JSON null or a nested record (one level recursion)
# We'll implement bounded recursion by passing depth parameter
def json_record(draw, depth=0):
    # Compose fields:
    # "id": int or double (to trigger divergence on id decoding)
    # "amount": string (always present)
    # "name": string or null (nullable)
    # "status": one of "active", "inactive", "unknown"
    # "tags": array of strings or missing (to trigger built_value vs others)
    # "child": null or nested record (one level recursion only)
    # We produce a dict of field texts, then join with commas.

    # id: sometimes int, sometimes double (to trigger divergence)
    # We pick int in 64-bit range or double outside 64-bit range
    id_choice = draw(st.integers(min_value=0, max_value=1))
    if id_choice == 0:
        # true int in 64-bit range
        id_val = draw(st.integers(min_value=-(2**53), max_value=2**53))
        id_text = str(id_val)
    else:
        # double outside 64-bit int range, e.g. 2^63 + fractional
        # jsonDecode will parse this as double, manual and built_value reject, others accept
        # Use a double literal with fractional part to ensure double
        base = 2**63
        frac = draw(st.floats(min_value=0.1, max_value=0.9))
        id_val = base + frac
        # Format as JSON number with decimal point
        id_text = f"{id_val:.6f}"

    # amount: string, non-null
    amount_val = draw(st.text(min_size=1, max_size=10))
    # Escape quotes and backslashes minimally (none allowed)
    amount_val = amount_val.replace('\\', '\\\\').replace('"', '\\"')
    amount_text = '"' + amount_val + '"'

    # name: string or null
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_text = "null"
    else:
        name_val = draw(st.text(min_size=0, max_size=10))
        name_val = name_val.replace('\\', '\\\\').replace('"', '\\"')
        name_text = '"' + name_val + '"'

    # status: one of "active", "inactive", "unknown"
    status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
    status_text = '"' + status_val + '"'

    # tags: array of strings or missing (to trigger built_value vs others)
    tags_present = draw(st.booleans())
    if tags_present:
        # array of 0-3 strings
        tags_list = draw(st.lists(st.text(min_size=0, max_size=5).filter(lambda s: '"' not in s and '\\' not in s), max_size=3))
        tags_text = '[' + ','.join('"' + t + '"' for t in tags_list) + ']'
    else:
        tags_text = None  # missing field

    # child: null or nested record (one level recursion only)
    if depth == 0:
        child_is_null = draw(st.booleans())
        if child_is_null:
            child_text = "null"
        else:
            # nested record with depth=1, no further recursion
            child_text = json_record(draw, depth=1)
    else:
        # depth=1, no further recursion, child must be null
        child_text = "null"

    # Compose fields as JSON object text
    # Fields order: id, amount, name, status, tags?, child
    fields = []
    fields.append('"id":' + id_text)
    fields.append('"amount":' + amount_text)
    fields.append('"name":' + name_text)
    fields.append('"status":' + status_text)
    if tags_text is not None:
        fields.append('"tags":' + tags_text)
    # else omit tags field to trigger divergence
    fields.append('"child":' + child_text)

    obj_text = '{' + ','.join(fields) + '}'
    return obj_text

@st.composite
def generated_json(draw) -> bytes:
    # Generate one top-level record JSON text
    json_text = json_record(draw, depth=0)
    # Return as bytes (utf-8)
    return json_text.encode('utf-8')