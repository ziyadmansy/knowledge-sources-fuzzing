from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    statuses = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
    # id: integer or sometimes string (to cause divergence)
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),
        st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit())  # invalid id as string
    )
    # amount: string normally numeric, sometimes number (no quotes) or null or empty string
    amount_strategy = st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(c in '0123456789.-' for c in s)),
        st.integers(min_value=-1000, max_value=1000).map(str),  # number without quotes (invalid)
        st.just("null"),  # null literal (invalid)
        st.just('""'),  # empty string quoted
    )
    # name: string or null or number (to cause divergence)
    name_strategy = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(lambda s: '"' + s.replace('"','\\"') + '"'),
        st.integers(min_value=-1000, max_value=1000).map(str),  # number literal (invalid)
    )
    # tags: array of strings, sometimes array of numbers or empty array or null (invalid)
    tag_string = st.text(min_size=1, max_size=5).map(lambda s: '"' + s.replace('"','\\"') + '"')
    tags_strategy = st.one_of(
        st.lists(tag_string, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]"),
        st.lists(st.integers(min_value=0, max_value=100).map(str), max_size=3).map(lambda lst: "[" + ",".join(lst) + "]"),  # numbers instead of strings
        st.just("null"),
        st.just("[]"),
    )
    # status: one of the three strings, or sometimes unquoted (invalid)
    status_strategy = st.one_of(
        statuses,
        st.sampled_from(['active', 'inactive', 'unknown']),  # unquoted
    )
    # child: null or nested record (bounded recursion)
    # To avoid infinite recursion, limit depth to 1 (child.child always null)
    def child_strategy(depth):
        if depth <= 0:
            return st.just("null")
        else:
            return record_strategy(depth - 1)
    # record strategy
    def record_strategy(depth):
        return st.tuples(
            id_strategy,
            amount_strategy,
            name_strategy,
            status_strategy,
            tags_strategy,
            child_strategy(depth)
        ).map(lambda t: (
            '{"id":' + t[0] +
            ',"amount":' + t[1] +
            ',"name":' + t[2] +
            ',"status":' + t[3] +
            ',"tags":' + t[4] +
            ',"child":' + t[5] +
            '}'
        ))
    # Generate top-level record with depth 1
    json_str = draw(record_strategy(1))
    return json_str.encode('utf-8')