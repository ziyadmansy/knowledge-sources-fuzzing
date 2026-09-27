from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper: produce a JSON string literal with proper escaping for simple ASCII only
    # (Hypothesis strings are unicode, but we restrict to safe ASCII for simplicity)
    def json_string(s: str) -> str:
        # Escape backslash and double quote only for safety
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return '"' + s + '"'

    # Generate a JSON string literal or null, with some chance of null
    def gen_name():
        # 20% null, else string of length 0-10 ASCII letters/digits/spaces
        return st.one_of(
            st.just("null"),
            st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['\\', '"']), min_size=0, max_size=10).map(json_string)
        )

    # Generate a JSON array of strings (tags)
    def gen_tags():
        # Array length 0-5, strings length 0-8 ASCII letters/digits/spaces, no escapes
        elem = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['\\', '"']), min_size=0, max_size=8).map(json_string)
        return st.lists(elem, min_size=0, max_size=5).map(lambda lst: "[" + ",".join(lst) + "]")

    # Generate the "status" field, sometimes invalid to provoke divergence:
    # - valid enum string
    # - invalid string (random string)
    # - number (wrong type)
    # - null (wrong type)
    def gen_status():
        # 70% valid enum, 10% invalid string, 10% number, 10% null
        valid = st.sampled_from(statuses)
        invalid_str = st.text(min_size=1, max_size=8, alphabet=st.characters(min_codepoint=97, max_codepoint=122)).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string)
        number = st.integers(min_value=-10, max_value=10).map(str)
        null = st.just("null")
        return st.one_of(
            valid,
            invalid_str,
            number,
            null,
        )

    # Generate the "amount" field, which is a string normally.
    # To provoke divergence, sometimes produce a number (wrong type),
    # or a string that looks like a number but with weird formatting.
    def gen_amount():
        # 80% string (normal), 10% number (wrong type), 10% string with weird chars
        normal_str = st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126).filter(lambda c: c not in ['\\', '"'])).map(json_string)
        number = st.integers(min_value=-1000, max_value=1000).map(str)
        weird_str = st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).map(json_string)
        return st.one_of(
            normal_str,
            number,
            weird_str,
        )

    # Generate the "id" field, which is an integer normally.
    # To provoke divergence, sometimes produce a string containing digits,
    # or a float number, or null.
    def gen_id():
        # 80% integer, 10% string digits, 5% float, 5% null
        integer = st.integers(min_value=0, max_value=100000).map(str)
        string_digits = st.integers(min_value=0, max_value=100000).map(lambda i: '"' + str(i) + '"')
        float_num = st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False).map(lambda f: format(f, '.2f'))
        null = st.just("null")
        return st.one_of(
            integer,
            string_digits,
            float_num,
            null,
        )

    # Generate the "child" field, which is either null or a nested record.
    # To bound recursion, pass a depth parameter.
    def gen_record(depth):
        # Compose fields except child first
        # id, amount, name, status, tags
        id_ = gen_id()
        amount = gen_amount()
        name = gen_name()
        status = gen_status()
        tags = gen_tags()

        # child: null or nested record (only one level of recursion normally)
        if depth <= 0:
            child = st.just("null")
        else:
            # 50% null, 50% nested record with depth-1
            child = st.one_of(
                st.just("null"),
                gen_record(depth - 1).map(lambda s: s.decode('utf-8'))
            )

        # Combine all fields into JSON object string
        def make_obj(fields):
            # fields is a tuple of strings for each field's JSON value
            id_v, amount_v, name_v, status_v, tags_v, child_v = fields
            # Compose JSON object string with all fields present
            # Order fixed for consistency
            return (
                '{'
                + '"id":' + id_v + ','
                + '"amount":' + amount_v + ','
                + '"name":' + name_v + ','
                + '"status":' + status_v + ','
                + '"tags":' + tags_v + ','
                + '"child":' + child_v
                + '}'
            )

        return st.tuples(id_, amount, name, status, tags, child).map(make_obj)

    # Generate top-level record with depth=1 (one level of recursion)
    json_str = draw(gen_record(depth=1))
    # Return as bytes UTF-8 encoded
    return json_str.encode('utf-8')