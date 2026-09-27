from hypothesis import strategies as st

# Constants for fixed sets
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce a JSON string literal with proper escaping of " and \
# We keep it simple: only allow chars that don't need escaping except \ and "
# Escape " and \ only.
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, with the given schema:
    {
      "id": <integer>,
      "amount": <string>,
      "name": <string or null>,
      "status": <one of "active", "inactive", "unknown">,
      "tags": <array of strings>,
      "child": <Record or null, one level of recursion normally>
    }
    We produce documents that are almost well-formed but with one or two subtle
    divergences to maximize disagreement between the four Dart deserializers.
    """

    # --- id field ---
    # To exploit the known difference in id decoding:
    # manual and built_value require a true Dart int (json int),
    # json_serializable and freezed accept double and call toInt().
    # jsonDecode turns integer literals outside 64-bit range into double.
    # So we produce id as either:
    # - a JSON integer in 64-bit range (accepted by all)
    # - a JSON integer outside 64-bit range (encoded as a JSON number without decimal point,
    #   but jsonDecode will parse it as double, so manual and built_value reject)
    # - a JSON number with decimal point but integral value (accepted by json_serializable/freezed)
    # - a JSON number with decimal point and fractional part (should be rejected by all)
    # We'll pick one of these with weighted probability to get divergences.

    # 64-bit signed int range
    INT64_MIN = -2**63
    INT64_MAX = 2**63 - 1

    id_case = draw(st.sampled_from(['int64_in_range', 'int64_out_of_range', 'double_integral', 'double_fractional']))

    if id_case == 'int64_in_range':
        # Pick an int in 64-bit range
        id_val = draw(st.integers(min_value=INT64_MIN, max_value=INT64_MAX))
        id_json = str(id_val)
    elif id_case == 'int64_out_of_range':
        # Pick an int outside 64-bit range, large magnitude
        # Use decimal notation without decimal point, so jsonDecode will parse as double
        # Pick either less than INT64_MIN or greater than INT64_MAX
        if draw(st.booleans()):
            # less than INT64_MIN
            val = draw(st.integers(min_value=INT64_MIN - 10**10, max_value=INT64_MIN - 1))
        else:
            # greater than INT64_MAX
            val = draw(st.integers(min_value=INT64_MAX + 1, max_value=INT64_MAX + 10**10))
        id_json = str(val)
    elif id_case == 'double_integral':
        # A JSON number with decimal point but integral value, e.g. 42.0
        integral = draw(st.integers(min_value=-10**6, max_value=10**6))
        id_json = f"{integral}.0"
    else:
        # double_fractional: a JSON number with fractional part, e.g. 42.5
        integral = draw(st.integers(min_value=-10**6, max_value=10**6))
        fractional = draw(st.floats(min_value=0.1, max_value=0.9))
        # Format fractional with one digit after decimal
        frac_digit = int(fractional * 10)
        id_json = f"{integral}.{frac_digit}"

    # --- amount field ---
    # amount is a string, non-nullable.
    # We produce a string that is either:
    # - a normal string (accepted by all)
    # - an empty string (accepted by all)
    # - a string with unicode escapes or special chars (accepted by all)
    # - a string that looks like a number (to check no confusion)
    # We keep it simple: generate ascii printable strings with possible digits.

    amount_str = draw(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['"', '\\']), min_size=0, max_size=20))
    amount_json = json_string_literal(amount_str)

    # --- name field ---
    # nullable string or null
    # We produce either null or a string (including empty string)
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        name_str = draw(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['"', '\\']), max_size=20))
        name_json = json_string_literal(name_str)

    # --- status field ---
    # One of "active", "inactive", "unknown"
    # We produce either a valid status or an invalid string to cause rejection by all
    # To maximize disagreement, mostly valid but sometimes invalid
    status_valid = draw(st.booleans())
    if status_valid:
        status_json = draw(st.sampled_from(STATUS_VALUES))
    else:
        # invalid status string, e.g. "pending"
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']))
        status_json = json_string_literal(invalid_status)

    # --- tags field ---
    # array of strings, always present in well-formed document
    # Known divergence: missing tags accepted only by built_value
    # We always include tags field (never missing) to avoid trivial rejection
    # But we can try:
    # - empty array []
    # - array with strings (including empty strings)
    # - array with one non-string element (should be rejected by all)
    # - array with null element (should be rejected by all)
    # To maximize disagreement, mostly valid arrays but sometimes invalid element type

    tags_case = draw(st.sampled_from(['valid_empty', 'valid_nonempty', 'invalid_element_null', 'invalid_element_number']))

    if tags_case == 'valid_empty':
        tags_json = "[]"
    elif tags_case == 'valid_nonempty':
        # array of 1-5 strings
        tag_count = draw(st.integers(min_value=1, max_value=5))
        tags_list = []
        for _ in range(tag_count):
            tag_str = draw(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['"', '\\']), max_size=10))
            tags_list.append(json_string_literal(tag_str))
        tags_json = "[" + ",".join(tags_list) + "]"
    elif tags_case == 'invalid_element_null':
        # array with one null element among strings
        tag_str = draw(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['"', '\\']), max_size=10))
        tags_json = "[" + json_string_literal(tag_str) + ",null]"
    else:
        # invalid_element_number: array with one number element among strings
        tag_str = draw(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['"', '\\']), max_size=10))
        num_val = draw(st.integers(min_value=-1000, max_value=1000))
        tags_json = "[" + json_string_literal(tag_str) + "," + str(num_val) + "]"

    # --- child field ---
    # nullable Record or null
    # To keep recursion bounded, we allow child to be null or a record with child=null only (one level)
    # We produce either null or a child record with all fields present and valid or with one subtle divergence
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json = "null"
    else:
        # Child record fields:
        # id, amount, name, status, tags, child=null
        # We produce a mostly valid child record, but with one subtle divergence:
        # - id as int64_in_range or int64_out_of_range or double_integral (like top-level)
        # - amount string normal
        # - name nullable string or null
        # - status valid only (to avoid double invalid)
        # - tags valid only (to avoid double invalid)
        # - child always null (no deeper recursion)

        child_id_case = draw(st.sampled_from(['int64_in_range', 'int64_out_of_range', 'double_integral']))

        if child_id_case == 'int64_in_range':
            child_id_val = draw(st.integers(min_value=INT64_MIN, max_value=INT64_MAX))
            child_id_json = str(child_id_val)
        elif child_id_case == 'int64_out_of_range':
            if draw(st.booleans()):
                val = draw(st.integers(min_value=INT64_MIN - 10**10, max_value=INT64_MIN - 1))
            else:
                val = draw(st.integers(min_value=INT64_MAX + 1, max_value=INT64_MAX + 10**10))
            child_id_json = str(val)
        else:
            integral = draw(st.integers(min_value=-10**6, max_value=10**6))
            child_id_json = f"{integral}.0"

        child_amount_str = draw(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['"', '\\']), max_size=20))
        child_amount_json = json_string_literal(child_amount_str)

        child_name_is_null = draw(st.booleans())
        if child_name_is_null:
            child_name_json = "null"
        else:
            child_name_str = draw(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['"', '\\']), max_size=20))
            child_name_json = json_string_literal(child_name_str)

        child_status_json = draw(st.sampled_from(STATUS_VALUES))

        # child tags always valid nonempty array of strings (1-3)
        child_tag_count = draw(st.integers(min_value=1, max_value=3))
        child_tags_list = []
        for _ in range(child_tag_count):
            tag_str = draw(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['"', '\\']), max_size=10))
            child_tags_list.append(json_string_literal(tag_str))
        child_tags_json = "[" + ",".join(child_tags_list) + "]"

        child_child_json = "null"

        child_json = (
            "{" +
            f'"id":{child_id_json},' +
            f'"amount":{child_amount_json},' +
            f'"name":{child_name_json},' +
            f'"status":{child_status_json},' +
            f'"tags":{child_tags_json},' +
            f'"child":{child_child_json}' +
            "}"
        )

    # --- Compose top-level JSON object ---
    # We always include all six fields (never missing) except we can try missing tags to trigger known divergence
    # But missing tags is known divergence but also causes rejection by manual, json_serializable, freezed
    # To maximize score, we mostly include tags, but sometimes omit it to trigger divergence.

    include_tags = draw(st.booleans())
    # If include_tags is False, omit tags field entirely (known divergence)
    # If True, include tags_json as above

    # Compose fields in random order to avoid bias
    fields = [
        ('"id"', id_json),
        ('"amount"', amount_json),
        ('"name"', name_json),
        ('"status"', status_json),
        ('"child"', child_json),
    ]
    if include_tags:
        fields.append(('"tags"', tags_json))

    # Shuffle fields order
    fields = draw(st.permutations(fields))

    # Build JSON object string
    json_fields_str = ",".join(f"{k}:{v}" for k, v in fields)
    json_obj_str = "{" + json_fields_str + "}"

    return json_obj_str.encode('utf-8')