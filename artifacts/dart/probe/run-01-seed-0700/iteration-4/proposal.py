from hypothesis import strategies as st

# Helper: JSON string escaping for Hypothesis-generated strings
def json_string_escape(s: str) -> str:
    # Minimal escaping for JSON strings: backslash, quote, control chars
    # Hypothesis strings won't have control chars by default, but escape anyway
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    # Escape control chars (U+0000 to U+001F)
    def esc_char(c):
        o = ord(c)
        if o < 0x20:
            return '\\u%04x' % o
        return c
    return ''.join(esc_char(c) for c in s)

# Compose a JSON string literal from a Hypothesis string
def json_string(draw, base_strat=st.text(min_size=0, max_size=10)):
    s = draw(base_strat)
    return '"' + json_string_escape(s) + '"'

# Compose a JSON array of strings
def json_array_of_strings(draw, min_size=0, max_size=5):
    arr = draw(st.lists(st.text(min_size=0, max_size=10), min_size=min_size, max_size=max_size))
    # Escape each string and join with commas
    escaped = [json_string_escape(x) for x in arr]
    return '[' + ','.join('"' + e + '"' for e in escaped) + ']'

# Compose a JSON enum value for "status"
def json_status(draw):
    # Known valid enum values
    valid = ["active", "inactive", "unknown"]
    # We will sometimes produce invalid enum to test rejection, but only one at a time
    # Strategy will be to produce mostly valid, sometimes invalid
    # But since the prompt says to produce only syntactically valid JSON,
    # we can produce invalid enum strings as strings, e.g. "enabled"
    # We'll produce mostly valid, occasionally invalid
    # But to maximize divergence, produce invalid only rarely
    # Here, we produce only valid, invalid can be injected by fuzzing later
    return draw(st.sampled_from(valid))

# Compose a JSON scalar integer for "id"
def json_id(draw):
    # id is integer, but to test boundaries, produce integers in a range
    # We avoid floats or strings here, as type mismatches are rejected uniformly
    return str(draw(st.integers(min_value=0, max_value=10000)))

# Compose a JSON scalar string for "amount"
def json_amount(draw):
    # amount is string, but to test boundaries, produce strings that look like numbers or empty
    # but always strings
    s = draw(st.one_of(
        st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])),
        st.just("0"),
        st.just("123.45"),
        st.just("-99"),
        st.just(""),
    ))
    return '"' + json_string_escape(s) + '"'

# Compose a JSON scalar string or null for "name"
def json_name(draw):
    # nullable string
    if draw(st.booleans()):
        return "null"
    else:
        return json_string(draw)

# Compose a JSON array of strings for "tags"
def json_tags(draw):
    # array of strings, length 0 to 5
    return json_array_of_strings(draw, min_size=0, max_size=5)

# Compose a JSON "child" field: either null or a nested record (one level only)
# To avoid infinite recursion, we only nest once
def json_child(draw):
    if draw(st.booleans()):
        return "null"
    else:
        # Compose a nested record with no further nesting (child=null)
        # Use mostly valid fields, but allow one subtle divergence:
        # e.g. sometimes omit a field (to test missing fields), or
        # sometimes put a wrong enum value in child.status (to test enum rejection)
        # But prompt says all six fields always present in well-formed documents,
        # so missing fields is malformed and rejected by all uniformly.
        # Instead, produce subtle type or enum errors in child sometimes.
        # But prompt says nested errors cause uniform rejection.
        # So to maximize divergence, produce a valid child record always.
        # We can produce a valid child record with a slight tweak: e.g. duplicate keys in child?
        # But duplicates in nested scalar fields cause rejection uniformly.
        # So produce a valid child record with normal fields.
        # To maximize chance of divergence, we can produce a child with "name": null or string,
        # "status" always valid enum.
        # We do not produce duplicate keys here to avoid uniform rejection.
        id_ = json_id(draw)
        amount = json_amount(draw)
        name = json_name(draw)
        status = json_status(draw)
        tags = json_tags(draw)
        child = "null"  # no further nesting
        # Compose child record JSON object string
        return (
            '{'
            + '"id":' + id_ + ','
            + '"amount":' + amount + ','
            + '"name":' + name + ','
            + '"status":' + '"' + status + '"' + ','
            + '"tags":' + tags + ','
            + '"child":' + child
            + '}'
        )

@st.composite
def generated_json(draw) -> bytes:
    # Compose a top-level record with all six fields always present
    # Mostly well-formed, but with one subtle divergence possibility:
    # - For "status", sometimes produce invalid enum to cause rejection divergence
    # - For "name" and "child", produce null or string/object as allowed
    # - For "tags", produce array of strings
    # - For "id" and "amount", produce correct types only (to avoid uniform rejection)
    # - Introduce one subtle divergence by sometimes producing duplicate keys for "tags"
    #   or "name" or "status" to test duplicate key handling differences.
    # But prompt says duplicate keys in nested scalar fields cause uniform rejection,
    # so avoid that at top-level.
    # Instead, produce a valid JSON object with one field subtly off:
    # e.g. "status" with invalid enum string sometimes.
    # Or "tags" with empty array or array with empty strings.
    # Or "name" null or string.
    # Or "child" null or nested record.
    # We'll produce mostly valid, but sometimes invalid enum for "status" to test divergence.
    # Also, produce "amount" as string but sometimes empty string.
    # We produce only syntactically valid JSON.

    # Decide if status is valid or invalid enum
    valid_statuses = ["active", "inactive", "unknown"]
    invalid_statuses = ["enabled", "disabled", "pending", ""]  # invalid enum strings

    # 80% chance valid, 20% invalid to maximize divergence chances
    if draw(st.booleans()):
        status_val = draw(st.sampled_from(valid_statuses))
    else:
        status_val = draw(st.sampled_from(invalid_statuses))

    # Compose fields
    id_ = json_id(draw)
    amount = json_amount(draw)
    name = json_name(draw)
    tags = json_tags(draw)
    child = json_child(draw)

    # Compose JSON object string
    # All keys in double quotes, colon, value, commas between fields
    # Fields order fixed for consistency
    json_obj = (
        '{'
        + '"id":' + id_ + ','
        + '"amount":' + amount + ','
        + '"name":' + name + ','
        + '"status":' + '"' + status_val + '"' + ','
        + '"tags":' + tags + ','
        + '"child":' + child
        + '}'
    )
    return json_obj.encode("utf-8")