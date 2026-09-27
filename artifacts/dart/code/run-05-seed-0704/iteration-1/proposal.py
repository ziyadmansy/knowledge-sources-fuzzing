from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    valid_statuses = ["active", "inactive", "unknown"]
    # We will sometimes produce invalid enum strings to trigger divergence
    invalid_statuses = ["Active", "INACTIVE", "unknown ", "invalid", "", "null", "123"]

    # id: integer or float representing integer (for json_serializable/freezed)
    # or a non-integer float (to test built_value rejection)
    # or a string (to test manual parsing cast failure)
    id_type = draw(st.sampled_from(["int", "float_int", "float_frac", "string"]))
    if id_type == "int":
        id_val = draw(st.integers(min_value=0, max_value=1_000_000))
        id_json = str(id_val)
    elif id_type == "float_int":
        # float with zero fractional part, e.g. 1.0
        id_val = draw(st.integers(min_value=0, max_value=1_000_000))
        id_json = f"{id_val}.0"
    elif id_type == "float_frac":
        # float with fractional part, e.g. 1.5
        id_val = draw(st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False))
        # ensure fractional part non-zero and not integral
        while id_val == int(id_val):
            id_val = draw(st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False))
        id_json = repr(id_val)
    else:  # string
        id_val = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"\n\r\t\\')))
        id_json = '"' + id_val.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # amount: always string, generate a numeric string or random string
    amount_val = draw(st.one_of(
        st.integers(min_value=0, max_value=1_000_000).map(str),
        st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False).map(lambda f: repr(f)),
        st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\n\r\t\\'))
    ))
    amount_json = '"' + amount_val.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # name: null or string (possibly empty)
    name_val = draw(st.one_of(st.none(), st.text(max_size=20, alphabet=st.characters(blacklist_characters='"\n\r\t\\'))))
    if name_val is None:
        name_json = "null"
    else:
        name_json = '"' + name_val.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # status: mostly valid enum, sometimes invalid to trigger divergence
    status_choice = draw(st.one_of(
        st.sampled_from(valid_statuses).map(lambda s: (s, True)),
        st.sampled_from(invalid_statuses).map(lambda s: (s, False))
    ))
    status_val, status_valid = status_choice
    status_json = '"' + status_val.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # tags: array of strings, but sometimes inject a non-string element to cause cast errors
    # We produce mostly valid tags, but sometimes one element is int/null/bool/object/array
    tags_len = draw(st.integers(min_value=0, max_value=5))
    # Decide if tags are all strings or have one non-string element
    tags_all_strings = draw(st.booleans())
    if tags_all_strings:
        tags_elements = draw(st.lists(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\n\r\t\\')), min_size=tags_len, max_size=tags_len))
        # Escape strings
        tags_json_elements = ['"' + e.replace('\\', '\\\\').replace('"', '\\"') + '"' for e in tags_elements]
    else:
        # Insert exactly one non-string element at random position
        if tags_len == 0:
            # no elements, so no non-string possible, fallback to empty array
            tags_json_elements = []
        else:
            non_string_element = draw(st.one_of(
                st.integers(min_value=-100, max_value=100).map(str),
                st.just("null"),
                st.just("true"),
                st.just("false"),
                st.just("[]"),
                st.just("{}"),
            ))
            # Generate strings for other elements
            string_elements = draw(st.lists(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\n\r\t\\')), min_size=tags_len-1, max_size=tags_len-1))
            string_elements_escaped = ['"' + e.replace('\\', '\\\\').replace('"', '\\"') + '"' for e in string_elements]
            # Insert non-string element at random position
            insert_pos = draw(st.integers(min_value=0, max_value=tags_len-1))
            tags_json_elements = string_elements_escaped.copy()
            tags_json_elements.insert(insert_pos, non_string_element)

    tags_json = "[" + ",".join(tags_json_elements) + "]"

    # child: null or nested record (one level only)
    # To avoid infinite recursion, child record is always well-formed and valid
    # We produce a minimal valid child record with all fields valid and simple
    child_present = draw(st.booleans())
    if child_present:
        # child record with all fields valid and simple
        child_id = draw(st.integers(min_value=0, max_value=1000))
        child_amount = "0"
        child_name = "null"
        child_status = '"active"'
        child_tags = "[]"
        child_child = "null"
        child_json = (
            '{'
            f'"id":{child_id},'
            f'"amount":{child_amount},'
            f'"name":{child_name},'
            f'"status":{child_status},'
            f'"tags":{child_tags},'
            f'"child":{child_child}'
            '}'
        )
        child_json_val = child_json
    else:
        child_json_val = "null"

    # Compose full JSON object
    json_text = (
        '{'
        f'"id":{id_json},'
        f'"amount":{amount_json},'
        f'"name":{name_json},'
        f'"status":{status_json},'
        f'"tags":{tags_json},'
        f'"child":{child_json_val}'
        '}'
    )

    return json_text.encode("utf-8")