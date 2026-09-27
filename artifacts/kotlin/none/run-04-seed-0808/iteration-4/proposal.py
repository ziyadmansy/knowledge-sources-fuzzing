from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum as JSON strings
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with proper escaping for quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Escape backslash and double quote
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Strategy for "amount": string, but sometimes inject edge cases (empty, numeric strings, whitespace)
    amount_str = st.one_of(
        st.text(min_size=0, max_size=10).map(json_string_literal),
        st.just('""'),  # empty string explicitly
        st.sampled_from(['"0"', '"-0"', '"123.45"', '" 123 "', '"\t\n"']),
    )

    # Strategy for "name": either null or string (including empty and some edge cases)
    name_str = st.one_of(
        st.just("null"),
        st.text(min_size=0, max_size=10).map(json_string_literal),
        st.sampled_from(['""', '"null"', '"\\u0000"', '"\\n"']),
    )

    # Strategy for "status": sometimes valid enum strings, sometimes invalid strings or wrong types
    # To maximize disagreement, sometimes produce invalid enum strings or numbers as strings
    status_str = st.one_of(
        st.sampled_from(statuses),
        st.text(min_size=1, max_size=8).filter(lambda x: x not in ['active', 'inactive', 'unknown']).map(json_string_literal),
        st.integers(min_value=-1, max_value=2).map(str),  # numbers as raw JSON (no quotes)
    )

    # Strategy for "tags": array of strings, sometimes empty, sometimes with null or wrong types inside
    # To maximize disagreement, sometimes inject null or numbers inside the array
    def tags_array():
        # Elements can be string literals, or sometimes null or numbers (as JSON literals)
        elem = st.one_of(
            st.text(min_size=0, max_size=5).map(json_string_literal),
            st.just("null"),
            st.integers(min_value=-10, max_value=10).map(str),
        )
        # Array length 0 to 3 for bounded size
        return st.lists(elem, min_size=0, max_size=3).map(
            lambda elems: "[" + ",".join(elems) + "]"
        )

    # Recursive strategy for "child": either null or a nested record (one level deep max)
    # To avoid deep recursion, child can only be null or a record with child=null
    @st.composite
    def record(draw, allow_child=True):
        # id: integer as JSON number, sometimes inject edge cases (0, negative, large)
        id_val = draw(st.integers(min_value=-10, max_value=1000))
        id_json = str(id_val)

        amount_json = draw(amount_str)
        name_json = draw(name_str)

        # For status, to maximize disagreement, sometimes produce invalid JSON types (string, number, or invalid string)
        # But to keep mostly one thing off at a time, 80% chance valid enum, 20% chance invalid
        if draw(st.booleans()):
            status_json = draw(st.sampled_from(statuses))
        else:
            status_json = draw(status_str)

        tags_json = draw(tags_array())

        if allow_child:
            # 50% chance null, 50% chance nested record with child=null
            if draw(st.booleans()):
                child_json = "null"
            else:
                # nested record with child=null (no further nesting)
                child_json = draw(record(allow_child=False))
        else:
            child_json = "null"

        # Build JSON object string with fields in fixed order
        json_obj = (
            "{" +
            f'"id":{id_json},' +
            f'"amount":{amount_json},' +
            f'"name":{name_json},' +
            f'"status":{status_json},' +
            f'"tags":{tags_json},' +
            f'"child":{child_json}' +
            "}"
        )
        return json_obj

    # Draw top-level record
    top_record = draw(record())

    # Return as bytes
    return top_record.encode("utf-8")