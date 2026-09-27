from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema:
    {
      "id": <integer>,
      "amount": <string>,
      "name": <string or null>,
      "status": <"active"|"inactive"|"unknown">,
      "tags": <array of strings>,
      "child": <Record or null>
    }
    with controlled variations to provoke divergence among four Dart JSON deserializers:
    - id: sometimes integer, sometimes float or exponent form (to trigger truncation or rejection)
    - amount: always string, numeric strings including fractional, or non-numeric strings
    - name: string or null (never missing)
    - status: always one of the three valid enums (to avoid universal rejection)
    - tags: array of strings, sometimes empty, sometimes null (to test built_value acceptance)
    - child: either null or a nested record (one level only)
    """
    # Helper to produce JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for quotes and backslash
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id variations: integer, float (decimal), float (exponent)
    id_type = draw(st.sampled_from(["int", "float_decimal", "float_exp"]))
    if id_type == "int":
        # 32-bit range plus some large values
        id_val = draw(st.integers(min_value=-2**40, max_value=2**40))
        id_json = str(id_val)
    elif id_type == "float_decimal":
        # float with decimal point but integral value or fractional
        # Use floats that are close to integers to test truncation
        base_int = draw(st.integers(min_value=-2**31, max_value=2**31))
        frac = draw(st.floats(min_value=0.1, max_value=0.9))
        val = float(base_int) + frac
        # Format with decimal point, no exponent
        id_json = ("%.6f" % val).rstrip('0').rstrip('.')
    else:  # float_exp
        # float in exponent notation, e.g. 1e3, -2.5e2
        base = draw(st.floats(min_value=1, max_value=1e6))
        exp = draw(st.integers(min_value=-10, max_value=10))
        val = base * (10 ** exp)
        # Format with exponent, forcing exponent notation
        id_json = ("%.6e" % val).replace('e+0', 'e+').replace('e-0', 'e-')

    # amount: string, numeric or non-numeric
    # numeric strings include integers, fractional, exponent forms as strings
    amount_type = draw(st.sampled_from(["numeric_int", "numeric_frac", "numeric_exp", "non_numeric"]))
    if amount_type == "numeric_int":
        amount_val = str(draw(st.integers(min_value=-10**10, max_value=10**10)))
    elif amount_type == "numeric_frac":
        amount_val = ("%.6f" % draw(st.floats(min_value=0.1, max_value=1e6))).rstrip('0').rstrip('.')
    elif amount_type == "numeric_exp":
        base = draw(st.floats(min_value=1, max_value=1e6))
        exp = draw(st.integers(min_value=-10, max_value=10))
        amount_val = ("%.6e" % (base * (10 ** exp))).replace('e+0', 'e+').replace('e-0', 'e-')
    else:
        # non-numeric string, possibly empty or with spaces
        amount_val = draw(st.text(min_size=0, max_size=20))

    amount_json = json_string(amount_val)

    # name: string or null (never missing)
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        # string with length 0-20, printable ascii excluding control chars and quotes/backslash
        name_str = draw(st.text(alphabet=st.characters(blacklist_characters=['"', '\\', '\n', '\r']), min_size=0, max_size=20))
        name_json = json_string(name_str)

    # status: one of the three valid enums (always valid to avoid universal rejection)
    status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
    status_json = json_string(status_val)

    # tags: array of strings, or null (to test built_value acceptance of null)
    tags_is_null = draw(st.booleans())
    if tags_is_null:
        tags_json = "null"
    else:
        # array of 0-5 strings, each string 0-10 chars, ascii printable excluding quotes/backslash
        tags_list = draw(st.lists(st.text(alphabet=st.characters(blacklist_characters=['"', '\\', '\n', '\r']), min_size=0, max_size=10), min_size=0, max_size=5))
        tags_json = "[" + ",".join(json_string(t) for t in tags_list) + "]"

    # child: null or nested record (one level only)
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json = "null"
    else:
        # nested record with all fields present, but no further nesting (child.child=null)
        # id: integer only (to reduce complexity)
        child_id = draw(st.integers(min_value=-2**40, max_value=2**40))
        child_id_json = str(child_id)

        # amount: numeric string integer only
        child_amount_val = str(draw(st.integers(min_value=-10**10, max_value=10**10)))
        child_amount_json = json_string(child_amount_val)

        # name: string or null
        child_name_is_null = draw(st.booleans())
        if child_name_is_null:
            child_name_json = "null"
        else:
            child_name_str = draw(st.text(alphabet=st.characters(blacklist_characters=['"', '\\', '\n', '\r']), min_size=0, max_size=20))
            child_name_json = json_string(child_name_str)

        # status: one of three valid enums
        child_status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
        child_status_json = json_string(child_status_val)

        # tags: array of strings (never null here)
        child_tags_list = draw(st.lists(st.text(alphabet=st.characters(blacklist_characters=['"', '\\', '\n', '\r']), min_size=0, max_size=10), min_size=0, max_size=3))
        child_tags_json = "[" + ",".join(json_string(t) for t in child_tags_list) + "]"

        # child.child: always null (no deeper nesting)
        child_child_json = "null"

        child_json = (
            "{" +
            '"id":' + child_id_json + "," +
            '"amount":' + child_amount_json + "," +
            '"name":' + child_name_json + "," +
            '"status":' + child_status_json + "," +
            '"tags":' + child_tags_json + "," +
            '"child":' + child_child_json +
            "}"
        )

    # Compose top-level JSON object with all fields present (no missing fields)
    # Order fields as per schema for readability
    json_obj = (
        "{" +
        '"id":' + id_json + "," +
        '"amount":' + amount_json + "," +
        '"name":' + name_json + "," +
        '"status":' + status_json + "," +
        '"tags":' + tags_json + "," +
        '"child":' + child_json +
        "}"
    )

    return json_obj.encode("utf-8")