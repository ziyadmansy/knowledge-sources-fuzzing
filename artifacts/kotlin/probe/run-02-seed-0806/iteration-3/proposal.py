from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum "status"
    valid_status = ["active", "inactive", "unknown"]
    # Also include some invalid enum values and null for testing enum handling
    enum_variants = valid_status + ["invalid_enum", "123", "", None]

    # Helper: produce JSON string literal with proper escaping of backslash and quotes
    def json_string(s: str) -> str:
        # Minimal escaping: backslash and double quote
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars for safety (not strictly required here)
        s = s.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{s}"'

    # Helper: produce JSON null or string or number for "id" and "amount"
    # id: integer, but can be string or number (both accepted by all)
    # amount: string, but can be string or number (kotlinx rejects number)
    # We will sometimes produce number or string for these fields to trigger divergence.

    # id field: produce int as number or string
    id_int = draw(st.integers(min_value=0, max_value=2**31-1))
    id_as_number = draw(st.booleans())
    if id_as_number:
        id_json = str(id_int)
    else:
        id_json = json_string(str(id_int))

    # amount field: string normally, but sometimes number to trigger divergence
    # Also try empty string, numeric string, or normal string
    amount_str = draw(st.one_of(
        st.text(min_size=0, max_size=10),
        st.integers(min_value=0, max_value=100000).map(str)
    ))
    amount_as_number = draw(st.booleans())
    if amount_as_number:
        # Try to parse amount_str as int if possible, else fallback to 0
        try:
            amt_num = int(amount_str)
        except Exception:
            amt_num = 0
        amount_json = str(amt_num)
    else:
        amount_json = json_string(amount_str)

    # name field: string or null
    # Gson accepts string or null, all accept null
    # We'll produce string or null
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        name_val = draw(st.text(min_size=0, max_size=20))
        name_json = json_string(name_val)

    # status field: enum string, null, or invalid string
    # Gson accepts null enum, others reject
    # Gson accepts unknown enum as null, others reject
    # We'll pick from enum_variants to trigger divergence
    status_val = draw(st.sampled_from(enum_variants))
    if status_val is None:
        status_json = "null"
    else:
        status_json = json_string(status_val)

    # tags field: array of strings normally
    # Gson and Moshi coerce non-string elements to strings
    # kotlinx rejects non-string elements and null elements
    # Jackson accepts non-string elements as-is and null elements
    # Gson and Jackson accept null tags; Moshi and kotlinx reject null tags
    # So tags can be null or array
    tags_is_null = draw(st.booleans())
    if tags_is_null:
        tags_json = "null"
    else:
        # Array length 0 to 5
        tags_len = draw(st.integers(min_value=0, max_value=5))
        tags_elements = []
        for _ in range(tags_len):
            # Element can be string, number, boolean, or null to trigger divergence
            elt_type = draw(st.sampled_from(["string", "int", "bool", "null"]))
            if elt_type == "string":
                s = draw(st.text(min_size=0, max_size=10))
                tags_elements.append(json_string(s))
            elif elt_type == "int":
                n = draw(st.integers(min_value=-100, max_value=100))
                tags_elements.append(str(n))
            elif elt_type == "bool":
                b = draw(st.booleans())
                tags_elements.append("true" if b else "false")
            else:
                tags_elements.append("null")
        tags_json = "[" + ",".join(tags_elements) + "]"

    # child field: null or object with same schema but no further recursion (one level only)
    # Gson accepts empty object for child; others reject
    # We'll produce either null, empty object, or a valid child object (no further recursion)
    child_choice = draw(st.sampled_from(["null", "empty_object", "valid_child"]))
    if child_choice == "null":
        child_json = "null"
    elif child_choice == "empty_object":
        child_json = "{}"
    else:
        # valid child object: all fields present, but no further child recursion (child=null)
        # id: int as number or string
        cid_int = draw(st.integers(min_value=0, max_value=2**31-1))
        cid_as_number = draw(st.booleans())
        if cid_as_number:
            cid_json = str(cid_int)
        else:
            cid_json = json_string(str(cid_int))

        # amount: string only (to avoid double divergence)
        camount_str = draw(st.text(min_size=0, max_size=10))
        camount_json = json_string(camount_str)

        # name: string or null
        cname_is_null = draw(st.booleans())
        if cname_is_null:
            cname_json = "null"
        else:
            cname_val = draw(st.text(min_size=0, max_size=20))
            cname_json = json_string(cname_val)

        # status: valid enum only (to avoid double divergence)
        cstatus_val = draw(st.sampled_from(valid_status))
        cstatus_json = json_string(cstatus_val)

        # tags: array of strings only (to avoid double divergence)
        ctags_len = draw(st.integers(min_value=0, max_value=3))
        ctags_elements = []
        for _ in range(ctags_len):
            s = draw(st.text(min_size=0, max_size=10))
            ctags_elements.append(json_string(s))
        ctags_json = "[" + ",".join(ctags_elements) + "]"

        # child: null (no further recursion)
        cchild_json = "null"

        child_json = (
            "{"
            f'"id":{cid_json},'
            f'"amount":{camount_json},'
            f'"name":{cname_json},'
            f'"status":{cstatus_json},'
            f'"tags":{ctags_json},'
            f'"child":{cchild_json}'
            "}"
        )

    # Compose top-level JSON object
    # To trigger divergence on unknown extra fields, sometimes add one unknown field
    add_extra_field = draw(st.booleans())
    if add_extra_field:
        # Gson and Moshi accept unknown extra fields; kotlinx and Jackson reject
        extra_key = draw(st.text(min_size=1, max_size=10))
        # Extra field value: string or number
        extra_val_type = draw(st.sampled_from(["string", "int"]))
        if extra_val_type == "string":
            extra_val = json_string(draw(st.text(min_size=0, max_size=10)))
        else:
            extra_val = str(draw(st.integers(min_value=-1000, max_value=1000)))
        extra_field_json = f',"{extra_key}":{extra_val}'
    else:
        extra_field_json = ""

    json_text = (
        "{"
        f'"id":{id_json},'
        f'"amount":{amount_json},'
        f'"name":{name_json},'
        f'"status":{status_json},'
        f'"tags":{tags_json},'
        f'"child":{child_json}'
        f"{extra_field_json}"
        "}"
    )

    return json_text.encode("utf-8")