from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Helper: produce a JSON string literal (with quotes)
    # Use Hypothesis's built-in text with safe chars for JSON strings
    def json_string():
        # Use a restricted charset to avoid escaping complexity
        # Allow empty string too
        return st.text(
            alphabet=st.characters(
                blacklist_characters=['\\', '"', '\b', '\f', '\n', '\r', '\t'],
                min_codepoint=0x20,
                max_codepoint=0x7E,
            ),
            min_size=0,
            max_size=20,
        ).map(lambda s: '"' + s + '"')

    # Helper: produce a JSON number literal as string (integer only)
    # Use integers in a range that might stress parsing (including zero and negatives)
    def json_int_string():
        return st.integers(min_value=-1000, max_value=1000).map(str)

    # Helper: produce a JSON array of strings (each string as JSON string literal)
    def json_string_array():
        # Array length 0..3 to keep size small
        return st.lists(json_string(), min_size=0, max_size=3).map(
            lambda lst: '[' + ','.join(lst) + ']'
        )

    # Helper: produce a JSON value for "name" field: either null or string
    # To induce divergence, sometimes produce null, sometimes string, sometimes empty string
    def json_name_value():
        # 40% null, 50% string, 10% empty string (as "")
        choice = draw(st.integers(min_value=1, max_value=100))
        if choice <= 40:
            return 'null'
        elif choice <= 90:
            return draw(json_string())
        else:
            return '""'

    # Helper: produce a JSON value for "status" field
    # To induce divergence, sometimes produce correct enum string,
    # sometimes produce a string with different casing or misspelling,
    # sometimes produce null (which is invalid but might be accepted differently)
    def json_status_value():
        choice = draw(st.integers(min_value=1, max_value=100))
        if choice <= 70:
            # correct enum
            return draw(st.sampled_from(STATUS_VALUES))
        elif choice <= 85:
            # incorrect casing or misspelling
            variants = ['"Active"', '"INACTIVE"', '"unkn0wn"', '"actve"', '"unknown "']
            return draw(st.sampled_from(variants))
        elif choice <= 95:
            # null (invalid per schema)
            return 'null'
        else:
            # number instead of string
            return draw(json_int_string())

    # Helper: produce a JSON value for "child" field
    # Either null or a nested record (one level only)
    # To induce divergence, sometimes produce null, sometimes a nested record,
    # sometimes an empty object {}, sometimes a wrong type (string or number)
    def json_child_value(depth=0):
        choice = draw(st.integers(min_value=1, max_value=100))
        if choice <= 50:
            # null child
            return 'null'
        elif choice <= 80 and depth == 0:
            # nested record (one level only)
            return draw(record_json(depth=depth+1))
        elif choice <= 90:
            # empty object (invalid but might be accepted differently)
            return '{}'
        elif choice <= 95:
            # string instead of object/null
            return draw(json_string())
        else:
            # number instead of object/null
            return draw(json_int_string())

    # Compose a record JSON object string
    @st.composite
    def record_json(draw, depth=0):
        # id: integer as number (no quotes)
        id_val = draw(st.integers(min_value=0, max_value=10000))
        id_str = str(id_val)

        # amount: string representing a decimal number, but sometimes malformed
        # To induce divergence, sometimes produce a valid decimal string,
        # sometimes a string with letters, sometimes empty string
        amount_choice = draw(st.integers(min_value=1, max_value=100))
        if amount_choice <= 70:
            # valid decimal string (e.g. "123.45")
            whole = draw(st.integers(min_value=0, max_value=10000))
            frac = draw(st.integers(min_value=0, max_value=99))
            amount_str = f'"{whole}.{frac:02d}"'
        elif amount_choice <= 85:
            # string with letters (invalid decimal)
            amount_str = draw(json_string())
        else:
            # empty string
            amount_str = '""'

        # name: string or null
        name_str = json_name_value()

        # status: enum string or variants
        status_str = json_status_value()

        # tags: array of strings
        tags_str = draw(json_string_array())

        # child: null or nested record or variants
        child_str = json_child_value(depth=depth)

        # Build JSON object string with fields in fixed order for consistency
        obj = (
            '{'
            f'"id":{id_str},'
            f'"amount":{amount_str},'
            f'"name":{name_str},'
            f'"status":{status_str},'
            f'"tags":{tags_str},'
            f'"child":{child_str}'
            '}'
        )
        return obj

    # Draw the top-level record JSON string
    json_obj_str = draw(record_json())

    # Return as bytes
    return json_obj_str.encode('utf-8')