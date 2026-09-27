from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal, possibly malformed
    def json_string():
        # Either a valid JSON string or a nearly valid one (e.g. unescaped control chars)
        # but keep it simple: valid or empty string or null or a number as string
        # To induce divergence, sometimes produce a number as string but unquoted
        choice = draw(st.integers(0, 9))
        if choice == 0:
            # valid string with quotes
            s = draw(st.text(alphabet=st.characters(blacklist_characters='"\\'), min_size=0, max_size=10))
            return '"' + s + '"'
        elif choice == 1:
            # null literal (valid)
            return "null"
        elif choice == 2:
            # unquoted string (invalid JSON but some libs might accept)
            s = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"{}[],:')))
            return s
        elif choice == 3:
            # number as string but unquoted (invalid JSON)
            n = draw(st.integers(-1000, 1000))
            return str(n)
        else:
            # valid empty string
            return '""'

    # Helper to produce a JSON string literal or null or malformed for "name"
    def name_field():
        # 70% chance valid string or null, 30% chance malformed variant
        p = draw(st.floats(0, 1))
        if p < 0.7:
            # valid string or null
            return json_string()
        else:
            # malformed: number, boolean, or missing quotes
            choice = draw(st.integers(0, 2))
            if choice == 0:
                # number literal
                return str(draw(st.integers(-1000, 1000)))
            elif choice == 1:
                # boolean literal
                return draw(st.sampled_from(["true", "false"]))
            else:
                # unquoted string without quotes
                s = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"{}[],:')))
                return s

    # Helper to produce the "status" field, mostly valid but sometimes invalid string or wrong type
    def status_field():
        p = draw(st.floats(0, 1))
        if p < 0.8:
            # valid status string
            return draw(st.sampled_from(STATUS_VALUES))
        elif p < 0.9:
            # invalid string (not one of the three)
            s = draw(st.text(min_size=1, max_size=8, alphabet=st.characters(blacklist_characters='"{}[],:')))
            return '"' + s + '"'
        else:
            # wrong type: number or boolean or null
            choice = draw(st.integers(0, 2))
            if choice == 0:
                return str(draw(st.integers(-10, 10)))
            elif choice == 1:
                return draw(st.sampled_from(["true", "false"]))
            else:
                return "null"

    # Helper to produce the "amount" field, which is a string but sometimes malformed
    def amount_field():
        # Mostly valid string, sometimes number or null or unquoted string
        p = draw(st.floats(0, 1))
        if p < 0.7:
            # valid string
            s = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
            return '"' + s + '"'
        elif p < 0.85:
            # null
            return "null"
        elif p < 0.95:
            # number literal (invalid for string field)
            return str(draw(st.integers(-1000, 1000)))
        else:
            # unquoted string (invalid JSON)
            s = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"{}[],:')))
            return s

    # Helper to produce the "id" field, which should be integer but sometimes malformed
    def id_field():
        p = draw(st.floats(0, 1))
        if p < 0.85:
            # valid integer
            return str(draw(st.integers(0, 10000)))
        elif p < 0.95:
            # string integer (invalid type)
            return '"' + str(draw(st.integers(0, 10000))) + '"'
        else:
            # float number (invalid type)
            return str(draw(st.floats(-1000, 1000)))

    # Helper to produce the "tags" array of strings
    def tags_field():
        p = draw(st.floats(0, 1))
        if p < 0.8:
            # valid array of strings
            n = draw(st.integers(0, 5))
            elems = []
            for _ in range(n):
                s = draw(st.text(min_size=0, max_size=8, alphabet=st.characters(blacklist_characters='"\\')))
                elems.append('"' + s + '"')
            return "[" + ",".join(elems) + "]"
        elif p < 0.9:
            # empty array but malformed element (number or null)
            elems = []
            n = draw(st.integers(1, 3))
            for _ in range(n):
                choice = draw(st.integers(0, 2))
                if choice == 0:
                    elems.append(str(draw(st.integers(-10, 10))))
                elif choice == 1:
                    elems.append("null")
                else:
                    s = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"{}[],:')))
                    elems.append(s)
            return "[" + ",".join(elems) + "]"
        else:
            # not an array: null or string or number
            choice = draw(st.integers(0, 2))
            if choice == 0:
                return "null"
            elif choice == 1:
                s = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"{}[],:')))
                return '"' + s + '"'
            else:
                return str(draw(st.integers(-10, 10)))

    # Recursive child field: either null or a nested record (one level max)
    def child_field(depth=0):
        if depth >= 1:
            # only null at max depth
            return "null"
        p = draw(st.floats(0, 1))
        if p < 0.6:
            return "null"
        else:
            # nested record with all fields valid or slightly malformed
            return record_field(depth + 1)

    # Compose a record JSON object string
    def record_field(depth=0):
        parts = []
        parts.append('"id":' + id_field())
        parts.append('"amount":' + amount_field())
        parts.append('"name":' + name_field())
        parts.append('"status":' + status_field())
        parts.append('"tags":' + tags_field())
        parts.append('"child":' + child_field(depth))
        return "{" + ",".join(parts) + "}"

    # Draw the top-level record
    json_text = record_field(0)
    return json_text.encode("utf-8")