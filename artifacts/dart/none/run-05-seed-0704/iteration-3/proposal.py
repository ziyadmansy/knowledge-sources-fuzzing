from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper: produce JSON string literal with proper escaping of " and \
    def json_string(s: str) -> str:
        # minimal escaping for " and \
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Recursive record generator with bounded depth (max 1 level recursion)
    def record(depth: int) -> st.SearchStrategy[str]:
        # id: integer
        id_strat = st.integers(min_value=0, max_value=2**31-1).map(str)

        # amount: string, but we will sometimes produce non-string to provoke divergence
        # Mostly string, sometimes integer or null (wrong types)
        amount_strat = st.one_of(
            st.text(min_size=1, max_size=10).map(json_string),
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.just("null"),
            st.just("123"),  # numeric string
        )

        # name: string or null, but sometimes produce integer or boolean to provoke divergence
        name_strat = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).map(json_string),
            st.integers(min_value=-10, max_value=10).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
        )

        # status: one of "active", "inactive", "unknown"
        # Sometimes produce invalid string or null to provoke divergence
        status_strat = st.one_of(
            st.sampled_from(["active", "inactive", "unknown"]).map(json_string),
            st.text(min_size=1, max_size=7).filter(lambda s: s not in {"active","inactive","unknown"}).map(json_string),
            st.none().map(lambda _: "null"),
        )

        # tags: array of strings
        # Sometimes empty array, sometimes array with null or non-string elements to provoke divergence
        tag_elem = st.one_of(
            st.text(min_size=0, max_size=5).map(json_string),
            st.none().map(lambda _: "null"),
            st.integers(min_value=0, max_value=10).map(str),
        )
        tags_strat = st.lists(tag_elem, min_size=0, max_size=3).map(
            lambda lst: "[" + ",".join(lst) + "]"
        )

        # child: either null or a nested record (only one level deep)
        if depth >= 1:
            # At max depth, child is null or empty object (to provoke divergence)
            child_strat = st.one_of(
                st.just("null"),
                st.just("{}"),
            )
        else:
            # child is null or a nested record (depth+1)
            child_strat = st.one_of(
                st.just("null"),
                record(depth + 1),
            )

        # Compose fields as a dict string with all six fields always present
        # To provoke divergence, sometimes shuffle field order or add whitespace
        # But Hypothesis does not guarantee order in dict, so we fix order here

        def build_record(id_s, amount_s, name_s, status_s, tags_s, child_s) -> str:
            # Insert some random whitespace around colons and commas to provoke divergence
            ws1 = " " if draw(st.booleans()) else ""
            ws2 = " " if draw(st.booleans()) else ""
            ws3 = " " if draw(st.booleans()) else ""
            ws4 = " " if draw(st.booleans()) else ""
            ws5 = " " if draw(st.booleans()) else ""
            ws6 = " " if draw(st.booleans()) else ""
            ws7 = " " if draw(st.booleans()) else ""
            ws8 = " " if draw(st.booleans()) else ""
            ws9 = " " if draw(st.booleans()) else ""
            ws10 = " " if draw(st.booleans()) else ""

            # Fixed field order: id, amount, name, status, tags, child
            return (
                "{" +
                ws1 + '"id"' + ws2 + ":" + ws3 + id_s + "," +
                ws4 + '"amount"' + ws5 + ":" + ws6 + amount_s + "," +
                ws7 + '"name"' + ws8 + ":" + ws9 + name_s + "," +
                ws10 + '"status"' + ":" + status_s + "," +
                '"tags":' + tags_s + "," +
                '"child":' + child_s +
                "}"
            )

        return st.tuples(id_strat, amount_strat, name_strat, status_strat, tags_strat, child_strat).map(
            lambda t: build_record(*t)
        )

    # Generate top-level record with depth 0
    json_text = draw(record(0))

    # Return as bytes
    return json_text.encode("utf-8")