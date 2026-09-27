from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum status
    valid_statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (escape minimal set)
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally for JSON string
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Helper: produce JSON array of strings
    def json_string_array(arr):
        return "[" + ",".join(json_string(s) for s in arr) + "]"

    # Compose a "name" field: either null or string
    name_value = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
    if name_value is None:
        name_json = "null"
    else:
        name_json = json_string(name_value)

    # Compose "id": integer, but allow also null or missing to test rejection
    # But missing fields cause all reject except built_value for some fields.
    # We want to produce always all fields present (per instructions),
    # but vary types slightly to provoke divergence.
    # So id must be integer, but try also stringified integer or float to provoke type errors.
    # However, probe 12 shows "amount" as number is rejected by all.
    # So let's keep id as integer or string integer to try to provoke divergence.
    id_type = draw(st.sampled_from(["int", "string_int", "null"]))
    if id_type == "int":
        id_value = draw(st.integers(min_value=0, max_value=1000000))
        id_json = str(id_value)
    elif id_type == "string_int":
        id_value = draw(st.integers(min_value=0, max_value=1000000))
        id_json = json_string(str(id_value))
    else:  # null
        id_json = "null"

    # Compose "amount": string required, no null allowed (probe 8 rejects null)
    # Try to provoke divergence by using string or number or null
    # But number rejected by all (probe 12), null rejected by all (probe 8)
    # So only string allowed, but we can try empty string, or string with digits, or string with whitespace
    amount_value = draw(st.text(min_size=0, max_size=20))
    amount_json = json_string(amount_value)

    # Compose "status": enum string, required, no null allowed (probe 9 rejects null)
    # Only exact lowercase "active", "inactive", "unknown" accepted
    # Try to provoke divergence by using valid enum, or missing (built_value accepts missing),
    # or null (all reject), or invalid casing (all reject)
    # But instructions say all fields always present in well-formed document,
    # so we keep present but vary value to valid or invalid enum.
    status_choice = draw(st.sampled_from(["valid", "invalid", "null"]))
    if status_choice == "valid":
        status_value = draw(st.sampled_from(valid_statuses))
        status_json = json_string(status_value)
    elif status_choice == "invalid":
        # invalid enum string (probe 16 rejected by all)
        # but try to provoke divergence by using a string close to valid
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_statuses))
        status_json = json_string(invalid_status)
    else:
        status_json = "null"

    # Compose "tags": array of strings, required, no null allowed (probe 10 rejects null except built_value accepts null as empty array)
    # Try to provoke divergence by using null (built_value accepts as empty array), empty array, or array with strings
    tags_choice = draw(st.sampled_from(["normal", "null"]))
    if tags_choice == "normal":
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        tags_json = json_string_array(tags_list)
    else:
        tags_json = "null"

    # Compose "child": either null or a nested record (one level recursion)
    # Compose child record similarly but simpler: all fields present and valid
    # To provoke divergence, child can be null or a valid record or malformed record
    child_choice = draw(st.sampled_from(["null", "valid", "malformed"]))
    if child_choice == "null":
        child_json = "null"
    elif child_choice == "valid":
        # Compose a valid child record with all fields present and valid types
        child_id = draw(st.integers(min_value=0, max_value=1000000))
        child_amount = draw(st.text(min_size=1, max_size=20))
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        child_status = draw(st.sampled_from(valid_statuses))
        child_tags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))

        child_name_json = "null" if child_name is None else json_string(child_name)
        child_json = (
            "{" +
            f'"id":{child_id},' +
            f'"amount":{json_string(child_amount)},' +
            f'"name":{child_name_json},' +
            f'"status":{json_string(child_status)},' +
            f'"tags":{json_string_array(child_tags)},' +
            f'"child":null' +
            "}"
        )
    else:
        # malformed child: e.g. missing required field "id" or wrong type for "tags"
        malformed_choice = draw(st.sampled_from(["missing_id", "tags_wrong_type", "status_null"]))
        if malformed_choice == "missing_id":
            # omit "id" field (probe 1 shows all reject missing id)
            child_amount = draw(st.text(min_size=1, max_size=20))
            child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
            child_status = draw(st.sampled_from(valid_statuses))
            child_tags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))
            child_name_json = "null" if child_name is None else json_string(child_name)
            child_json = (
                "{" +
                # no id
                f'"amount":{json_string(child_amount)},' +
                f'"name":{child_name_json},' +
                f'"status":{json_string(child_status)},' +
                f'"tags":{json_string_array(child_tags)},' +
                f'"child":null' +
                "}"
            )
        elif malformed_choice == "tags_wrong_type":
            # tags as array with non-string elements (probe 19 all reject)
            child_id = draw(st.integers(min_value=0, max_value=1000000))
            child_amount = draw(st.text(min_size=1, max_size=20))
            child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
            child_status = draw(st.sampled_from(valid_statuses))
            # tags array with a number inside
            child_tags_json = "[1,2]"
            child_name_json = "null" if child_name is None else json_string(child_name)
            child_json = (
                "{" +
                f'"id":{child_id},' +
                f'"amount":{json_string(child_amount)},' +
                f'"name":{child_name_json},' +
                f'"status":{json_string(child_status)},' +
                f'"tags":{child_tags_json},' +
                f'"child":null' +
                "}"
            )
        else:  # status_null
            # status null (probe 9 all reject)
            child_id = draw(st.integers(min_value=0, max_value=1000000))
            child_amount = draw(st.text(min_size=1, max_size=20))
            child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
            child_tags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))
            child_name_json = "null" if child_name is None else json_string(child_name)
            child_json = (
                "{" +
                f'"id":{child_id},' +
                f'"amount":{json_string(child_amount)},' +
                f'"name":{child_name_json},' +
                f'"status":null,' +
                f'"tags":{json_string_array(child_tags)},' +
                f'"child":null' +
                "}"
            )

    # Compose the top-level JSON object with all six fields always present (per instructions)
    # Order fields in canonical order for clarity
    # id, amount, name, status, tags, child
    json_obj = (
        "{" +
        f'"id":{id_json},' +
        f'"amount":{amount_json},' +
        f'"name":{name_json},' +
        f'"status":{status_json},' +
        f'"tags":{tags_json},' +
        f'"child":{child_json}' +
        "}"
    )

    # Return as bytes
    return json_obj.encode("utf-8")