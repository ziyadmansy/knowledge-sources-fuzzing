from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with proper escaping for simple ASCII subset
    def json_string(s: str) -> str:
        # Escape backslash and double quotes minimally
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Recursive generator for the "child" field, bounded to one level of recursion
    # We produce either null or a nested record with no further child (child=null)
    def record_json(level: int) -> st.SearchStrategy[str]:
        # At level 1 (top), allow child; at level 2, child must be null to bound recursion
        allow_child = (level == 1)

        # id: integer as number or sometimes as string (to induce divergence)
        id_strategy = st.one_of(
            st.integers(min_value=0, max_value=10**6).map(str),
            st.integers(min_value=0, max_value=10**6).map(lambda i: json_string(str(i))),
            # Occasionally produce a float string to cause divergence
            st.floats(min_value=0, max_value=10**6, allow_infinity=False, allow_nan=False).map(lambda f: str(round(f, 2))),
        )

        # amount: string, but sometimes a number (to cause divergence)
        amount_strategy = st.one_of(
            st.text(min_size=1, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=10**6).map(str),
            st.floats(min_value=0, max_value=10**6, allow_infinity=False, allow_nan=False).map(lambda f: str(round(f, 2))),
        )

        # name: string or null, sometimes number or boolean to cause divergence
        name_strategy = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=100).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
        )

        # status: one of the three strings, sometimes null or wrong string
        status_strategy = st.one_of(
            st.sampled_from(STATUS_VALUES),
            st.just("null"),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string),
        )

        # tags: array of strings, sometimes empty array, sometimes array with non-string elements
        tags_strategy = st.one_of(
            st.lists(st.text(min_size=0, max_size=5).map(json_string), max_size=5).map(lambda lst: "[" + ",".join(lst) + "]"),
            st.just("[]"),
            # Occasionally insert a number or null inside tags array to cause divergence
            st.lists(st.one_of(
                st.text(min_size=0, max_size=5).map(json_string),
                st.integers(min_value=0, max_value=100).map(str),
                st.just("null"),
            ), max_size=5).map(lambda lst: "[" + ",".join(lst) + "]"),
        )

        # child: either null or nested record (only if allow_child)
        if allow_child:
            child_strategy = st.one_of(
                st.just("null"),
                record_json(level + 1),
            )
        else:
            child_strategy = st.just("null")

        # Compose the JSON object fields in order
        def compose_record(id_, amount, name, status, tags, child):
            return (
                "{" +
                f'"id":{id_},' +
                f'"amount":{amount},' +
                f'"name":{name},' +
                f'"status":{status},' +
                f'"tags":{tags},' +
                f'"child":{child}' +
                "}"
            )

        return st.tuples(id_strategy, amount_strategy, name_strategy, status_strategy, tags_strategy, child_strategy).map(
            lambda t: compose_record(*t)
        )

    # Generate top-level record JSON string
    json_str = draw(record_json(1))
    return json_str.encode("utf-8")