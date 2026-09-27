from hypothesis import strategies as st

@st.composite
def generated_json(draw, _depth=0):
    # Limit recursion depth to 1 for "child" field (one level of recursion normally)
    max_depth = 1

    # Helper to produce JSON string for a string value, including null or invalid strings
    def json_string(draw):
        # Sometimes produce null, sometimes a valid JSON string, sometimes an invalid JSON string (e.g. unescaped control chars)
        choice = draw(st.integers(min_value=0, max_value=9))
        if choice == 0:
            # null literal
            return "null"
        elif choice <= 7:
            # valid JSON string with possible unicode and escapes
            s = draw(st.text(
                alphabet=st.characters(blacklist_characters=['"', '\\', '\b', '\f', '\n', '\r', '\t']),
                min_size=0, max_size=20))
            # escape backslash and quote
            s_escaped = s.replace('\\', '\\\\').replace('"', '\\"')
            return '"' + s_escaped + '"'
        else:
            # invalid JSON string: unescaped control characters or unescaped quote inside
            s = draw(st.text(min_size=1, max_size=10))
            # insert an unescaped quote or control char randomly
            pos = draw(st.integers(min_value=0, max_value=len(s)-1))
            bad_char = draw(st.sampled_from(['"', '\n', '\r', '\t']))
            s = s[:pos] + bad_char + s[pos+1:]
            return '"' + s + '"'

    # Helper to produce JSON string for "amount" field (string)
    def json_amount(draw):
        # amount is string, but try to produce edge cases: numeric strings, empty, null, invalid string
        choice = draw(st.integers(min_value=0, max_value=9))
        if choice == 0:
            return "null"
        elif choice <= 7:
            # valid string representing a number or empty string
            s = draw(st.one_of(
                st.text(alphabet=st.characters(min_codepoint=48, max_codepoint=57), min_size=0, max_size=10),  # digits only or empty
                st.just("0"),
                st.just(""),
                st.text(min_size=1, max_size=10)
            ))
            s_escaped = s.replace('\\', '\\\\').replace('"', '\\"')
            return '"' + s_escaped + '"'
        else:
            # invalid string with unescaped quote or control char
            s = draw(st.text(min_size=1, max_size=10))
            pos = draw(st.integers(min_value=0, max_value=len(s)-1))
            bad_char = draw(st.sampled_from(['"', '\n', '\r', '\t']))
            s = s[:pos] + bad_char + s[pos+1:]
            return '"' + s + '"'

    # Helper to produce JSON string for "name" field (string or null)
    def json_name(draw):
        # name can be null or string or invalid string
        return json_string(draw)

    # Helper to produce JSON string for "status" field (one of "active", "inactive", "unknown")
    def json_status(draw):
        # Sometimes produce valid enum string, sometimes null, sometimes invalid string, sometimes number
        choice = draw(st.integers(min_value=0, max_value=9))
        if choice == 0:
            return "null"
        elif choice <= 6:
            val = draw(st.sampled_from(['"active"', '"inactive"', '"unknown"']))
            return val
        elif choice == 7:
            # invalid enum string
            s = draw(st.text(min_size=1, max_size=10))
            s_escaped = s.replace('\\', '\\\\').replace('"', '\\"')
            return '"' + s_escaped + '"'
        else:
            # number instead of string
            n = draw(st.integers(min_value=-100, max_value=100))
            return str(n)

    # Helper to produce JSON string for "tags" field (array of strings)
    def json_tags(draw):
        # tags is array of strings, but try edge cases: empty array, null, array with null elements, array with invalid strings
        choice = draw(st.integers(min_value=0, max_value=9))
        if choice == 0:
            return "null"
        else:
            # array length 0..5
            length = draw(st.integers(min_value=0, max_value=5))
            elems = []
            for _ in range(length):
                # each element can be string, null, or invalid string
                elem_choice = draw(st.integers(min_value=0, max_value=9))
                if elem_choice == 0:
                    elems.append("null")
                elif elem_choice <= 7:
                    s = draw(st.text(
                        alphabet=st.characters(blacklist_characters=['"', '\\', '\b', '\f', '\n', '\r', '\t']),
                        min_size=0, max_size=10))
                    s_escaped = s.replace('\\', '\\\\').replace('"', '\\"')
                    elems.append('"' + s_escaped + '"')
                else:
                    # invalid string with unescaped quote or control char
                    s = draw(st.text(min_size=1, max_size=10))
                    pos = draw(st.integers(min_value=0, max_value=len(s)-1))
                    bad_char = draw(st.sampled_from(['"', '\n', '\r', '\t']))
                    s = s[:pos] + bad_char + s[pos+1:]
                    elems.append('"' + s + '"')
            return "[" + ",".join(elems) + "]"

    # Helper to produce JSON string for "child" field (Record or null)
    def json_child(draw, depth):
        if depth >= max_depth:
            # only null or empty object (invalid for schema but to test divergence)
            choice = draw(st.integers(min_value=0, max_value=2))
            if choice == 0:
                return "null"
            else:
                # empty object
                return "{}"
        else:
            # 80% chance null, 20% chance nested record
            choice = draw(st.integers(min_value=0, max_value=9))
            if choice < 8:
                return "null"
            else:
                return generated_json(draw, _depth=depth+1)

    # id: integer, but try edge cases: number as string, null, float, string, missing (we cannot omit fields, so no missing)
    # We must produce all six fields always present, so no missing fields.
    # But we can produce invalid types.
    def json_id(draw):
        choice = draw(st.integers(min_value=0, max_value=9))
        if choice == 0:
            # null
            return "null"
        elif choice <= 6:
            # valid integer
            n = draw(st.integers(min_value=-2**31, max_value=2**31-1))
            return str(n)
        elif choice == 7:
            # float number
            f = draw(st.floats(allow_nan=False, allow_infinity=False, width=32))
            # format float without exponent to avoid JSON parsing issues
            s = format(f, 'f')
            return s
        else:
            # string containing a number or garbage
            s = draw(st.one_of(
                st.text(alphabet=st.characters(min_codepoint=48, max_codepoint=57), min_size=1, max_size=10),
                st.text(min_size=1, max_size=10)
            ))
            s_escaped = s.replace('\\', '\\\\').replace('"', '\\"')
            return '"' + s_escaped + '"'

    # Compose the JSON object string with all fields in order
    id_str = json_id(draw)
    amount_str = json_amount(draw)
    name_str = json_name(draw)
    status_str = json_status(draw)
    tags_str = json_tags(draw)
    child_str = json_child(draw, _depth)

    # Build JSON text with all fields present, no extra whitespace (to keep minimal)
    json_text = (
        '{'
        '"id":' + id_str + ','
        '"amount":' + amount_str + ','
        '"name":' + name_str + ','
        '"status":' + status_str + ','
        '"tags":' + tags_str + ','
        '"child":' + child_str +
        '}'
    )

    return json_text.encode('utf-8')