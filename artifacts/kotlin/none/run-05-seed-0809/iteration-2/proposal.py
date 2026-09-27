from hypothesis import strategies as st

@st.composite
def generated_json(draw, _depth=0):
    # Limit recursion depth to 1 for "child" field
    # Base fields:
    # id: integer
    # amount: string
    # name: string or null
    # status: one of "active", "inactive", "unknown"
    # tags: array of strings
    # child: Record or null (one level recursion)
    #
    # Strategy: produce mostly well-formed documents, but vary one or two fields subtly:
    # - sometimes omit a field (to test missing vs present)
    # - sometimes put wrong type (e.g. number instead of string)
    # - sometimes null where string expected or vice versa
    # - sometimes empty array or array with nulls in tags
    # - sometimes child null or a nested record
    #
    # We produce JSON text manually by concatenation.
    #
    # To maximize divergence, we produce documents that are almost valid,
    # with one or two fields off in subtle ways.

    # Helpers to produce JSON string literals safely:
    def json_string(s):
        # Escape backslash and double quote, and control chars minimally
        # Hypothesis strings can contain anything, so escape carefully
        # We'll just replace backslash and double quote for simplicity
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        # Also replace control chars with \u escapes
        def esc_char(c):
            o = ord(c)
            if o < 0x20:
                return '\\u%04x' % o
            return c
        s = ''.join(esc_char(c) for c in s)
        return '"' + s + '"'

    # id: integer, but sometimes string or null to cause divergence
    id_choice = draw(st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),
        st.text(min_size=1, max_size=5).filter(lambda x: not x.isdigit()),  # non-digit string
        st.just("null"),
    ))

    # amount: string, but sometimes number or null
    amount_type = draw(st.sampled_from(["string", "number", "null"]))
    if amount_type == "string":
        amount_val = draw(st.text(min_size=1, max_size=10))
        amount = json_string(amount_val)
    elif amount_type == "number":
        # number as JSON number literal
        amount_val = draw(st.integers(min_value=-1000, max_value=1000))
        amount = str(amount_val)
    else:
        amount = "null"

    # name: string or null, sometimes number or missing
    name_type = draw(st.sampled_from(["string", "null", "number", "missing"]))
    if name_type == "string":
        name_val = draw(st.text(min_size=0, max_size=10))
        name = json_string(name_val)
    elif name_type == "null":
        name = "null"
    elif name_type == "number":
        name = str(draw(st.integers(min_value=-10, max_value=10)))
    else:
        name = None  # missing field

    # status: one of "active", "inactive", "unknown"
    # sometimes invalid string or null or missing
    status_type = draw(st.sampled_from(["valid", "invalid", "null", "missing"]))
    if status_type == "valid":
        status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
        status = json_string(status_val)
    elif status_type == "invalid":
        # invalid string
        status_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in {"active","inactive","unknown"}))
        status = json_string(status_val)
    elif status_type == "null":
        status = "null"
    else:
        status = None  # missing

    # tags: array of strings, sometimes null, sometimes array with null or number inside, sometimes missing
    tags_type = draw(st.sampled_from(["valid", "null", "mixed", "missing"]))
    if tags_type == "valid":
        # array of strings, possibly empty
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
        tags = "[" + ",".join(json_string(t) for t in tags_list) + "]"
    elif tags_type == "null":
        tags = "null"
    elif tags_type == "mixed":
        # array with strings and some null or numbers
        elems = []
        n = draw(st.integers(min_value=1, max_value=5))
        for _ in range(n):
            etype = draw(st.sampled_from(["string", "null", "number"]))
            if etype == "string":
                elems.append(json_string(draw(st.text(min_size=0, max_size=10))))
            elif etype == "null":
                elems.append("null")
            else:
                elems.append(str(draw(st.integers(min_value=-10, max_value=10))))
        tags = "[" + ",".join(elems) + "]"
    else:
        tags = None  # missing

    # child: null or nested record or missing
    if _depth >= 1:
        # no more recursion, only null or missing
        child_type = draw(st.sampled_from(["null", "missing"]))
    else:
        child_type = draw(st.sampled_from(["record", "null", "missing"]))
    if child_type == "record":
        child = generated_json(draw, _depth=_depth+1)
        # child is bytes, decode to str
        child_str = child.decode("utf-8")
    elif child_type == "null":
        child_str = "null"
    else:
        child_str = None  # missing

    # Build JSON object text
    # Compose fields, omit those with None (missing)
    fields = []

    # id always present, but we put it as string or null or invalid string sometimes
    fields.append('"id":' + id_choice)

    fields.append('"amount":' + amount)

    if name is not None:
        fields.append('"name":' + name)

    if status is not None:
        fields.append('"status":' + status)

    if tags is not None:
        fields.append('"tags":' + tags)

    if child_str is not None:
        fields.append('"child":' + child_str)

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")