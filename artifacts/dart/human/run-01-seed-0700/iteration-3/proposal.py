from hypothesis import strategies as st

# Constants for the status field
STATUS_VALUES = ['active', 'inactive', 'unknown']

# Helper to produce a JSON string literal from a Python string (no escapes except for " and \)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote for JSON string literal
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the described record schema,
    with subtle variations designed to provoke behavioral divergence between four Dart JSON deserializers.
    """

    # --- id field ---
    # To exploit the difference in id decoding:
    # manual and built_value require a true int (no double),
    # json_serializable and freezed accept double and call toInt().
    # jsonDecode turns out-of-range int literals into double.
    #
    # So we generate either:
    # - a safe int (fits in 64-bit signed range), encoded as an integer literal
    # - an out-of-range int literal encoded as a JSON number that jsonDecode will parse as double
    #
    # 64-bit signed int range: -2^63 .. 2^63-1
    # Use boundaries slightly outside this range to produce doubles.
    #
    # We'll produce either:
    # - an int literal in [-2^63, 2^63-1]
    # - a float literal representing an integer outside that range (e.g. 2^63 or -2^63-1)
    #
    # Because Hypothesis float literals are decimal, we produce a float with no fractional part,
    # e.g. 9223372036854775808.0 (2^63) or -9223372036854775809.0 (-2^63-1)
    #
    # Note: JSON numbers do not distinguish int vs float, but Dart jsonDecode does.
    #
    # We'll produce the id field as a JSON number literal (no quotes).

    # 64-bit signed int boundaries
    INT64_MIN = -9223372036854775808
    INT64_MAX = 9223372036854775807

    # Out-of-range values just outside 64-bit range
    OOR_MIN = INT64_MIN - 1  # -9223372036854775809
    OOR_MAX = INT64_MAX + 1  # 9223372036854775808

    # Choose id variant: "int_in_range" or "float_out_of_range"
    id_variant = draw(st.sampled_from(['int_in_range', 'float_out_of_range']))

    if id_variant == 'int_in_range':
        # Pick an int in range
        id_value = draw(st.integers(min_value=INT64_MIN, max_value=INT64_MAX))
        # JSON number literal as decimal integer string
        id_json = str(id_value)
    else:
        # Pick out-of-range float representing an integer outside 64-bit range
        # Choose either OOR_MIN or OOR_MAX
        oor_value = draw(st.sampled_from([OOR_MIN, OOR_MAX]))
        # Represent as float literal with ".0" to force float
        id_json = str(oor_value) + ".0"

    # --- amount field ---
    # amount is a string, always present.
    # We generate a simple string literal.
    amount_str = draw(st.text(min_size=1, max_size=10))
    amount_json = json_string_literal(amount_str)

    # --- name field ---
    # nullable string, optional presence is accepted by all.
    # We always include it (never missing) to avoid trivial rejections.
    # It can be null or string.
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        name_str = draw(st.text(min_size=0, max_size=10))
        name_json = json_string_literal(name_str)

    # --- status field ---
    # one of "active", "inactive", "unknown"
    # Always present, always valid string to avoid trivial rejection.
    status_str = draw(st.sampled_from(STATUS_VALUES))
    status_json = json_string_literal(status_str)

    # --- tags field ---
    # array of strings, always present normally.
    # Known divergence: missing tags accepted only by built_value.
    # We produce either:
    # - present tags array (possibly empty)
    # - or missing tags field (to provoke divergence)
    tags_present = draw(st.booleans())
    if tags_present:
        # tags array of strings (possibly empty)
        tags_len = draw(st.integers(min_value=0, max_value=3))
        tags_list = draw(st.lists(st.text(min_size=0, max_size=5), min_size=tags_len, max_size=tags_len))
        # encode tags array as JSON array of string literals
        tags_json = "[" + ",".join(json_string_literal(t) for t in tags_list) + "]"
    else:
        tags_json = None  # field omitted

    # --- child field ---
    # nullable record or null
    # We produce either:
    # - null
    # - a one-level nested record (no recursion beyond one level)
    # - omit child field (accepted by all)
    child_choice = draw(st.sampled_from(['null', 'record', 'missing']))

    if child_choice == 'null':
        child_json = "null"
    elif child_choice == 'missing':
        child_json = None
    else:
        # nested record with same schema but no further recursion (child.child always null or missing)
        # To keep it simple, nested child.child is always null here.
        # We reuse the same generation logic but fix child.child to null or missing.
        # For nested record, we pick:
        # id: int in range (to avoid nested complexity)
        nested_id = draw(st.integers(min_value=INT64_MIN, max_value=INT64_MAX))
        nested_id_json = str(nested_id)
        nested_amount = draw(st.text(min_size=1, max_size=10))
        nested_amount_json = json_string_literal(nested_amount)
        nested_name_null = draw(st.booleans())
        if nested_name_null:
            nested_name_json = "null"
        else:
            nested_name_json = json_string_literal(draw(st.text(min_size=0, max_size=10)))
        nested_status = draw(st.sampled_from(STATUS_VALUES))
        nested_status_json = json_string_literal(nested_status)
        nested_tags_len = draw(st.integers(min_value=0, max_value=3))
        nested_tags_list = draw(st.lists(st.text(min_size=0, max_size=5), min_size=nested_tags_len, max_size=nested_tags_len))
        nested_tags_json = "[" + ",".join(json_string_literal(t) for t in nested_tags_list) + "]"
        # nested child field: null or missing (choose randomly)
        nested_child_present = draw(st.booleans())
        if nested_child_present:
            nested_child_json = "null"
        else:
            nested_child_json = None

        # Compose nested record JSON fields
        nested_fields = [
            '"id":' + nested_id_json,
            '"amount":' + nested_amount_json,
            '"name":' + nested_name_json,
            '"status":' + nested_status_json,
            '"tags":' + nested_tags_json,
        ]
        if nested_child_json is not None:
            nested_fields.append('"child":' + nested_child_json)
        # else omit child field

        child_json = "{" + ",".join(nested_fields) + "}"

    # Compose top-level JSON fields
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
    ]
    if tags_json is not None:
        fields.append('"tags":' + tags_json)
    # else omit tags field to provoke divergence

    if child_json is not None:
        fields.append('"child":' + child_json)
    # else omit child field

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")