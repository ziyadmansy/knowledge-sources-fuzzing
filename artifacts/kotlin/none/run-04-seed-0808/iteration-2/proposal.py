from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal with proper escaping of " and \ only (minimal)
    def json_string(s: str) -> str:
        # Minimal escaping for " and \ only
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return '"' + s + '"'

    # Helper: produce a JSON array of strings
    def json_array_of_strings(lst):
        return "[" + ",".join(json_string(x) for x in lst) + "]"

    # Recursive generator for a Record JSON text, with bounded depth
    def record_json(depth=0):
        # We want to produce "almost" well-formed documents with 0 or 1 subtle divergence per doc.
        # So we produce a mostly valid record, then with some probability introduce one subtle divergence:
        # - wrong type for one field (e.g. number instead of string)
        # - missing field (instead of present)
        # - null where not expected or vice versa
        # - enum field with invalid string or number
        # - array with wrong element types
        # - child field null or nested record (one level max)
        # We do NOT produce multiple errors per doc to maximize disagreement.

        # Base valid fields
        # id: integer
        # amount: string
        # name: string or null
        # status: one of "active", "inactive", "unknown"
        # tags: array of strings
        # child: record or null (one level recursion max)

        # Decide which field to "break" or if none (valid)
        # We pick one field to break or none (valid) with weighted chance
        fields = ["id", "amount", "name", "status", "tags", "child"]
        break_field = draw(st.one_of(st.none(), st.sampled_from(fields)))

        # id field
        def gen_id():
            if break_field == "id":
                # break id: produce string or null or float instead of int
                choice = draw(st.sampled_from(["string", "null", "float"]))
                if choice == "string":
                    return json_string(draw(st.text(min_size=1, max_size=5)))
                elif choice == "null":
                    return "null"
                else:
                    # float as number with decimal point
                    return str(draw(st.floats(allow_nan=False, allow_infinity=False, width=32)))
            else:
                # valid int
                return str(draw(st.integers(min_value=0, max_value=2**31-1)))

        # amount field
        def gen_amount():
            if break_field == "amount":
                # break amount: produce number, null, or missing (missing handled outside)
                choice = draw(st.sampled_from(["number", "null", "missing"]))
                if choice == "missing":
                    return None
                elif choice == "null":
                    return "null"
                else:
                    # number as string without quotes
                    return str(draw(st.floats(allow_nan=False, allow_infinity=False, width=32)))
            else:
                # valid string
                return json_string(draw(st.text(min_size=1, max_size=10)))

        # name field
        def gen_name():
            if break_field == "name":
                # break name: produce number, boolean, or missing
                choice = draw(st.sampled_from(["number", "bool", "missing"]))
                if choice == "missing":
                    return None
                elif choice == "number":
                    return str(draw(st.integers(min_value=-1000, max_value=1000)))
                else:
                    return draw(st.sampled_from(["true", "false"]))
            else:
                # valid string or null
                val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
                if val is None:
                    return "null"
                else:
                    return json_string(val)

        # status field
        def gen_status():
            if break_field == "status":
                # break status: produce invalid enum string, number, null, or missing
                choice = draw(st.sampled_from(["invalid_enum", "number", "null", "missing"]))
                if choice == "missing":
                    return None
                elif choice == "invalid_enum":
                    # invalid enum string (not in allowed)
                    invalid = draw(st.text(min_size=1, max_size=10).filter(lambda x: x not in statuses))
                    return json_string(invalid)
                elif choice == "null":
                    return "null"
                else:
                    # number
                    return str(draw(st.integers(min_value=0, max_value=10)))
            else:
                # valid enum string
                return json_string(draw(st.sampled_from(statuses)))

        # tags field
        def gen_tags():
            if break_field == "tags":
                # break tags: produce array with non-string elements, null, or missing
                choice = draw(st.sampled_from(["nonstring", "null", "missing"]))
                if choice == "missing":
                    return None
                elif choice == "null":
                    return "null"
                else:
                    # array with at least one non-string element (int or bool)
                    length = draw(st.integers(min_value=1, max_value=5))
                    elems = []
                    # at least one non-string element
                    nonstring_pos = draw(st.integers(min_value=0, max_value=length-1))
                    for i in range(length):
                        if i == nonstring_pos:
                            # non-string element
                            elem = draw(st.one_of(
                                st.integers(min_value=-100, max_value=100).map(str),
                                st.sampled_from(["true", "false"])
                            ))
                        else:
                            # string element
                            elem = json_string(draw(st.text(min_size=0, max_size=5)))
                        elems.append(elem)
                    return "[" + ",".join(elems) + "]"
            else:
                # valid array of strings (possibly empty)
                length = draw(st.integers(min_value=0, max_value=5))
                elems = [json_string(draw(st.text(min_size=0, max_size=5))) for _ in range(length)]
                return "[" + ",".join(elems) + "]"

        # child field
        def gen_child():
            if break_field == "child":
                # break child: produce invalid type (string, number, bool), or missing
                choice = draw(st.sampled_from(["string", "number", "bool", "missing"]))
                if choice == "missing":
                    return None
                elif choice == "string":
                    return json_string(draw(st.text(min_size=1, max_size=10)))
                elif choice == "number":
                    return str(draw(st.integers(min_value=-1000, max_value=1000)))
                else:
                    return draw(st.sampled_from(["true", "false"]))
            else:
                # valid: null or nested record (only one level recursion)
                if depth >= 1:
                    # no further recursion, only null
                    return "null"
                else:
                    # 50% chance null or nested record
                    if draw(st.booleans()):
                        return "null"
                    else:
                        return record_json(depth=depth+1)

        # Compose fields, skipping missing fields if any
        id_val = gen_id()
        amount_val = gen_amount()
        name_val = gen_name()
        status_val = gen_status()
        tags_val = gen_tags()
        child_val = gen_child()

        # Build JSON object string with fields present except those marked None (missing)
        # Order fields always same for consistency
        parts = []
        parts.append('"id":' + id_val)
        if amount_val is not None:
            parts.append('"amount":' + amount_val)
        if name_val is not None:
            parts.append('"name":' + name_val)
        if status_val is not None:
            parts.append('"status":' + status_val)
        if tags_val is not None:
            parts.append('"tags":' + tags_val)
        if child_val is not None:
            parts.append('"child":' + child_val)

        json_obj = "{" + ",".join(parts) + "}"
        return json_obj

    # Draw the top-level record JSON string
    json_text = record_json(depth=0)
    # Return as bytes (UTF-8)
    return json_text.encode("utf-8")