from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Base valid field strategies
    id_strat = st.integers(min_value=0, max_value=2**31-1)
    amount_strat = st.text(min_size=1).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))  # printable ASCII
    # name can be string or null
    name_strat = st.one_of(
        st.none(),
        st.text(min_size=0).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))
    )
    status_strat = st.sampled_from(statuses)
    tags_strat = st.lists(
        st.text(min_size=0).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
        max_size=5
    )

    # To induce divergence, we will create a "field type variant" strategy:
    # For each field, with some small probability, produce a wrong type variant:
    # - id: sometimes string instead of int
    # - amount: sometimes number instead of string
    # - name: sometimes number or bool instead of string/null
    # - status: sometimes string outside enum, or number
    # - tags: sometimes null or string instead of array
    # - child: sometimes missing, or wrong type (string, number), or recursive record or null

    # Recursive record strategy with bounded depth
    def record_strategy(depth):
        if depth <= 0:
            # leaf: child is null only
            child_strat = st.just("null")
        else:
            # child can be null or a nested record
            child_strat = st.one_of(
                st.just("null"),
                record_strategy(depth - 1).map(lambda s: s.decode("utf-8"))
            )

        # For each field, build a strategy that produces a JSON snippet (string) for that field,
        # sometimes with correct type, sometimes with a wrong type variant.

        # id field: int normally, sometimes stringified int, sometimes float, sometimes null (wrong)
        id_field = st.one_of(
            id_strat.map(lambda v: f'"id":{v}'),
            id_strat.map(lambda v: f'"id":"{v}"'),
            st.floats(allow_infinity=False, allow_nan=False).map(lambda v: f'"id":{v}'),
            st.just('"id":null'),
        )

        # amount field: string normally, sometimes number, sometimes null, sometimes bool
        amount_field = st.one_of(
            amount_strat.map(lambda s: f'"amount":"{s}"'),
            st.floats(allow_infinity=False, allow_nan=False).map(lambda v: f'"amount":{v}'),
            st.just('"amount":null'),
            st.booleans().map(lambda b: f'"amount":{str(b).lower()}'),
        )

        # name field: string or null normally, sometimes number, bool, or missing (simulate missing by empty string)
        name_field = st.one_of(
            name_strat.map(lambda v: f'"name":{("null" if v is None else f"\\"{v}\\"")}'),
            st.integers().map(lambda v: f'"name":{v}'),
            st.booleans().map(lambda b: f'"name":{str(b).lower()}'),
            st.just(''),  # simulate missing by empty string (will be removed later)
        )

        # status field: enum string normally, sometimes invalid string, number, or null
        status_field = st.one_of(
            status_strat.map(lambda s: f'"status":"{s}"'),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses).map(lambda s: f'"status":"{s}"'),
            st.integers().map(lambda v: f'"status":{v}'),
            st.just('"status":null'),
        )

        # tags field: array of strings normally, sometimes null, string, number, or bool
        tags_field = st.one_of(
            tags_strat.map(lambda lst: '"tags":[' + ",".join(f'"{t}"' for t in lst) + ']'),
            st.just('"tags":null'),
            st.text(min_size=1, max_size=10).map(lambda s: f'"tags":"{s}"'),
            st.integers().map(lambda v: f'"tags":{v}'),
            st.booleans().map(lambda b: f'"tags":{str(b).lower()}'),
        )

        # child field: null or nested record normally, sometimes string, number, bool, or missing (empty string)
        child_field = st.one_of(
            child_strat.map(lambda s: f'"child":{s}'),
            st.text(min_size=1, max_size=10).map(lambda s: f'"child":"{s}"'),
            st.integers().map(lambda v: f'"child":{v}'),
            st.booleans().map(lambda b: f'"child":{str(b).lower()}'),
            st.just(''),  # simulate missing by empty string
        )

        # Compose fields into a JSON object string.
        # We allow some fields to be missing by filtering out empty strings.
        fields = st.tuples(id_field, amount_field, name_field, status_field, tags_field, child_field)

        def assemble(fields):
            # Remove empty strings (simulate missing fields)
            filtered = [f for f in fields if f != '']
            # Join with commas
            body = ",".join(filtered)
            return ("{" + body + "}").encode("utf-8")

        return fields.map(assemble)

    # Generate with max depth 1 (one level of recursion)
    return draw(record_strategy(depth=1))