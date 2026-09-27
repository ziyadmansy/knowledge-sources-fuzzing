from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for the schema
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Helper: produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for quotes and backslash
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Recursive generator for the "child" field, bounded to one level deep
    # To avoid infinite recursion, pass a depth parameter
    def gen_record(depth=0):
        # id: integer
        id_val = draw(st.integers(min_value=0, max_value=10**9))
        id_json = str(id_val)

        # amount: string representing a decimal number, but we will sometimes break it
        # to cause divergence, we produce either a valid decimal string or an invalid one
        # (e.g. empty string, or string with spaces)
        amount_valid = draw(st.booleans())
        if amount_valid:
            # valid decimal string: digits, optionally with decimal point and fraction
            int_part = draw(st.integers(min_value=0, max_value=10**6))
            frac_part = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=999999).map(lambda x: f"{x:06d}")))
            if frac_part is None:
                amount_str = str(int_part)
            else:
                # trim trailing zeros to increase variability
                frac_str = frac_part.rstrip('0')
                if frac_str == '':
                    amount_str = str(int_part)
                else:
                    amount_str = f"{int_part}.{frac_str}"
        else:
            # invalid decimal string: empty or spaces or letters
            amount_str = draw(st.one_of(st.just(""), st.just(" "), st.just("abc"), st.just("12 34"), st.just("1.2.3")))

        amount_json = json_string(amount_str)

        # name: string or null
        # To cause divergence, sometimes produce null, sometimes string, sometimes empty string
        name_choice = draw(st.integers(min_value=0, max_value=3))
        if name_choice == 0:
            name_json = "null"
        elif name_choice == 1:
            # valid string, possibly empty
            name_val = draw(st.text(min_size=0, max_size=10))
            name_json = json_string(name_val)
        elif name_choice == 2:
            # string with control chars or escapes to test parsers
            name_val = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters=['"','\\'])))
            # forcibly add backslash or quote to cause divergence
            name_val = name_val + ('\\' if draw(st.booleans()) else '"')
            name_json = json_string(name_val)
        else:
            # null again for balance
            name_json = "null"

        # status: one of "active", "inactive", "unknown"
        # To cause divergence, sometimes produce invalid string or null or number
        status_choice = draw(st.integers(min_value=0, max_value=5))
        if status_choice <= 2:
            status_json = STATUS_VALUES[status_choice]
        elif status_choice == 3:
            status_json = "null"
        elif status_choice == 4:
            status_json = '"invalid_status"'
        else:
            # number instead of string
            status_json = str(draw(st.integers(min_value=0, max_value=10)))

        # tags: array of strings
        # To cause divergence, sometimes produce array of strings, sometimes empty array,
        # sometimes array with null or numbers, sometimes missing (but missing is not allowed)
        tags_choice = draw(st.integers(min_value=0, max_value=4))
        if tags_choice == 0:
            # valid array of strings
            tag_count = draw(st.integers(min_value=0, max_value=3))
            tags_list = []
            for _ in range(tag_count):
                tag_str = draw(st.text(min_size=1, max_size=5))
                tags_list.append(json_string(tag_str))
            tags_json = "[" + ",".join(tags_list) + "]"
        elif tags_choice == 1:
            # empty array
            tags_json = "[]"
        elif tags_choice == 2:
            # array with null inside
            tags_json = "[null]"
        elif tags_choice == 3:
            # array with number inside
            tags_json = "[123]"
        else:
            # array with mixed types
            tags_json = "[" + ",".join([json_string(draw(st.text(min_size=1, max_size=3))) if draw(st.booleans()) else "null" for _ in range(draw(st.integers(min_value=1, max_value=3)))]) + "]"

        # child: either null or a nested record (one level only)
        if depth == 0:
            child_choice = draw(st.integers(min_value=0, max_value=3))
            if child_choice == 0:
                child_json = "null"
            elif child_choice == 1:
                # valid nested record
                child_json = gen_record(depth=1)
            elif child_choice == 2:
                # malformed child: missing fields (empty object)
                child_json = "{}"
            else:
                # child is a wrong type (number)
                child_json = str(draw(st.integers(min_value=0, max_value=1000)))
        else:
            # at depth 1, no further nesting
            child_json = "null"

        # Compose the JSON object string with all fields present (except malformed child cases)
        # To cause divergence, sometimes omit a field by replacing it with empty string (but spec says all fields always present)
        # So we keep all fields present, but sometimes with wrong types or values

        # Compose fields in fixed order
        fields = [
            '"id":' + id_json,
            '"amount":' + amount_json,
            '"name":' + name_json,
            '"status":' + status_json,
            '"tags":' + tags_json,
            '"child":' + child_json,
        ]

        json_obj = "{" + ",".join(fields) + "}"
        return json_obj

    # Generate top-level record JSON string
    json_text = gen_record(depth=0)

    # Return bytes as required
    return json_text.encode("utf-8")