from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal safely (no escapes, only simple ASCII)
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars (replace with \uXXXX)
        def esc_char(c):
            if c < ' ':
                return "\\u%04x" % ord(c)
            return c
        s = "".join(esc_char(c) for c in s)
        return '"' + s + '"'

    # Helper to produce a JSON value for a string or null, with some chance of null
    def gen_string_or_null():
        # To induce divergence, sometimes produce null, sometimes string, sometimes empty string
        # Also sometimes produce strings that look like numbers or booleans (to test type confusion)
        choice = draw(st.integers(min_value=0, max_value=9))
        if choice == 0:
            return "null"
        elif choice == 1:
            # string that looks like a number
            return json_string(draw(st.one_of(st.integers(min_value=-1000, max_value=1000).map(str),
                                             st.floats(allow_infinity=False, allow_nan=False).map(lambda f: format(f, '.6g')))))
        elif choice == 2:
            # string that looks like boolean
            return json_string(draw(st.sampled_from(["true", "false", "null"])))
        else:
            # normal string or empty string
            s = draw(st.text(min_size=0, max_size=20))
            return json_string(s)

    # Helper to produce a JSON array of strings (tags)
    def gen_tags():
        # To induce divergence, sometimes produce empty array, sometimes array with nulls or numbers as strings
        length = draw(st.integers(min_value=0, max_value=5))
        elements = []
        for _ in range(length):
            choice = draw(st.integers(min_value=0, max_value=4))
            if choice == 0:
                # normal string
                s = draw(st.text(min_size=1, max_size=10))
                elements.append(json_string(s))
            elif choice == 1:
                # empty string
                elements.append('""')
            elif choice == 2:
                # string that looks like number
                elements.append(json_string(draw(st.integers(min_value=-100, max_value=100).map(str))))
            elif choice == 3:
                # string that looks like boolean
                elements.append(json_string(draw(st.sampled_from(["true", "false", "null"]))))
            else:
                # null as element (not valid per schema, but might cause divergence)
                elements.append("null")
        return "[" + ",".join(elements) + "]"

    # Helper to produce a JSON value for status field (enum)
    def gen_status():
        # To induce divergence, sometimes produce invalid enum strings or null or numbers
        choice = draw(st.integers(min_value=0, max_value=6))
        if choice <= 2:
            # valid enum string
            return json_string(draw(st.sampled_from(statuses)))
        elif choice == 3:
            # invalid enum string
            return json_string(draw(st.text(min_size=1, max_size=10).filter(lambda x: x not in statuses)))
        elif choice == 4:
            # null (invalid per schema)
            return "null"
        elif choice == 5:
            # number instead of string
            return str(draw(st.integers(min_value=-10, max_value=10)))
        else:
            # boolean instead of string
            return draw(st.sampled_from(["true", "false"]))

    # Helper to produce a JSON value for amount (string)
    def gen_amount():
        # To induce divergence, sometimes produce numeric string, sometimes number, sometimes null
        choice = draw(st.integers(min_value=0, max_value=5))
        if choice == 0:
            # normal numeric string (positive or negative, decimals)
            s = draw(st.one_of(
                st.integers(min_value=-10000, max_value=10000).map(str),
                st.floats(min_value=-10000, max_value=10000, allow_infinity=False, allow_nan=False).map(lambda f: format(f, '.6g'))
            ))
            return json_string(s)
        elif choice == 1:
            # number (invalid per schema)
            return draw(st.one_of(
                st.integers(min_value=-10000, max_value=10000).map(str),
                st.floats(min_value=-10000, max_value=10000, allow_infinity=False, allow_nan=False).map(lambda f: format(f, '.6g'))
            ))
        elif choice == 2:
            # null (invalid per schema)
            return "null"
        elif choice == 3:
            # empty string
            return '""'
        else:
            # string that looks like boolean
            return json_string(draw(st.sampled_from(["true", "false", "null"])))

    # Helper to produce a JSON value for id (integer)
    def gen_id():
        # To induce divergence, sometimes produce integer, sometimes string integer, sometimes float, sometimes null
        choice = draw(st.integers(min_value=0, max_value=5))
        if choice == 0:
            # integer
            return str(draw(st.integers(min_value=0, max_value=1000000)))
        elif choice == 1:
            # string integer
            return json_string(str(draw(st.integers(min_value=0, max_value=1000000))))
        elif choice == 2:
            # float number
            return format(draw(st.floats(min_value=0, max_value=1000000, allow_infinity=False, allow_nan=False)), '.6g')
        elif choice == 3:
            # null (invalid)
            return "null"
        else:
            # string float
            return json_string(format(draw(st.floats(min_value=0, max_value=1000000, allow_infinity=False, allow_nan=False)), '.6g'))

    # Recursive generation of child record or null
    def gen_child(depth):
        if depth <= 0:
            # Only null or empty object (invalid but might cause divergence)
            choice = draw(st.integers(min_value=0, max_value=1))
            if choice == 0:
                return "null"
            else:
                # empty object (invalid)
                return "{}"
        else:
            # With some chance null, else a record
            choice = draw(st.integers(min_value=0, max_value=3))
            if choice == 0:
                return "null"
            else:
                # Generate a record with one level less depth
                return gen_record(depth - 1)

    # Generate a record JSON object string
    def gen_record(depth):
        # Compose fields in random order to test order sensitivity
        fields = []

        # id
        fields.append('"id":' + gen_id())

        # amount
        fields.append('"amount":' + gen_amount())

        # name
        fields.append('"name":' + gen_string_or_null())

        # status
        fields.append('"status":' + gen_status())

        # tags
        fields.append('"tags":' + gen_tags())

        # child
        fields.append('"child":' + gen_child(depth))

        # Shuffle fields order to test order sensitivity
        fields = draw(st.permutations(fields))

        return "{" + ",".join(fields) + "}"

    # Generate top-level record with depth 1 recursion
    json_text = gen_record(1)

    return json_text.encode("utf-8")