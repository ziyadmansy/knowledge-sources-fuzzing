from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    valid_statuses = ["active", "inactive", "unknown"]
    # Add some invalid enum strings to test enum decoding divergence
    enum_candidates = valid_statuses + ["Active", "INACTIVE", "unkn0wn", "", "null", "active "]

    # Helper: generate a JSON string literal with proper escaping for quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Minimal escaping: backslash and quote
        esc = s.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{esc}\""

    # Helper: generate JSON array of strings
    def json_array_of_strings(lst):
        # lst is list of strings
        return "[" + ",".join(json_string_literal(x) for x in lst) + "]"

    # Recursive record generator, bounded depth 1 (child can be null or record with child=null)
    def gen_record(depth=0):
        # id: int or num (to test divergence)
        # Manual and built_value require int strictly
        # json_serializable and freezed accept any num and convert to int
        # We'll generate either int or float with integral value to test divergence
        id_is_int = draw(st.booleans())
        if id_is_int:
            id_val = draw(st.integers(min_value=-(2**31), max_value=2**31-1))
            id_json = str(id_val)
        else:
            # float with integral value (e.g. 42.0)
            integral = draw(st.integers(min_value=-(2**31), max_value=2**31-1))
            id_val = float(integral)
            # Represent as JSON number with decimal point
            id_json = f"{integral}.0"

        # amount: string (always present)
        amount_val = draw(st.text(min_size=1, max_size=10))
        amount_json = json_string_literal(amount_val)

        # name: nullable string, present always for manual, optional for others
        # To test divergence, sometimes omit name field (allowed for json_serializable/freezed/built_value)
        # But manual requires present (nullable)
        # So we vary presence and nullness
        name_present = draw(st.booleans())
        if name_present:
            name_is_null = draw(st.booleans())
            if name_is_null:
                name_json = "null"
            else:
                name_val = draw(st.text(min_size=0, max_size=10))
                name_json = json_string_literal(name_val)
        else:
            name_json = None  # omitted

        # status: enum string, test valid and invalid strings
        status_val = draw(st.sampled_from(enum_candidates))
        status_json = json_string_literal(status_val)

        # tags: array of strings, always present
        # To test divergence, sometimes put non-string elements (e.g. numbers) to test manual strictness
        tags_len = draw(st.integers(min_value=0, max_value=4))
        tags = []
        for _ in range(tags_len):
            # 80% chance string, 20% chance number (to test divergence)
            if draw(st.floats(min_value=0, max_value=1)) < 0.8:
                tag_str = draw(st.text(min_size=0, max_size=8))
                tags.append(json_string_literal(tag_str))
            else:
                # number as JSON number string
                num_val = draw(st.integers(min_value=-100, max_value=100))
                tags.append(str(num_val))
        tags_json = "[" + ",".join(tags) + "]"

        # child: null or nested record (only one level recursion)
        # built_value tolerates missing child (sets null)
        # manual requires present (nullable)
        child_present = draw(st.booleans())
        if child_present:
            # 50% null, 50% nested record with child=null
            if draw(st.booleans()):
                child_json = "null"
            else:
                # nested record with child=null (to avoid deeper recursion)
                nested_id = draw(st.integers(min_value=-(2**31), max_value=2**31-1))
                nested_amount = draw(st.text(min_size=1, max_size=10))
                nested_name_present = draw(st.booleans())
                if nested_name_present:
                    nested_name_is_null = draw(st.booleans())
                    if nested_name_is_null:
                        nested_name_json = "null"
                    else:
                        nested_name_val = draw(st.text(min_size=0, max_size=10))
                        nested_name_json = json_string_literal(nested_name_val)
                else:
                    nested_name_json = None

                nested_status_val = draw(st.sampled_from(enum_candidates))
                nested_status_json = json_string_literal(nested_status_val)

                nested_tags_len = draw(st.integers(min_value=0, max_value=3))
                nested_tags = []
                for _ in range(nested_tags_len):
                    nested_tag_str = draw(st.text(min_size=0, max_size=8))
                    nested_tags.append(json_string_literal(nested_tag_str))
                nested_tags_json = "[" + ",".join(nested_tags) + "]"

                # child null for nested
                nested_fields = [
                    f"\"id\":{nested_id}",
                    f"\"amount\":{json_string_literal(nested_amount)}",
                ]
                if nested_name_json is not None:
                    nested_fields.append(f"\"name\":{nested_name_json}")
                else:
                    # omit name field to test divergence
                    pass
                nested_fields.append(f"\"status\":{nested_status_json}")
                nested_fields.append(f"\"tags\":{nested_tags_json}")
                nested_fields.append(f"\"child\":null")

                child_json = "{" + ",".join(nested_fields) + "}"
        else:
            child_json = None  # omitted

        # Compose top-level fields
        fields = [f"\"id\":{id_json}", f"\"amount\":{amount_json}"]

        if name_json is not None:
            fields.append(f"\"name\":{name_json}")
        # else omit name field

        fields.append(f"\"status\":{status_json}")
        fields.append(f"\"tags\":{tags_json}")

        if child_json is not None:
            fields.append(f"\"child\":{child_json}")
        # else omit child field

        json_obj = "{" + ",".join(fields) + "}"

        return json_obj.encode("utf-8")

    return gen_record()