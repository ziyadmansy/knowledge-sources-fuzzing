from hypothesis import strategies as st

# Constants for the "status" enum strings
STATUS_VALUES = ["active", "inactive", "unknown"]

# Helper to produce JSON string literals with proper escaping of quotes and backslashes
def json_string(s: str) -> str:
    # Minimal escaping for " and \ to keep valid JSON strings
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper to produce JSON arrays of strings
def json_string_array(strings) -> str:
    return "[" + ",".join(json_string(s) for s in strings) + "]"

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, with the given schema:
    {
      "id": <integer or double (to trigger divergence)>,
      "amount": <string>,
      "name": <string or null or missing>,
      "status": <one of "active", "inactive", "unknown" or invalid string (to trigger rejection)>,
      "tags": <array of strings or missing>,
      "child": <nested record or null or missing>
    }
    We vary presence, types, and values to maximize divergence among the four Dart deserializers.
    """

    # --- id field ---
    # id is required and non-nullable.
    # Manual and built_value require a true int.
    # json_serializable and freezed accept num.toInt(), so accept doubles.
    # jsonDecode turns out-of-range int literals into doubles.
    # We produce either:
    # - a true int within 64-bit range (accepted by all)
    # - a double that is an integer value (accepted by all)
    # - a double outside 64-bit int range (accepted by json_serializable/freezed, rejected by manual/built_value)
    # - a double with fractional part (rejected by all)
    # We do NOT produce null or missing id (all reject).
    id_choice = draw(st.integers(min_value=-(2**63), max_value=2**63-1).map(lambda x: ("int", x)) |
                     st.floats(allow_nan=False, allow_infinity=False).filter(lambda f: f != int(f)).map(lambda f: ("double_frac", f)) |
                     st.floats(min_value=2**63, max_value=2**65, allow_infinity=False, allow_nan=False).map(lambda f: ("double_large", f)) |
                     st.floats(min_value=-(2**65), max_value=-(2**63)-1, allow_infinity=False, allow_nan=False).map(lambda f: ("double_large_neg", f)) |
                     st.floats(min_value=-(2**63), max_value=2**63-1, allow_infinity=False, allow_nan=False).filter(lambda f: f == int(f)).map(lambda f: ("double_int", f))
                    )
    id_type, id_val = id_choice

    # Format id JSON value accordingly
    if id_type == "int":
        id_json = str(id_val)
    else:
        # JSON floats must have decimal point or exponent
        # Use repr to get decimal notation with decimal point or exponent
        # repr(float) always includes decimal or exponent
        id_json = repr(id_val)

    # --- amount field ---
    # required string, non-nullable
    # We produce always a string (non-null)
    amount_str = draw(st.text(min_size=1, max_size=20))
    amount_json = json_string(amount_str)

    # --- name field ---
    # nullable string, optional presence
    # Missing name is accepted by all
    # null name accepted by all
    # string name accepted by all
    # We vary presence and null vs string
    name_presence = draw(st.sampled_from(["missing", "null", "string"]))
    if name_presence == "missing":
        name_json = None
    elif name_presence == "null":
        name_json = "null"
    else:
        name_val = draw(st.text(max_size=20))
        name_json = json_string(name_val)

    # --- status field ---
    # required enum string, non-nullable
    # unrecognized string rejected by all
    # We produce either a valid enum or an invalid string to cause rejection
    status_valid = draw(st.booleans())
    if status_valid:
        status_val = draw(st.sampled_from(STATUS_VALUES))
    else:
        # invalid string: non-empty, not in STATUS_VALUES
        # avoid empty string (could be accepted as missing?)
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES))
        status_val = invalid_status
    status_json = json_string(status_val)

    # --- tags field ---
    # array of strings, optional presence
    # Missing tags accepted by built_value (uses empty list), rejected by others
    # Present tags must be array of strings (empty allowed)
    # We produce either missing or present with array of strings
    tags_presence = draw(st.sampled_from(["missing", "present"]))
    if tags_presence == "missing":
        tags_json = None
    else:
        # array of strings, length 0..5
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
        tags_json = json_string_array(tags_list)

    # --- child field ---
    # nullable record or null or missing
    # Missing child accepted by all
    # null child accepted by all
    # child present: one level recursion only
    # We produce either missing, null, or a nested record with no child (child missing)
    child_presence = draw(st.sampled_from(["missing", "null", "present"]))
    if child_presence == "missing":
        child_json = None
    elif child_presence == "null":
        child_json = "null"
    else:
        # nested record with no child field (missing child)
        # id: int within 64-bit range (to avoid double edge cases in child)
        child_id = draw(st.integers(min_value=-(2**63), max_value=2**63-1))
        child_amount = draw(st.text(min_size=1, max_size=20))
        child_name_presence = draw(st.sampled_from(["missing", "null", "string"]))
        if child_name_presence == "missing":
            child_name_json = None
        elif child_name_presence == "null":
            child_name_json = "null"
        else:
            child_name_json = json_string(draw(st.text(max_size=20)))
        child_status = draw(st.sampled_from(STATUS_VALUES))
        child_tags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=3))
        child_tags_json = json_string_array(child_tags_list)

        # Build child JSON object text
        child_fields = []
        child_fields.append('"id":' + str(child_id))
        child_fields.append('"amount":' + json_string(child_amount))
        if child_name_json is not None:
            child_fields.append('"name":' + child_name_json)
        child_fields.append('"status":' + json_string(child_status))
        child_fields.append('"tags":' + child_tags_json)
        # child field missing in child record (no recursion beyond one level)
        child_json = "{" + ",".join(child_fields) + "}"

    # Build top-level JSON object fields
    fields = []
    fields.append('"id":' + id_json)
    fields.append('"amount":' + amount_json)
    if name_json is not None:
        fields.append('"name":' + name_json)
    fields.append('"status":' + status_json)
    if tags_json is not None:
        fields.append('"tags":' + tags_json)
    if child_json is not None:
        fields.append('"child":' + child_json)

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")