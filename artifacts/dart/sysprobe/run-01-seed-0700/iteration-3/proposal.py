from hypothesis import strategies as st

# Helper: JSON string escape for double quotes and backslash only (minimal safe subset)
def json_string_escape(s: str) -> str:
    # Only escape backslash and double quote for JSON string safety
    return s.replace("\\", "\\\\").replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to maximize behavioral divergence among four Dart JSON deserializers.
    """

    # Constants for enum "status"
    statuses = ["active", "inactive", "unknown"]

    # id: integer normally, but allow floats and exponent forms to trigger divergence
    # We produce the JSON text for "id" ourselves to control integer vs float vs exponent forms.
    # Strategy: mostly integers, sometimes floats or exponent notation as strings (but valid JSON numbers).
    id_type = draw(st.sampled_from(["int", "float", "exponent"]))
    if id_type == "int":
        # 32-bit and 64-bit range integers, including boundary values
        id_val = draw(st.one_of(
            st.integers(min_value=-(2**31), max_value=2**31-1),
            st.integers(min_value=-(2**63), max_value=2**63-1),
        ))
        id_json = str(id_val)
    elif id_type == "float":
        # float with fractional part, e.g. 123.0 or -0.5
        # Use a float that is not integral to distinguish from int
        f = draw(st.floats(min_value=-1e6, max_value=1e6, allow_infinity=False, allow_nan=False))
        # Avoid integral floats to keep float form
        if f == int(f):
            f += 0.1
        id_json = repr(f)
    else:  # exponent
        # exponent form, e.g. 1e3, -2.5e2
        base = draw(st.floats(min_value=1, max_value=1e6, allow_infinity=False, allow_nan=False))
        exp = draw(st.integers(min_value=-10, max_value=10))
        # Compose exponent string manually, forcing float form
        # Use lower-case 'e' to match JSON number syntax
        id_json = f"{base}e{exp}"

    # amount: string, numeric strings including fractional, but also test empty string or unusual numeric strings
    # Also test some borderline strings that might confuse parsers
    amount_numeric_str = draw(st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789.-+" for c in s)),
        st.just("0"),
        st.just("123.456"),
        st.just("-0.001"),
        st.just("1e3"),
        st.just("+42"),
        st.just("000123"),
        st.just("0.0"),
    ))
    # Also allow some non-numeric strings to test rejection (but all implementations require string, so no null)
    amount_non_numeric_str = draw(st.one_of(
        st.just("NaN"),
        st.just("Infinity"),
        st.just(""),
        st.just("abc123"),
        st.just(" 123 "),
    ))
    # Choose mostly numeric strings but sometimes non-numeric
    amount_val = draw(st.one_of(
        st.just(amount_numeric_str),
        st.just(amount_non_numeric_str),
    ))

    # name: string or null (null allowed only here)
    # Test empty string, unicode, and null
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20),
        st.just(""),
        st.just("null"),  # string "null" to distinguish from null
        st.just("名前"),  # unicode example
    ))

    # status: enum, always one of the three valid strings, but also test case variants to cause rejection
    # To maximize divergence, mostly valid, sometimes invalid case variants
    status_val = draw(st.one_of(
        st.sampled_from(statuses),
        st.sampled_from(["ACTIVE", "Inactive", "Unknown", "actIve", "inActive"]),
        st.just(""),  # empty string invalid
        st.just("unknown "),  # trailing space invalid
    ))

    # tags: array of strings, always present (except test built_value accepts null or missing)
    # To trigger divergence, sometimes omit tags, sometimes null, sometimes empty list, sometimes list with empty string
    tags_option = draw(st.sampled_from(["present", "null", "missing"]))
    if tags_option == "present":
        # list of strings, including empty string and unicode
        tags_list = draw(st.lists(st.one_of(
            st.text(min_size=0, max_size=10),
            st.just(""),
            st.just("tag1"),
            st.just("タグ"),
        ), min_size=0, max_size=5))
        # Compose JSON array string
        tags_json = "[" + ",".join('"' + json_string_escape(t) + '"' for t in tags_list) + "]"
        tags_present = True
    elif tags_option == "null":
        tags_json = "null"
        tags_present = True
    else:  # missing
        tags_present = False

    # child: null or nested Record (one level recursion only)
    # To keep bounded recursion, child is either null or a shallow record with no child
    child_option = draw(st.sampled_from(["null", "present", "missing"]))
    if child_option == "null":
        child_json = "null"
        child_present = True
    elif child_option == "present":
        # Compose a shallow child record with no child field (to test missing child in nested)
        # Use minimal valid fields, mostly valid values
        child_id = draw(st.integers(min_value=0, max_value=1000))
        child_amount = draw(st.just("0.0"))
        child_name = draw(st.one_of(st.none(), st.just("child")))
        child_status = draw(st.sampled_from(statuses))
        child_tags = draw(st.lists(st.text(min_size=1, max_size=5), min_size=0, max_size=2))
        # Compose child tags JSON array
        child_tags_json = "[" + ",".join('"' + json_string_escape(t) + '"' for t in child_tags) + "]"
        # Compose child JSON object, omit "child" field to test missing child in nested
        child_fields = [
            '"id":' + str(child_id),
            '"amount":"' + json_string_escape(child_amount) + '"',
            '"name":' + ("null" if child_name is None else '"' + json_string_escape(child_name) + '"'),
            '"status":"' + child_status + '"',
            '"tags":' + child_tags_json,
            # no "child" field here
        ]
        child_json = "{" + ",".join(child_fields) + "}"
        child_present = True
    else:  # missing
        child_present = False

    # Compose top-level JSON object fields as strings
    fields = []

    # "id" always present
    fields.append('"id":' + id_json)

    # "amount" always present as string
    fields.append('"amount":"' + json_string_escape(amount_val) + '"')

    # "name" always present (null allowed)
    fields.append('"name":' + ("null" if name_val is None else '"' + json_string_escape(name_val) + '"'))

    # "status" always present as string (may be invalid)
    fields.append('"status":"' + json_string_escape(status_val) + '"')

    # "tags" field presence depends on tags_present
    if tags_present:
        fields.append('"tags":' + tags_json)

    # "child" field presence depends on child_present
    if child_present:
        fields.append('"child":' + child_json)

    # To trigger divergence on missing fields, sometimes omit "tags" or "child" (tags missing allowed only by built_value)
    # "name" missing is always rejected, so never omit "name"
    # "id", "amount", "status" always present (required)
    # "tags" and "child" may be omitted to test divergence

    # Compose final JSON object string
    json_text = "{" + ",".join(fields) + "}"

    # Return as bytes
    return json_text.encode("utf-8")