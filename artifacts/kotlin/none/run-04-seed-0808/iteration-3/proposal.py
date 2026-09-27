from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for the schema
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Escape backslash and double quote for JSON string
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Strategy for "amount" field: string, but try to produce edge cases
    # including numeric strings, empty string, strings with spaces, unicode, etc.
    amount_str = st.one_of(
        st.text(min_size=0, max_size=10),
        st.just("0"),
        st.just("0.0"),
        st.just("-0"),
        st.just("1234567890"),
        st.just("1e10"),
        st.just("NaN"),
        st.just("Infinity"),
        st.just(""),
        st.just(" "),
        st.just(" 123 "),
        st.just("null"),
        st.just("true"),
        st.just("false"),
    ).map(json_string_literal)

    # Strategy for "name" field: string or null
    # Include empty string, unicode, escaped chars, or null literal
    name_str = st.one_of(
        st.none(),
        st.text(min_size=0, max_size=15),
        st.just("null"),
        st.just(""),
        st.just(" "),
        st.just("null"),
        st.just("true"),
        st.just("false"),
    ).map(lambda v: "null" if v is None else json_string_literal(v))

    # Strategy for "status" field: one of the three strings or sometimes wrong type to induce divergence
    # We'll mostly produce correct values, but sometimes produce a string with typo or number or null
    status_correct = st.sampled_from(STATUS_VALUES)
    status_typo = st.sampled_from(['"activ"', '"inactiv"', '"unknwn"', '"ACTIVE"', '"Inactive"'])
    status_wrong_type = st.one_of(
        st.integers(min_value=-1, max_value=2).map(str),
        st.just("null"),
        st.just("true"),
        st.just("false"),
        st.just("123"),
    )
    status_field = st.one_of(
        status_correct,
        status_typo,
        status_wrong_type,
    )

    # Strategy for "tags": array of strings
    # Try empty array, array with empty strings, array with nulls (should be invalid), array with numbers (invalid)
    # But mostly valid arrays of strings
    tag_string = st.text(min_size=0, max_size=10).map(json_string_literal)
    tags_valid = st.lists(tag_string, min_size=0, max_size=5).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_invalid_null = st.lists(st.just("null"), min_size=1, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_invalid_number = st.lists(st.integers(min_value=0, max_value=10).map(str), min_size=1, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_field = st.one_of(
        tags_valid,
        tags_invalid_null,
        tags_invalid_number,
    )

    # Recursive strategy for "child" field: either null or a nested record (one level max)
    # We'll limit recursion depth to 1 by passing a parameter
    def record_json(depth=0):
        # id: integer (try boundary values and normal)
        id_field = st.one_of(
            st.integers(min_value=0, max_value=1000),
            st.just(-1),
            st.just(2**31-1),
            st.just(-2**31),
        ).map(str)

        # amount: from above
        amount_field = amount_str

        # name: from above
        name_field = name_str

        # status: from above
        status_field_local = status_field

        # tags: from above
        tags_field_local = tags_field

        # child: null or nested record if depth == 0, else only null
        if depth == 0:
            child_field = st.one_of(
                st.just("null"),
                st.deferred(lambda: record_json(depth=1))
            )
        else:
            child_field = st.just("null")

        # Compose JSON object string with one or two subtle errors:
        # - sometimes omit a field (to test missing field handling)
        # - sometimes put a field with wrong type (e.g. number instead of string)
        # - sometimes put a field as null when not allowed
        # We'll mostly produce all fields, but sometimes omit one field or replace one field with wrong type

        # Decide which field to possibly corrupt or omit (or none)
        corrupt_or_omit = st.one_of(
            st.just(None),
            st.sampled_from(["id", "amount", "name", "status", "tags", "child"]),
        )

        corrupt_type = st.one_of(
            st.just("omit"),
            st.just("wrong_type"),
            st.just("nullify"),
            st.just("none"),
        )

        corrupt_choice = st.tuples(corrupt_or_omit, corrupt_type)

        corrupt_field, corrupt_mode = draw(corrupt_choice)

        # Build fields dict with values or corrupted values
        fields = {}

        # id field
        if corrupt_field == "id" and corrupt_mode == "omit":
            pass  # omit id
        elif corrupt_field == "id" and corrupt_mode == "wrong_type":
            # put string instead of int
            fields["id"] = json_string_literal(draw(st.text(min_size=1, max_size=5)))
        elif corrupt_field == "id" and corrupt_mode == "nullify":
            fields["id"] = "null"
        else:
            fields["id"] = draw(id_field)

        # amount field
        if corrupt_field == "amount" and corrupt_mode == "omit":
            pass
        elif corrupt_field == "amount" and corrupt_mode == "wrong_type":
            # number instead of string
            fields["amount"] = draw(st.integers(min_value=-1000, max_value=1000).map(str))
        elif corrupt_field == "amount" and corrupt_mode == "nullify":
            fields["amount"] = "null"
        else:
            fields["amount"] = draw(amount_field)

        # name field
        if corrupt_field == "name" and corrupt_mode == "omit":
            pass
        elif corrupt_field == "name" and corrupt_mode == "wrong_type":
            # number instead of string or null
            fields["name"] = draw(st.integers(min_value=-1000, max_value=1000).map(str))
        elif corrupt_field == "name" and corrupt_mode == "nullify":
            fields["name"] = "null"
        else:
            fields["name"] = draw(name_field)

        # status field
        if corrupt_field == "status" and corrupt_mode == "omit":
            pass
        elif corrupt_field == "status" and corrupt_mode == "wrong_type":
            # number or boolean instead of string
            fields["status"] = draw(st.one_of(
                st.integers(min_value=0, max_value=10).map(str),
                st.just("true"),
                st.just("false"),
                st.just("null"),
            ))
        elif corrupt_field == "status" and corrupt_mode == "nullify":
            fields["status"] = "null"
        else:
            fields["status"] = draw(status_field_local)

        # tags field
        if corrupt_field == "tags" and corrupt_mode == "omit":
            pass
        elif corrupt_field == "tags" and corrupt_mode == "wrong_type":
            # string or number instead of array
            fields["tags"] = draw(st.one_of(
                json_string_literal(draw(st.text(min_size=0, max_size=10))),
                st.integers(min_value=0, max_value=10).map(str),
                st.just("null"),
            ))
        elif corrupt_field == "tags" and corrupt_mode == "nullify":
            fields["tags"] = "null"
        else:
            fields["tags"] = draw(tags_field_local)

        # child field
        if corrupt_field == "child" and corrupt_mode == "omit":
            pass
        elif corrupt_field == "child" and corrupt_mode == "wrong_type":
            # string or number instead of object or null
            fields["child"] = draw(st.one_of(
                json_string_literal(draw(st.text(min_size=0, max_size=10))),
                st.integers(min_value=0, max_value=10).map(str),
            ))
        elif corrupt_field == "child" and corrupt_mode == "nullify":
            fields["child"] = "null"
        else:
            fields["child"] = draw(child_field)

        # Compose JSON object string
        # Fields must appear in order: id, amount, name, status, tags, child
        # Omitted fields are skipped
        parts = []
        for key in ["id", "amount", "name", "status", "tags", "child"]:
            if key in fields:
                parts.append(f'"{key}":{fields[key]}')

        json_obj = "{" + ",".join(parts) + "}"
        return json_obj

    # Draw the top-level record JSON string
    json_text = draw(record_json(depth=0))
    return json_text.encode("utf-8")