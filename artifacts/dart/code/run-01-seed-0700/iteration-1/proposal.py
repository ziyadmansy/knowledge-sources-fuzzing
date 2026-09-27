from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    valid_statuses = ["active", "inactive", "unknown"]
    # Also include some invalid enum strings to test enum decoding differences
    enum_candidates = valid_statuses + ["Active", "INACTIVE", "unknown ", "invalid", "", "null", "123"]

    # Helper: generate a JSON string literal with proper escaping for simple ASCII subset
    # We only generate ASCII printable chars except control chars and quotes/backslash
    # to keep JSON valid and simple.
    def json_string_literal(s: str) -> str:
        # Escape backslash and double quote
        s = s.replace("\\", "\\\\").replace("\"", "\\\"")
        # Escape control chars (none generated here, but just in case)
        s = s.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f"\"{s}\""

    # Generate id field:
    # Manual and built_value require int strictly
    # json_serializable and freezed accept any num and convert to int
    # So generate either int or float with fractional part to cause divergence
    # Also try large int values and negative values to test boundaries
    id_type = draw(st.sampled_from(["int", "float"]))
    if id_type == "int":
        id_val = draw(st.integers(min_value=-2**31, max_value=2**31-1))
        id_json = str(id_val)
    else:
        # float with fractional part to cause manual and built_value to reject
        # but json_serializable/freezed accept by toInt()
        # Use floats that are not integral
        float_val = draw(st.floats(min_value=-1e6, max_value=1e6, allow_infinity=False, allow_nan=False))
        # Ensure fractional part
        if float_val == int(float_val):
            float_val += 0.5
        id_json = repr(float_val)

    # Generate amount field: must be string always
    # Try normal strings and numeric strings to test no divergence but keep valid
    amount_str = draw(st.text(min_size=1, max_size=10))
    amount_json = json_string_literal(amount_str)

    # Generate name field:
    # Manual requires present (nullable)
    # json_serializable, freezed, built_value allow missing or null
    # To cause divergence, sometimes omit name field (built_value accepts, others reject)
    # or present with null or string
    name_option = draw(st.sampled_from(["present_string", "present_null", "missing"]))
    if name_option == "present_string":
        name_val = draw(st.text(min_size=0, max_size=10))
        name_json = json_string_literal(name_val)
        name_field = f"\"name\":{name_json}"
    elif name_option == "present_null":
        name_field = "\"name\":null"
    else:
        # missing field
        name_field = None

    # Generate status field:
    # Manual uses Enum.values.byName (throws raw ArgumentError on unknown)
    # json_serializable/freezed throw CheckedFromJsonException on unknown
    # built_value wraps ArgumentError in built_value error
    # So generate valid enum strings and invalid variants to cause divergence
    status_val = draw(st.sampled_from(enum_candidates))
    status_json = json_string_literal(status_val)

    # Generate tags field:
    # Must be array of strings
    # Manual expects List<String>
    # json_serializable/freezed map List<dynamic> to String
    # built_value expects BuiltList<String>
    # To cause divergence, try empty list, list of strings, or list with non-string
    tags_option = draw(st.sampled_from(["all_strings", "some_nonstring"]))
    if tags_option == "all_strings":
        tags_list = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=5))
        tags_json_items = [json_string_literal(t) for t in tags_list]
    else:
        # Insert one non-string element (number or null) to cause divergence
        tags_list = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=4))
        non_str_elem = draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.just("null")))
        # Represent non_str_elem as JSON literal
        if non_str_elem == "null":
            non_str_json = "null"
        elif isinstance(non_str_elem, int):
            non_str_json = str(non_str_elem)
        else:
            # float
            non_str_json = repr(non_str_elem)
        tags_json_items = [json_string_literal(t) for t in tags_list] + [non_str_json]
    tags_json = "[" + ",".join(tags_json_items) + "]"

    # Generate child field:
    # Manual requires present (nullable)
    # json_serializable/freezed allow missing or null
    # built_value omits if null, tolerates missing
    # To cause divergence, sometimes omit child, sometimes present null, sometimes present nested record
    child_option = draw(st.sampled_from(["missing", "null", "nested"]))

    # To avoid infinite recursion, limit recursion depth to 1 (top-level + one child)
    # So nested child record fields must be well-formed but no further child nesting
    def gen_child_record():
        # id int strictly (to avoid too many divergences inside child)
        child_id = draw(st.integers(min_value=-2**31, max_value=2**31-1))
        child_id_json = str(child_id)
        child_amount = draw(st.text(min_size=1, max_size=10))
        child_amount_json = json_string_literal(child_amount)
        # name present string or null (always present to avoid too many divergences inside child)
        child_name_val = draw(st.one_of(st.text(min_size=0, max_size=10), st.just(None)))
        if child_name_val is None:
            child_name_json = "null"
        else:
            child_name_json = json_string_literal(child_name_val)
        # status valid enum only to avoid enum divergence inside child
        child_status_val = draw(st.sampled_from(valid_statuses))
        child_status_json = json_string_literal(child_status_val)
        # tags all strings
        child_tags_list = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=3))
        child_tags_json_items = [json_string_literal(t) for t in child_tags_list]
        child_tags_json = "[" + ",".join(child_tags_json_items) + "]"
        # child null (no further nesting)
        child_child_json = "null"
        # Compose child record JSON object with all fields present
        child_fields = [
            f"\"id\":{child_id_json}",
            f"\"amount\":{child_amount_json}",
            f"\"name\":{child_name_json}",
            f"\"status\":{child_status_json}",
            f"\"tags\":{child_tags_json}",
            f"\"child\":{child_child_json}",
        ]
        return "{" + ",".join(child_fields) + "}"

    if child_option == "missing":
        child_field = None
    elif child_option == "null":
        child_field = "\"child\":null"
    else:
        child_field = "\"child\":" + gen_child_record()

    # Compose top-level JSON object fields
    fields = [f"\"id\":{id_json}", f"\"amount\":{amount_json}", f"\"status\":{status_json}", f"\"tags\":{tags_json}"]
    if name_field is not None:
        fields.append(name_field)
    if child_field is not None:
        fields.append(child_field)

    # Shuffle fields order to avoid positional bias
    fields = draw(st.permutations(fields))

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")