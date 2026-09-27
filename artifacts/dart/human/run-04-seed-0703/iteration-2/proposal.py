from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = st.sampled_from(["active", "inactive", "unknown"])
    # Tags: array of strings
    tags_str = st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5)
    # name: string or null
    name_str = st.one_of(st.none(), st.text(min_size=0, max_size=20))
    # amount: string (always present)
    amount_str = st.text(min_size=0, max_size=20)
    # id: integer or double (to trigger divergence)
    # We want to produce either:
    # - an int within 64-bit range (accepted by all)
    # - a double that is an integer value (accepted by all)
    # - a double outside 64-bit int range (accepted by json_serializable/freezed but not manual/built_value)
    # - a double with fractional part (should be rejected by all)
    # We'll pick from these cases with weights to maximize divergence chances.
    id_case = draw(st.sampled_from([
        "int64_in_range",
        "double_int64_in_range",
        "double_int64_out_of_range",
        "double_fractional"
    ]))
    if id_case == "int64_in_range":
        # int in 64-bit range
        id_val = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
        id_json = str(id_val)
    elif id_case == "double_int64_in_range":
        # double with integer value in 64-bit range
        int_val = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
        # Represent as float with .0
        id_json = str(float(int_val))
    elif id_case == "double_int64_out_of_range":
        # double with integer value outside 64-bit range
        # Use values just outside 64-bit range to trigger saturation in toInt()
        # Use a float literal (e.g. 1e20)
        # But jsonDecode will parse 1e20 as double
        # We'll pick a large number > 2**63
        large_val = draw(st.one_of(
            st.just(2**63 + 1),
            st.just(-(2**63) - 1),
            st.integers(min_value=2**63 + 1, max_value=10**20),
            st.integers(min_value=-(10**20), max_value=-(2**63) - 1)
        ))
        id_json = str(float(large_val))
    else:
        # double with fractional part (should be rejected by all)
        # pick a float with fractional part
        frac_val = draw(st.floats(min_value=-1e10, max_value=1e10, allow_infinity=False, allow_nan=False))
        # Ensure fractional part is nonzero
        if frac_val == int(frac_val):
            frac_val += 0.1
        id_json = repr(frac_val)

    # status: always valid string or sometimes invalid string to test rejection
    # But invalid status rejected by all, so no divergence from that
    # We'll keep it valid to focus on other fields
    status_val = draw(statuses)

    # tags: sometimes missing (to trigger built_value acceptance vs others rejection)
    # or present as empty or non-empty array of strings
    tags_missing = draw(st.booleans())
    if not tags_missing:
        tags_val = draw(tags_str)
    else:
        tags_val = None  # missing

    # name: nullable string, missing not allowed (always present)
    name_val = draw(name_str)

    # amount: string, always present
    amount_val = draw(amount_str)

    # child: nullable record or null
    # To keep recursion bounded, only one level of recursion allowed
    # We'll produce either null or a record with child=null
    child_null = draw(st.booleans())
    if child_null:
        child_val = None
    else:
        # child record with all fields present and valid, no further recursion
        child_id = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
        child_amount = draw(st.text(min_size=0, max_size=20))
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        child_status = draw(statuses)
        child_tags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))
        child_val = {
            "id": child_id,
            "amount": child_amount,
            "name": child_name,
            "status": child_status,
            "tags": child_tags,
            "child": None
        }

    # Compose JSON text manually with string concatenation
    # Helper to encode JSON string literals safely (escape quotes and backslashes)
    def json_str(s):
        if s is None:
            return "null"
        # Escape backslash and double quote and control chars
        esc = s.replace("\\", "\\\\").replace("\"", "\\\"")
        # Escape control chars (U+0000 to U+001F)
        esc2 = []
        for c in esc:
            if ord(c) < 0x20:
                esc2.append(f"\\u{ord(c):04x}")
            else:
                esc2.append(c)
        return '"' + "".join(esc2) + '"'

    # Compose tags JSON array or omit field if missing
    if tags_val is None:
        tags_json = None
    else:
        tags_json = "[" + ",".join(json_str(t) for t in tags_val) + "]"

    # Compose child JSON or null
    if child_val is None:
        child_json = "null"
    else:
        child_json = (
            "{"
            + f"\"id\":{child_val['id']},"
            + f"\"amount\":{json_str(child_val['amount'])},"
            + f"\"name\":{json_str(child_val['name'])},"
            + f"\"status\":{json_str(child_val['status'])},"
            + f"\"tags\":[{','.join(json_str(t) for t in child_val['tags'])}],"
            + "\"child\":null"
            + "}"
        )

    # Compose top-level JSON object fields
    fields = [
        f"\"id\":{id_json}",
        f"\"amount\":{json_str(amount_val)}",
        f"\"name\":{json_str(name_val)}",
        f"\"status\":{json_str(status_val)}",
    ]
    if tags_json is not None:
        fields.append(f"\"tags\":{tags_json}")
    # else omit tags field to test built_value acceptance vs others rejection

    fields.append(f"\"child\":{child_json}")

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")