from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    valid_statuses = ["active", "inactive", "unknown"]
    # We will sometimes produce invalid enum strings to trigger divergence
    invalid_statuses = ["Active", "INACTIVE", "unknown ", "actve", "inactivee", "null", ""]

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Escape backslash and double quote
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars (minimal)
        s = s.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return '"' + s + '"'

    # id field: test integer vs float that is integral vs float non-integral
    # Manual parsing requires int JSON number (no float)
    # json_serializable and freezed accept float if integral (e.g. 1.0)
    # built_value likely rejects fractional floats
    # So produce mostly integral numbers, sometimes float integral, sometimes float non-integral
    id_type = draw(st.sampled_from(["int", "float_integral", "float_fractional"]))
    if id_type == "int":
        id_val = draw(st.integers(min_value=0, max_value=10000))
        id_json = str(id_val)
    elif id_type == "float_integral":
        # float with .0 fractional part
        id_val = float(draw(st.integers(min_value=0, max_value=10000)))
        id_json = str(id_val) + ".0" if not str(id_val).endswith(".0") else str(id_val)
        # But to be sure, force .0 suffix
        if not id_json.endswith(".0"):
            id_json = str(int(id_val)) + ".0"
    else:
        # float fractional, e.g. 1.5
        id_val = draw(st.floats(min_value=0.1, max_value=10000, allow_nan=False, allow_infinity=False))
        # Ensure fractional part non-zero
        while id_val == int(id_val):
            id_val = draw(st.floats(min_value=0.1, max_value=10000, allow_nan=False, allow_infinity=False))
        id_json = repr(id_val)
        # repr might produce scientific notation, which is valid JSON but rare
        # Accept it anyway

    # amount field: string, always present, can be any string
    amount_str = draw(st.text(min_size=1, max_size=20))
    amount_json = json_string_literal(amount_str)

    # name field: string or null
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        name_str = draw(st.text(min_size=0, max_size=20))
        name_json = json_string_literal(name_str)

    # status field: mostly valid enum strings, sometimes invalid to trigger divergence
    status_choice = draw(st.sampled_from(["valid", "invalid"]))
    if status_choice == "valid":
        status_val = draw(st.sampled_from(valid_statuses))
    else:
        status_val = draw(st.sampled_from(invalid_statuses))
    status_json = json_string_literal(status_val)

    # tags field: array of strings, but to trigger divergence, sometimes include non-string elements
    # Manual and json_serializable/freezed throw cast errors on non-string elements
    # built_value likely similar
    # So produce mostly all strings, sometimes one non-string element (int, null, bool)
    tags_len = draw(st.integers(min_value=0, max_value=5))
    # Decide if tags are all strings or have one non-string element
    tags_type = draw(st.sampled_from(["all_strings", "one_non_string"]))
    if tags_type == "all_strings":
        tags_elems = draw(st.lists(st.text(min_size=0, max_size=10), min_size=tags_len, max_size=tags_len))
    else:
        # At least one element is non-string
        if tags_len == 0:
            # no elements, so all strings anyway
            tags_elems = []
        else:
            # Pick one index to be non-string
            non_string_index = draw(st.integers(min_value=0, max_value=tags_len - 1))
            elems = []
            for i in range(tags_len):
                if i == non_string_index:
                    non_str_val = draw(st.sampled_from([
                        "null", "true", "false", "123", "12.3"
                    ]))
                    # These are JSON literals, not strings, so we will emit them raw
                    elems.append(non_str_val)
                else:
                    s = draw(st.text(min_size=0, max_size=10))
                    elems.append(json_string_literal(s))
            tags_elems = elems

    tags_json = "[" + ",".join(tags_elems) + "]"

    # child field: null or nested record (one level)
    # To keep complexity manageable, child is either null or a well-formed record with no further child
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json = "null"
    else:
        # Nested record with all fields valid (no invalid enum, id int only, tags all strings)
        # This avoids combinatorial explosion and focuses divergence on top-level fields
        child_id = draw(st.integers(min_value=0, max_value=10000))
        child_id_json = str(child_id)
        child_amount = draw(st.text(min_size=1, max_size=20))
        child_amount_json = json_string_literal(child_amount)
        child_name_is_null = draw(st.booleans())
        if child_name_is_null:
            child_name_json = "null"
        else:
            child_name = draw(st.text(min_size=0, max_size=20))
            child_name_json = json_string_literal(child_name)
        child_status = draw(st.sampled_from(valid_statuses))
        child_status_json = json_string_literal(child_status)
        child_tags_len = draw(st.integers(min_value=0, max_value=3))
        child_tags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=child_tags_len, max_size=child_tags_len))
        child_tags_json = "[" + ",".join(json_string_literal(t) for t in child_tags) + "]"
        # child.child is null (no further recursion)
        child_json = (
            "{" +
            f'"id":{child_id_json},'
            f'"amount":{child_amount_json},'
            f'"name":{child_name_json},'
            f'"status":{child_status_json},'
            f'"tags":{child_tags_json},'
            f'"child":null'
            "}"
        )

    # Compose full JSON object
    json_obj = (
        "{" +
        f'"id":{id_json},'
        f'"amount":{amount_json},'
        f'"name":{name_json},'
        f'"status":{status_json},'
        f'"tags":{tags_json},'
        f'"child":{child_json}'
        "}"
    )

    return json_obj.encode("utf-8")