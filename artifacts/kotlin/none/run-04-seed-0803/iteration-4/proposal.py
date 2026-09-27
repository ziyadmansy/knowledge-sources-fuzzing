from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and null
    status_values = ["active", "inactive", "unknown"]
    null = "null"

    # Helper: produce a JSON string literal with proper escaping for simple ASCII only
    # (Hypothesis strings are unicode, but we keep it simple)
    def json_string(s: str) -> str:
        # Escape backslash and double quote only for simplicity
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars (replace with \uXXXX)
        # but to keep it simple, just remove control chars here
        s = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in s)
        return '"' + s + '"'

    # Compose a valid "amount" string: can be numeric string or something else
    # To induce divergence, sometimes produce numeric strings, sometimes non-numeric
    amount_str = draw(
        st.one_of(
            st.just("0"),
            st.just("123.45"),
            st.just("-0"),
            st.just("1e10"),
            st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
        )
    )
    amount_json = json_string(amount_str)

    # Compose "id" as integer or sometimes as a string to induce divergence
    id_is_int = draw(st.booleans())
    if id_is_int:
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_json = str(id_val)
    else:
        # id as string (wrong type)
        id_val = draw(st.text(min_size=1, max_size=5).filter(lambda s: s.isdigit()))
        id_json = json_string(id_val)

    # Compose "name" as null or string or sometimes number (wrong type)
    name_type = draw(st.sampled_from(["null", "string", "number"]))
    if name_type == "null":
        name_json = null
    elif name_type == "string":
        name_val = draw(st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)))
        name_json = json_string(name_val)
    else:
        # number as wrong type for name
        name_val = draw(st.integers(min_value=-100, max_value=100))
        name_json = str(name_val)

    # Compose "status" as valid enum string or sometimes invalid string or number or null
    status_type = draw(st.sampled_from(["valid", "invalid_string", "number", "null"]))
    if status_type == "valid":
        status_val = draw(st.sampled_from(status_values))
        status_json = json_string(status_val)
    elif status_type == "invalid_string":
        # invalid enum string
        invalid_status = draw(st.text(min_size=1, max_size=8).filter(lambda s: s not in status_values and all(32 <= ord(c) <= 126 for c in s)))
        status_json = json_string(invalid_status)
    elif status_type == "number":
        status_json = str(draw(st.integers(min_value=0, max_value=10)))
    else:
        status_json = null

    # Compose "tags" as array of strings or sometimes null or sometimes array with non-string
    tags_type = draw(st.sampled_from(["valid_array", "empty_array", "null", "array_with_nonstring"]))
    if tags_type == "valid_array":
        tags_list = draw(st.lists(st.text(min_size=1, max_size=8).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), min_size=1, max_size=5))
        tags_json = "[" + ",".join(json_string(t) for t in tags_list) + "]"
    elif tags_type == "empty_array":
        tags_json = "[]"
    elif tags_type == "null":
        tags_json = null
    else:
        # array with one non-string element (number)
        good_tags = draw(st.lists(st.text(min_size=1, max_size=8).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), min_size=0, max_size=4))
        nonstring = str(draw(st.integers(min_value=0, max_value=100)))
        arr = good_tags + [nonstring]
        tags_json = "[" + ",".join(json_string(t) if isinstance(t, str) else t for t in arr) + "]"

    # Compose "child" as null or a nested record (one level only)
    # To keep recursion bounded, child can be null or a record with all fields valid or with one field slightly off
    child_type = draw(st.sampled_from(["null", "valid_child", "child_with_one_error"]))

    def make_child_record(with_error=False):
        # id int always for child
        child_id = draw(st.integers(min_value=0, max_value=1000))
        child_id_json = str(child_id)

        # amount string always valid for child
        child_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)))
        child_amount_json = json_string(child_amount)

        # name string or null for child
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))))
        child_name_json = null if child_name is None else json_string(child_name)

        # status valid enum for child
        child_status = draw(st.sampled_from(status_values))
        child_status_json = json_string(child_status)

        # tags array of strings for child
        child_tags_list = draw(st.lists(st.text(min_size=1, max_size=8).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), min_size=0, max_size=3))
        child_tags_json = "[" + ",".join(json_string(t) for t in child_tags_list) + "]"

        # child.child is always null (one level recursion)
        child_child_json = null

        # If with_error, introduce one small error in one field
        if with_error:
            error_field = draw(st.sampled_from(["id", "amount", "name", "status", "tags"]))
            if error_field == "id":
                # id as string instead of int
                child_id_json_err = json_string(str(child_id))
                child_id_json = child_id_json_err
            elif error_field == "amount":
                # amount as number instead of string
                child_amount_json = str(draw(st.integers(min_value=0, max_value=1000)))
            elif error_field == "name":
                # name as number instead of string/null
                child_name_json = str(draw(st.integers(min_value=0, max_value=1000)))
            elif error_field == "status":
                # status invalid string
                child_status_json = json_string("badstatus")
            elif error_field == "tags":
                # tags null instead of array
                child_tags_json = null

        return (
            '"id":' + child_id_json + ","
            + '"amount":' + child_amount_json + ","
            + '"name":' + child_name_json + ","
            + '"status":' + child_status_json + ","
            + '"tags":' + child_tags_json + ","
            + '"child":' + child_child_json
        )

    if child_type == "null":
        child_json = null
    elif child_type == "valid_child":
        child_json = "{" + make_child_record(with_error=False) + "}"
    else:
        child_json = "{" + make_child_record(with_error=True) + "}"

    # Compose top-level JSON object with all fields
    # To induce divergence, sometimes omit one field (except id and amount which are required)
    # But per instructions, all six fields always present in well-formed document
    # So we produce mostly well-formed with one field off type or value

    # Compose fields as list of key:value strings
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
        '"child":' + child_json,
    ]

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")