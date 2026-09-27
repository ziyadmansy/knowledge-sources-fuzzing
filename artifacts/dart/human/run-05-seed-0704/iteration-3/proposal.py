from hypothesis import strategies as st

# Constants for the "status" enum strings
STATUS_VALUES = ["active", "inactive", "unknown"]

# Helper to produce a JSON string literal from a Python string (escaping quotes and backslashes)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote
    s = s.replace("\\", "\\\\").replace("\"", "\\\"")
    # Escape control characters minimally (newline, tab, carriage return)
    s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f"\"{s}\""

# Compose JSON array of strings from Python list of strings
def json_array_of_strings(lst):
    # lst is a list of strings
    # map each string to JSON string literal
    items = ",".join(json_string_literal(s) for s in lst)
    return f"[{items}]"

# Compose JSON object from dict of key->json_value (strings already JSON encoded)
def json_object(d):
    # d: dict[str, str]
    items = ",".join(json_string_literal(k) + ":" + v for k, v in d.items())
    return "{" + items + "}"

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the described record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.
    """

    # --- id field ---
    # id must be present and an integer for manual and built_value to accept.
    # json_serializable and freezed accept double that converts to int via toInt().
    # jsonDecode converts large int literals outside 64-bit range into double.
    #
    # Strategy:
    # - Mostly generate int in 64-bit range ([-2**63, 2**63-1])
    # - Occasionally generate a large int literal outside 64-bit range, which jsonDecode
    #   will parse as double, causing manual and built_value to reject, but others accept.
    # - Occasionally generate a double with fractional part to cause all to reject.
    #
    # We'll do this by choosing a "mode" for id:
    # 0: valid int in 64-bit range (accepted by all)
    # 1: large int literal outside 64-bit range (parsed as double by jsonDecode)
    # 2: double with fractional part (all reject)
    id_mode = draw(st.integers(min_value=0, max_value=9))
    if id_mode <= 6:
        # 70% chance: valid int in 64-bit range
        id_val = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
        # Represent as JSON integer literal (no quotes)
        id_json = str(id_val)
    elif id_mode <= 8:
        # 20% chance: large int literal outside 64-bit range (e.g. 2**65)
        # Represent as a numeric literal (no quotes), but too large for 64-bit int
        # This will be parsed by jsonDecode as a double
        large_int = draw(st.one_of(
            st.integers(min_value=2**63, max_value=2**70),
            st.integers(min_value=-(2**70), max_value=-(2**63))
        ))
        id_json = str(large_int)
    else:
        # 10% chance: double with fractional part (all reject)
        # Represent as JSON number with decimal point
        dbl = draw(st.floats(allow_infinity=False, allow_nan=False))
        # Format with decimal point, forcing fractional part
        if dbl == int(dbl):
            dbl = dbl + 0.1
        id_json = repr(dbl)

    # --- amount field ---
    # amount is a string, always present.
    # We can try to provoke divergence by:
    # - Using numeric strings that look like numbers but are strings (should be accepted by all)
    # - Using empty string, or strings with unicode escapes, or control chars
    # - Using null is invalid (all reject)
    #
    # We'll mostly generate normal strings, occasionally empty or numeric strings.
    amount_str = draw(st.one_of(
        st.text(min_size=1, max_size=20),
        st.just(""),  # empty string
        st.integers(min_value=-1000000, max_value=1000000).map(str),
    ))
    amount_json = json_string_literal(amount_str)

    # --- name field ---
    # nullable string, missing or null accepted by all.
    # We'll always include it (to avoid missing field confusion).
    # Occasionally null, occasionally string.
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        # string or empty string
        name_str = draw(st.one_of(
            st.text(min_size=0, max_size=20),
            st.just(""),
        ))
        name_json = json_string_literal(name_str)

    # --- status field ---
    # must be one of "active", "inactive", "unknown"
    # unrecognized string rejected by all.
    # We'll mostly generate valid values.
    # Occasionally generate invalid string to cause all reject (no divergence).
    # To maximize divergence, keep valid.
    status_str = draw(st.sampled_from(STATUS_VALUES))
    status_json = json_string_literal(status_str)

    # --- tags field ---
    # array of strings, always present.
    # Missing tags is accepted only by built_value, rejected by others.
    # To provoke divergence, sometimes omit tags field.
    # Otherwise, generate array of strings.
    omit_tags = draw(st.booleans())
    if omit_tags:
        tags_json = None
    else:
        # Generate array of strings, possibly empty
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
        tags_json = json_array_of_strings(tags_list)

    # --- child field ---
    # nullable Record or null, one level recursion normally.
    # Missing or null accepted by all.
    # We'll sometimes omit, sometimes null, sometimes a nested record.
    # To keep recursion bounded, max depth 1.
    child_choice = draw(st.integers(min_value=0, max_value=2))
    if child_choice == 0:
        # omit child field
        child_json = None
    elif child_choice == 1:
        # child null
        child_json = "null"
    else:
        # child is a nested record, but no further recursion (child.child omitted)
        # We'll generate a minimal valid nested record with fixed values to reduce complexity
        # id: valid int
        child_id = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
        child_id_json = str(child_id)
        # amount: fixed string
        child_amount_json = json_string_literal("child_amount")
        # name: null
        child_name_json = "null"
        # status: fixed valid value
        child_status_json = json_string_literal("unknown")
        # tags: empty array
        child_tags_json = "[]"
        # child.child omitted
        child_fields = {
            "id": child_id_json,
            "amount": child_amount_json,
            "name": child_name_json,
            "status": child_status_json,
            "tags": child_tags_json,
        }
        child_json = json_object(child_fields)

    # Compose top-level object fields
    fields = {
        "id": id_json,
        "amount": amount_json,
        "name": name_json,
        "status": status_json,
    }
    if tags_json is not None:
        fields["tags"] = tags_json
    if child_json is not None:
        fields["child"] = child_json

    # Compose JSON object string
    json_text = json_object(fields)

    # Return bytes
    return json_text.encode("utf-8")