from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text for the described record schema with subtle variations
    to maximize divergence among Gson, Moshi, kotlinx.serialization, and Jackson.

    Strategy:
    - Generate a mostly valid record with all fields present and well-typed.
    - Introduce at most one or two small deviations:
      * missing required field (except "child" which can be missing or null)
      * null in non-nullable field (except "name" nullable)
      * wrong type for a field (e.g. number instead of string for "amount")
      * unknown enum value or case variant for "status"
      * empty object for "child" or nested child with missing fields
      * null for non-nullable string fields ("amount")
      * "amount" as number or string (to trigger known differences)
    - Limit recursion depth to 1 for "child".
    - Compose JSON text manually with string concatenation.
    """

    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]
    STATUS_UNKNOWN_ENUMS = ["Active", "INACTIVE", "unknownx", "null", ""]  # invalid or case variants
    MAX_TAGS = 3
    MAX_TAG_LENGTH = 8

    # Helper to quote JSON strings with minimal escaping (only backslash and quote)
    def json_str(s: str) -> str:
        # Escape backslash and quote
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'

    # Generate a valid "id" integer (>=0)
    id_val = draw(st.integers(min_value=0, max_value=1000))

    # Generate "amount" as string normally, but sometimes number or null or missing
    # "amount" is non-nullable string in Kotlin, but Gson accepts null and number
    amount_type = draw(st.sampled_from(["string", "number", "null", "missing"]))
    # For "missing" we omit the field (to test missing required field)
    if amount_type == "string":
        amount_val = draw(st.text(min_size=1, max_size=10))
        amount_json = json_str(amount_val)
    elif amount_type == "number":
        # number as int or float
        amount_val = draw(st.one_of(st.integers(min_value=0, max_value=10000), st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)))
        amount_json = str(amount_val)
    elif amount_type == "null":
        amount_json = "null"
    else:  # missing
        amount_json = None

    # Generate "name" nullable string or null or missing (name is nullable)
    name_type = draw(st.sampled_from(["string", "null", "missing"]))
    if name_type == "string":
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=15)))  # allow empty string
        if name_val is None:
            name_json = "null"
        else:
            name_json = json_str(name_val)
    elif name_type == "null":
        name_json = "null"
    else:
        name_json = None  # missing

    # Generate "status" enum or invalid or missing
    status_type = draw(st.sampled_from(["valid", "invalid", "missing", "null"]))
    if status_type == "valid":
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_json = json_str(status_val)
    elif status_type == "invalid":
        status_val = draw(st.sampled_from(STATUS_UNKNOWN_ENUMS))
        status_json = json_str(status_val)
    elif status_type == "null":
        status_json = "null"
    else:
        status_json = None  # missing

    # Generate "tags" array of strings (non-nullable)
    # Sometimes missing or null or wrong type (e.g. string instead of array)
    tags_type = draw(st.sampled_from(["array", "null", "missing", "string"]))
    if tags_type == "array":
        tags_len = draw(st.integers(min_value=0, max_value=MAX_TAGS))
        tags_list = draw(st.lists(st.text(min_size=1, max_size=MAX_TAG_LENGTH), min_size=tags_len, max_size=tags_len))
        tags_json = "[" + ",".join(json_str(t) for t in tags_list) + "]"
    elif tags_type == "null":
        tags_json = "null"
    elif tags_type == "string":
        # wrong type: string instead of array
        tags_json = json_str(draw(st.text(min_size=1, max_size=10)))
    else:
        tags_json = None  # missing

    # Generate "child" field: either null, missing, or a nested record (depth=1)
    # Nested record follows same rules but no further nesting (child.child always null or missing)
    child_type = draw(st.sampled_from(["object", "null", "missing"]))

    def gen_child_json():
        # Nested child with all fields present and valid except possibly one deviation
        # For child.child, always null or missing (to limit recursion)
        # We'll generate a valid nested record with small chance of one deviation

        # id int
        c_id = draw(st.integers(min_value=0, max_value=1000))

        # amount string only (to reduce complexity), but allow null or missing rarely
        c_amount_type = draw(st.sampled_from(["string", "null", "missing"]))
        if c_amount_type == "string":
            c_amount_val = draw(st.text(min_size=1, max_size=10))
            c_amount_json = json_str(c_amount_val)
        elif c_amount_type == "null":
            c_amount_json = "null"
        else:
            c_amount_json = None

        # name nullable string or null or missing
        c_name_type = draw(st.sampled_from(["string", "null", "missing"]))
        if c_name_type == "string":
            c_name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=15)))
            if c_name_val is None:
                c_name_json = "null"
            else:
                c_name_json = json_str(c_name_val)
        elif c_name_type == "null":
            c_name_json = "null"
        else:
            c_name_json = None

        # status valid only (to reduce complexity)
        c_status_val = draw(st.sampled_from(STATUS_VALUES))
        c_status_json = json_str(c_status_val)

        # tags array only (no null or missing)
        c_tags_len = draw(st.integers(min_value=0, max_value=MAX_TAGS))
        c_tags_list = draw(st.lists(st.text(min_size=1, max_size=MAX_TAG_LENGTH), min_size=c_tags_len, max_size=c_tags_len))
        c_tags_json = "[" + ",".join(json_str(t) for t in c_tags_list) + "]"

        # child.child always null or missing (never object)
        c_child_type = draw(st.sampled_from(["null", "missing"]))
        if c_child_type == "null":
            c_child_json = "null"
        else:
            c_child_json = None

        # Compose child.child field
        c_child_field = f'"child":{c_child_json}' if c_child_json is not None else None

        # Compose fields list, omit missing
        fields = [f'"id":{c_id}']
        if c_amount_json is not None:
            fields.append(f'"amount":{c_amount_json}')
        if c_name_json is not None:
            fields.append(f'"name":{c_name_json}')
        fields.append(f'"status":{c_status_json}')
        fields.append(f'"tags":{c_tags_json}')
        if c_child_field is not None:
            fields.append(c_child_field)

        return "{" + ",".join(fields) + "}"

    if child_type == "object":
        child_json = gen_child_json()
    elif child_type == "null":
        child_json = "null"
    else:
        child_json = None  # missing

    # Compose top-level fields, omit missing
    top_fields = [f'"id":{id_val}']
    if amount_json is not None:
        top_fields.append(f'"amount":{amount_json}')
    if name_json is not None:
        top_fields.append(f'"name":{name_json}')
    if status_json is not None:
        top_fields.append(f'"status":{status_json}')
    if tags_json is not None:
        top_fields.append(f'"tags":{tags_json}')
    if child_json is not None:
        top_fields.append(f'"child":{child_json}')

    json_text = "{" + ",".join(top_fields) + "}"

    return json_text.encode("utf-8")