from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    valid_statuses = ["active", "inactive", "unknown"]
    # Add some invalid enum strings to cause divergence
    invalid_statuses = ["Active", "INACTIVE", "unknown ", "actve", "null", "", "123"]

    # Helper: generate a JSON string literal with proper escaping for quotes and backslashes
    def json_string(s: str) -> str:
        # minimal escaping for " and \ and control chars
        # Hypothesis strings are unicode, but we keep it simple here
        s = s.replace("\\", "\\\\").replace("\"", "\\\"")
        # Also escape control chars \b \f \n \r \t for safety
        s = s.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f"\"{s}\""

    # Recursive generator for the "child" field, bounded to one level deep normally
    # We allow null or a nested record (one level)
    # To keep control, we pass a depth parameter
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # id: int or sometimes num (float) to cause divergence on id type
        # Manual and built_value require int strictly
        # json_serializable and freezed accept any num and convert to int
        # So we generate int mostly, but sometimes float with .0 or .5 to cause divergence
        id_int = st.integers(min_value=0, max_value=1_000_000)
        id_float = st.floats(min_value=0, max_value=1_000_000, allow_infinity=False, allow_nan=False).filter(lambda x: x != int(x))
        id_choice = st.one_of(id_int, id_float)

        # amount: always string, but sometimes numeric string to test
        amount_str = st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in "\"\\\b\f\n\r\t"))
        # name: nullable string, manual requires present (null or string), others allow missing
        # We will generate present always here to keep baseline well-formedness
        name_str = st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in "\"\\\b\f\n\r\t")))
        # status: mostly valid enum strings, sometimes invalid to cause divergence
        status_valid = st.sampled_from(valid_statuses)
        status_invalid = st.sampled_from(invalid_statuses)
        # We bias towards valid but sometimes invalid
        status_choice = st.one_of(status_valid, status_invalid)

        # tags: list of strings, manual expects List<String>, others map List<dynamic> to String
        # We generate list of strings mostly, but sometimes list with non-string elements to cause divergence
        tag_str = st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in "\"\\\b\f\n\r\t"))
        tags_valid = st.lists(tag_str, min_size=0, max_size=5)
        # Introduce non-string elements: numbers, bools, null
        tags_invalid = st.lists(st.one_of(
            tag_str,
            st.integers(min_value=0, max_value=100),
            st.booleans(),
            st.none(),
            st.floats(allow_infinity=False, allow_nan=False)
        ), min_size=0, max_size=5)
        tags_choice = st.one_of(tags_valid, tags_invalid)

        # child: null or nested record if depth==0, else null only (to limit recursion)
        if depth > 0:
            child_choice = st.just("null")
        else:
            child_choice = st.one_of(st.just("null"), record_json(depth=1))

        # Compose fields with some variations to cause divergence
        # We will sometimes omit nullable fields (name, child) to cause divergence between manual (requires present) and others (allow missing)
        # We will sometimes put wrong types in fields to cause divergence

        # Decide on name field presence and type
        # Manual requires present (nullable string)
        # built_value tolerates missing (sets null)
        # json_serializable and freezed tolerate missing
        # So omitting name causes manual to reject, others accept
        name_present = draw(st.booleans())
        if name_present:
            name_val = draw(name_str)
            if name_val is None:
                name_json = "null"
            else:
                name_json = json_string(name_val)
        else:
            name_json = None  # omit field

        # Decide on child field presence and type
        # Same logic as name
        child_present = draw(st.booleans())
        if child_present:
            child_json = draw(child_choice)
        else:
            child_json = None  # omit field

        # id field: sometimes int, sometimes float (to cause divergence)
        id_val = draw(id_choice)
        if isinstance(id_val, float):
            # Format float with decimal point
            id_json = f"{id_val:.1f}"
        else:
            id_json = str(id_val)

        # amount: always string, but sometimes empty string or numeric string
        amount_val = draw(amount_str)
        amount_json = json_string(amount_val)

        # status: mostly valid, sometimes invalid
        status_val = draw(status_choice)
        status_json = json_string(status_val)

        # tags: sometimes all strings, sometimes mixed types
        tags_val = draw(tags_choice)
        # Serialize tags array as JSON array
        def serialize_tag(t):
            if t is None:
                return "null"
            elif isinstance(t, bool):
                return "true" if t else "false"
            elif isinstance(t, (int, float)):
                # Format floats with decimal point if needed
                if isinstance(t, float):
                    return f"{t:.1f}"
                else:
                    return str(t)
            else:
                # string
                return json_string(str(t))
        tags_json = "[" + ",".join(serialize_tag(t) for t in tags_val) + "]"

        # Compose JSON object fields, controlling order for readability
        # Manual requires all fields present (id, amount, name, status, tags, child)
        # built_value tolerates missing name and child
        # json_serializable and freezed tolerate missing name and child
        # We omit name and/or child sometimes to cause divergence

        fields = []
        fields.append(f"\"id\":{id_json}")
        fields.append(f"\"amount\":{amount_json}")
        if name_json is not None:
            fields.append(f"\"name\":{name_json}")
        if status_json is not None:
            fields.append(f"\"status\":{status_json}")
        fields.append(f"\"tags\":{tags_json}")
        if child_json is not None:
            fields.append(f"\"child\":{child_json}")

        json_obj = "{" + ",".join(fields) + "}"

        return json_obj

    # Generate top-level record JSON string
    json_str = draw(record_json(depth=0))
    # Return bytes as required
    return json_str.encode("utf-8")