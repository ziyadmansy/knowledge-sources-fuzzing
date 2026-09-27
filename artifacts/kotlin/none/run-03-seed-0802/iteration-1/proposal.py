from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper: produce a JSON string literal with possible escapes
    def json_string():
        # Use a restricted charset to avoid complex escaping
        # but include some edge chars to test escapes
        chars = st.characters(
            blacklist_characters=['\\', '"', '\b', '\f', '\n', '\r', '\t'],
            min_codepoint=0x20, max_codepoint=0x7E
        )
        # Occasionally produce empty string or null string (null is separate)
        return chars.filter(lambda s: s != '').map(
            lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
        )

    # Helper: produce a JSON string literal or null literal
    def json_string_or_null():
        # 20% chance null, 80% chance string
        return st.one_of(
            st.just("null"),
            json_string()
        )

    # Helper: produce a JSON array of strings (possibly empty)
    def json_string_array():
        # Array of 0 to 3 strings
        return st.lists(json_string(), max_size=3).map(
            lambda lst: "[" + ",".join(lst) + "]"
        )

    # Helper: produce a JSON integer literal (no quotes)
    def json_integer():
        # Use a range to test boundaries, including negatives and zero
        return st.integers(min_value=-1000, max_value=1000).map(str)

    # Helper: produce a JSON value for "status" field
    # Sometimes produce invalid status strings to test rejection
    def json_status():
        # 80% valid, 20% invalid string (quoted)
        valid = st.sampled_from(statuses)
        invalid = json_string()
        return st.one_of(valid, invalid)

    # Recursive helper to produce a "child" field value (either null or a record)
    # Limit recursion depth to 1 (child.child always null)
    def json_record(depth=0):
        # id: integer or sometimes string to test type divergence
        id_val = st.one_of(
            json_integer(),
            json_string()  # wrong type but quoted string
        )

        # amount: string (always string, but sometimes empty or numeric-looking)
        amount_val = json_string()

        # name: string or null or sometimes integer (wrong type)
        name_val = st.one_of(
            json_string_or_null(),
            json_integer()  # wrong type, unquoted integer
        )

        # status: mostly valid, sometimes invalid string
        status_val = json_status()

        # tags: array of strings or sometimes null (wrong type)
        tags_val = st.one_of(
            json_string_array(),
            st.just("null")
        )

        # child: null or nested record (only if depth==0)
        if depth == 0:
            child_val = st.one_of(
                st.just("null"),
                json_record(depth=1)
            )
        else:
            # depth 1: child always null
            child_val = st.just("null")

        # Compose fields in random order to test field order tolerance
        fields = [
            ("\"id\"", id_val),
            ("\"amount\"", amount_val),
            ("\"name\"", name_val),
            ("\"status\"", status_val),
            ("\"tags\"", tags_val),
            ("\"child\"", child_val),
        ]

        # Draw all field values
        drawn_fields = []
        for key, val_strat in fields:
            drawn_fields.append((key, draw(val_strat)))

        # Shuffle fields order
        drawn_fields = draw(st.permutations(drawn_fields))

        # Build JSON object text
        obj_text = "{" + ",".join(f"{k}:{v}" for k, v in drawn_fields) + "}"

        return obj_text

    # Generate top-level record JSON text
    record_text = draw(json_record(depth=0))

    # Return as bytes (UTF-8)
    return record_text.encode("utf-8")