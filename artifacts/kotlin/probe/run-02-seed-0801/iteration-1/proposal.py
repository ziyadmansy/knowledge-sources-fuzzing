from hypothesis import strategies as st

# Helper: JSON string escaping for minimal safe output (only escape backslash and double quote)
def json_string_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON documents as bytes, with controlled variations to provoke
    behavioral divergence among Gson, Moshi, kotlinx.serialization, and Jackson.

    The document schema:
    {
      "id": <integer or string convertible to integer>,
      "amount": <string or number (some accept number, some reject)>,
      "name": <string or null or other types (some accept coercion)>,
      "status": <"active"|"inactive"|"unknown" or invalid or null>,
      "tags": <array of strings, or array with non-string elements, or null elements>,
      "child": <nested record or null or empty object or missing>
    }

    Strategy:
    - Start from a valid base document with all fields well-formed.
    - Introduce at most one or two small "off" variations per document to maximize divergence.
    - Variations chosen based on known differences from the problem statement.
    """

    # Base valid values for fields
    base_id_int = draw(st.integers(min_value=0, max_value=1000))
    # id can be int or string convertible to int
    id_as_int = draw(st.booleans())
    if id_as_int:
        id_val = str(base_id_int)
        id_json = id_val  # as number
    else:
        id_json = '"' + id_val + '"'  # as string

    # amount: string or number (kotlinx rejects number)
    # We'll pick either string or number here, sometimes number to provoke divergence
    amount_is_number = draw(st.booleans())
    if amount_is_number:
        # number as int or float string
        amount_num = draw(st.one_of(st.integers(min_value=0, max_value=10000), st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)))
        # JSON number formatting: floats must be formatted without trailing .0 if integral
        if isinstance(amount_num, float):
            # Format float with minimal decimal places
            amount_json = repr(amount_num)
        else:
            amount_json = str(amount_num)
    else:
        # amount as string (always accepted)
        amount_str = draw(st.text(min_size=1, max_size=10))
        amount_json = '"' + json_string_escape(amount_str) + '"'

    # name: string or null or other types (Gson/Jackson accept number/boolean as string, Moshi/kotlinx reject)
    # We'll pick one of these types to provoke divergence
    name_type = draw(st.sampled_from(["string", "null", "number", "boolean"]))
    if name_type == "string":
        name_str = draw(st.text(min_size=0, max_size=20))
        name_json = '"' + json_string_escape(name_str) + '"'
    elif name_type == "null":
        name_json = "null"
    elif name_type == "number":
        name_num = draw(st.one_of(st.integers(min_value=-1000, max_value=1000), st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
        if isinstance(name_num, float):
            name_json = repr(name_num)
        else:
            name_json = str(name_num)
    else:  # boolean
        name_bool = draw(st.booleans())
        name_json = "true" if name_bool else "false"

    # status: exact enum strings or invalid or null
    # Gson accepts invalid enum as null, others reject
    status_val = draw(st.sampled_from(["active", "inactive", "unknown", "invalid_enum", "null"]))
    if status_val == "null":
        status_json = "null"
    elif status_val == "invalid_enum":
        # invalid enum string
        status_json = '"invalid"'
    else:
        status_json = '"' + status_val + '"'

    # tags: array of strings normally
    # Variations:
    # - all strings (accepted by all)
    # - some non-string elements (Gson, Moshi, Jackson accept with conversion; kotlinx rejects)
    # - some null elements (Gson, Moshi, Jackson accept; kotlinx rejects)
    tags_type = draw(st.sampled_from(["all_strings", "non_string_elements", "null_elements"]))
    if tags_type == "all_strings":
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        tags_json = "[" + ",".join('"' + json_string_escape(t) + '"' for t in tags_list) + "]"
    elif tags_type == "non_string_elements":
        # Mix strings and numbers/booleans
        tags_list = draw(st.lists(st.one_of(
            st.text(min_size=0, max_size=10).map(lambda s: ('"' + json_string_escape(s) + '"')),
            st.integers(min_value=-100, max_value=100).map(str),
            st.booleans().map(lambda b: "true" if b else "false")
        ), min_size=1, max_size=5))
        tags_json = "[" + ",".join(tags_list) + "]"
    else:  # null_elements
        # Mix strings and nulls
        tags_list = draw(st.lists(st.one_of(
            st.text(min_size=0, max_size=10).map(lambda s: ('"' + json_string_escape(s) + '"')),
            st.just("null")
        ), min_size=1, max_size=5))
        tags_json = "[" + ",".join(tags_list) + "]"

    # child: nested record or null or empty object or missing
    # Variations:
    # - null (accepted by all)
    # - missing (omit field)
    # - empty object {} (accepted only by Gson)
    # - nested record with same rules, but limit recursion depth to 1
    child_option = draw(st.sampled_from(["null", "missing", "empty_object", "nested_record"]))

    # To avoid infinite recursion, define a helper for nested record generation with depth=1
    def gen_child_record(depth=1):
        # At depth=1, child.child must be null or missing (no further recursion)
        # We'll reuse the same field generation but fix child to null or missing
        # Use simpler variations to keep size small
        # id: int or string
        child_id_int = draw(st.integers(min_value=0, max_value=1000))
        child_id_as_int = draw(st.booleans())
        if child_id_as_int:
            child_id_json = str(child_id_int)
        else:
            child_id_json = '"' + str(child_id_int) + '"'

        # amount: string or number (same rules)
        child_amount_is_number = draw(st.booleans())
        if child_amount_is_number:
            child_amount_num = draw(st.one_of(st.integers(min_value=0, max_value=10000), st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)))
            if isinstance(child_amount_num, float):
                child_amount_json = repr(child_amount_num)
            else:
                child_amount_json = str(child_amount_num)
        else:
            child_amount_str = draw(st.text(min_size=1, max_size=10))
            child_amount_json = '"' + json_string_escape(child_amount_str) + '"'

        # name: string or null only (to reduce complexity)
        child_name_is_null = draw(st.booleans())
        if child_name_is_null:
            child_name_json = "null"
        else:
            child_name_str = draw(st.text(min_size=0, max_size=20))
            child_name_json = '"' + json_string_escape(child_name_str) + '"'

        # status: exact enum or invalid or null (to provoke divergence)
        child_status_val = draw(st.sampled_from(["active", "inactive", "unknown", "invalid_enum", "null"]))
        if child_status_val == "null":
            child_status_json = "null"
        elif child_status_val == "invalid_enum":
            child_status_json = '"invalid"'
        else:
            child_status_json = '"' + child_status_val + '"'

        # tags: all strings or null elements (avoid non-string elements to keep simpler)
        child_tags_type = draw(st.sampled_from(["all_strings", "null_elements"]))
        if child_tags_type == "all_strings":
            child_tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))
            child_tags_json = "[" + ",".join('"' + json_string_escape(t) + '"' for t in child_tags_list) + "]"
        else:
            child_tags_list = draw(st.lists(st.one_of(
                st.text(min_size=0, max_size=10).map(lambda s: ('"' + json_string_escape(s) + '"')),
                st.just("null")
            ), min_size=1, max_size=3))
            child_tags_json = "[" + ",".join(child_tags_list) + "]"

        # child.child: null or missing (no recursion)
        child_child_option = draw(st.sampled_from(["null", "missing"]))
        if child_child_option == "null":
            child_child_json = '"child":null'
        else:
            child_child_json = None

        fields = [
            '"id":' + child_id_json,
            '"amount":' + child_amount_json,
            '"name":' + child_name_json,
            '"status":' + child_status_json,
            '"tags":' + child_tags_json,
        ]
        if child_child_json is not None:
            fields.append(child_child_json)
        # Compose child record JSON object
        return "{" + ",".join(fields) + "}"

    if child_option == "null":
        child_json = '"child":null'
    elif child_option == "missing":
        child_json = None
    elif child_option == "empty_object":
        # "{}" accepted only by Gson for child
        child_json = '"child":{}'
    else:  # nested_record
        nested = gen_child_record(depth=1)
        child_json = '"child":' + nested

    # Compose top-level JSON object fields
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
    ]
    if child_json is not None:
        fields.append(child_json)

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")