from hypothesis import strategies as st

# We build JSON text manually, carefully controlling types and formatting.
# We produce mostly well-formed documents with one or two fields tweaked to
# provoke divergence among Gson, Moshi, kotlinx.serialization, Jackson.

# We use bounded recursion depth to produce "child" records.

# We leverage known divergences:
# - "amount": string or number (kotlinx rejects number)
# - "name": string, null, or number (kotlinx rejects number)
# - "status": exact enum strings, or invalid string (Gson accepts invalid as null)
# - "tags": array of strings, or array with numbers/booleans (kotlinx rejects non-string)
# - "child": null, full record, or empty object ({} accepted only by Gson)
# - extra fields: present or absent (kotlinx/Jackson reject extra fields)
# - missing fields in child: present or missing (Gson fills defaults, others reject)
# - numeric "id": integer or string convertible to integer (all accept both)
# - duplicate keys: last wins (not modeled here, too complex for now)

# We produce a mostly valid record, then randomly tweak one or two fields to
# values that cause known divergences.

MAX_DEPTH = 1  # one level of recursion for "child"

# Enum values for "status"
STATUS_ENUM = ["active", "inactive", "unknown"]

@st.composite
def generated_json(draw, depth=0):
    # id: integer or string convertible to integer
    id_int = draw(st.integers(min_value=0, max_value=1000))
    id_as_string = draw(st.booleans())
    if id_as_string:
        id_json = '"' + str(id_int) + '"'
    else:
        id_json = str(id_int)

    # amount: string or number (kotlinx rejects number)
    # We pick mostly string, sometimes number
    amount_as_number = draw(st.booleans())
    if amount_as_number:
        # number as integer or float string
        amount_num = draw(st.one_of(st.integers(min_value=0, max_value=10000), st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)))
        # format floats carefully
        if isinstance(amount_num, float):
            amount_json = str(round(amount_num, 2))
        else:
            amount_json = str(amount_num)
    else:
        # string, possibly empty or numeric string
        amount_str = draw(st.text(min_size=0, max_size=10))
        # escape quotes and backslashes minimally
        amount_str_esc = amount_str.replace('\\', '\\\\').replace('"', '\\"')
        amount_json = '"' + amount_str_esc + '"'

    # name: string, null, or number (kotlinx rejects number)
    # Also test null always accepted
    name_choice = draw(st.sampled_from(["string", "null", "number"]))
    if name_choice == "string":
        name_str = draw(st.text(min_size=0, max_size=10))
        name_str_esc = name_str.replace('\\', '\\\\').replace('"', '\\"')
        name_json = '"' + name_str_esc + '"'
    elif name_choice == "null":
        name_json = "null"
    else:  # number
        name_num = draw(st.one_of(st.integers(min_value=-1000, max_value=1000), st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
        if isinstance(name_num, float):
            name_json = str(round(name_num, 2))
        else:
            name_json = str(name_num)

    # status: exact enum strings or invalid string (Gson accepts invalid as null)
    # Mostly valid, sometimes invalid string
    status_valid = draw(st.booleans())
    if status_valid:
        status_val = draw(st.sampled_from(STATUS_ENUM))
        status_json = '"' + status_val + '"'
    else:
        # invalid string: random string not in enum
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_ENUM))
        invalid_status_esc = invalid_status.replace('\\', '\\\\').replace('"', '\\"')
        status_json = '"' + invalid_status_esc + '"'

    # tags: array of strings or array with numbers/booleans (kotlinx rejects non-string)
    # Moshi rejects booleans, Gson/Jackson accept numbers and booleans
    # We produce arrays mostly of strings, sometimes with numbers or booleans
    tags_type = draw(st.sampled_from(["strings", "numbers", "booleans"]))
    tags_len = draw(st.integers(min_value=0, max_value=5))
    tags_elements = []
    for _ in range(tags_len):
        if tags_type == "strings":
            s = draw(st.text(min_size=0, max_size=10))
            s_esc = s.replace('\\', '\\\\').replace('"', '\\"')
            tags_elements.append('"' + s_esc + '"')
        elif tags_type == "numbers":
            n = draw(st.one_of(st.integers(min_value=-1000, max_value=1000), st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
            if isinstance(n, float):
                tags_elements.append(str(round(n, 2)))
            else:
                tags_elements.append(str(n))
        else:  # booleans
            b = draw(st.booleans())
            tags_elements.append("true" if b else "false")
    tags_json = "[" + ",".join(tags_elements) + "]"

    # child: null, full record, or empty object ({} accepted only by Gson)
    # Limit recursion depth to MAX_DEPTH
    child_type = draw(st.sampled_from(["null", "record", "empty_object"]))
    if depth >= MAX_DEPTH:
        # no recursion deeper than MAX_DEPTH
        child_type = draw(st.sampled_from(["null", "empty_object"]))
    if child_type == "null":
        child_json = "null"
    elif child_type == "empty_object":
        child_json = "{}"
    else:
        # full record recursively
        child_json = draw(generated_json(depth=depth + 1)).decode("utf-8")

    # Extra fields: present or absent (kotlinx/Jackson reject extra fields)
    # If present, add one extra field with string value
    extra_field_present = draw(st.booleans())
    if extra_field_present:
        extra_key = "extra_field"
        extra_val_str = draw(st.text(min_size=0, max_size=10))
        extra_val_esc = extra_val_str.replace('\\', '\\\\').replace('"', '\\"')
        extra_field_json = f',"{extra_key}":"{extra_val_esc}"'
    else:
        extra_field_json = ""

    # Missing fields inside child: if child is record, sometimes omit one field (Moshi/kotlinx/Jackson reject)
    # We only do this if child is a record and depth < MAX_DEPTH
    # To keep code simpler, we do not implement missing fields inside child here,
    # because it requires building child JSON as dict and removing keys.
    # Instead, we rely on other divergences.

    # Compose the JSON text for the top-level record
    # Fields order: id, amount, name, status, tags, child, extra_field (if any)
    json_text = (
        '{'
        f'"id":{id_json},'
        f'"amount":{amount_json},'
        f'"name":{name_json},'
        f'"status":{status_json},'
        f'"tags":{tags_json},'
        f'"child":{child_json}'
        f'{extra_field_json}'
        '}'
    )

    return json_text.encode("utf-8")