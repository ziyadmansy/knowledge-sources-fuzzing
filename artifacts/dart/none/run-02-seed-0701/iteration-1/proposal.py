from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal with proper escaping for quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for " and \ to keep JSON valid
        # Hypothesis strings are unicode, but we keep it simple here
        s_escaped = s.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{s_escaped}\""

    # Recursive record generator with depth limit
    def record(depth: int) -> st.SearchStrategy[str]:
        # id: integer (always present)
        id_strat = st.integers(min_value=-(2**31), max_value=2**31-1).map(str)

        # amount: string (always present)
        # To induce subtle divergences, sometimes produce numeric strings, sometimes empty, sometimes with spaces
        amount_strat = st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(c not in "\"\\" for c in s)),  # simple strings no quotes or backslash
            st.integers(min_value=0, max_value=999999).map(str),
            st.just(""),  # empty string
            st.just(" 123 "),  # string with spaces
        ).map(json_string)

        # name: string or null
        # To induce divergence, sometimes produce null, sometimes string, sometimes empty string
        name_strat = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).filter(lambda s: all(c not in "\"\\" for c in s)).map(json_string),
        )

        # status: one of the three strings, but also sometimes an invalid string to induce divergence
        # We produce mostly valid, but sometimes invalid strings or null to test behavior
        status_strat = st.one_of(
            st.sampled_from(statuses).map(json_string),
            st.text(min_size=1, max_size=8).filter(lambda s: s not in statuses and all(c not in "\"\\" for c in s)).map(json_string),
            st.none().map(lambda _: "null"),
        )

        # tags: array of strings (always present)
        # To induce divergence, sometimes empty array, sometimes array with empty string, sometimes array with null (invalid)
        tag_string = st.text(min_size=0, max_size=5).filter(lambda s: all(c not in "\"\\" for c in s)).map(json_string)
        tags_strat = st.one_of(
            st.lists(tag_string, min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]"),
            st.just("[]"),
            st.just("[null]"),  # invalid element to induce divergence
        )

        # child: either null or a nested record (one level recursion max)
        if depth <= 0:
            child_strat = st.just("null")
        else:
            # To induce divergence, sometimes produce null, sometimes a nested record
            child_strat = st.one_of(
                st.just("null"),
                record(depth - 1),
            )

        # Compose the JSON object string with fields in fixed order for consistency
        def compose(id_s, amount_s, name_s, status_s, tags_s, child_s) -> str:
            return (
                "{" +
                f"\"id\":{id_s}," +
                f"\"amount\":{amount_s}," +
                f"\"name\":{name_s}," +
                f"\"status\":{status_s}," +
                f"\"tags\":{tags_s}," +
                f"\"child\":{child_s}" +
                "}"
            )

        return st.tuples(id_strat, amount_strat, name_strat, status_strat, tags_strat, child_strat).map(
            lambda t: compose(*t)
        )

    # Generate a record with max depth 1 (one level of recursion)
    json_text = draw(record(depth=1))
    return json_text.encode("utf-8")