from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # minimal escaping for " and \
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Strategy for id field: mostly integers, but sometimes strings or floats to cause divergence
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=10**9).map(str),
        # stringified integer (quoted)
        st.integers(min_value=0, max_value=10**9).map(lambda i: json_string_literal(str(i))),
        # float as string (unquoted)
        st.floats(min_value=0, max_value=10**9, allow_infinity=False, allow_nan=False).map(lambda f: str(f)),
        # float as string (quoted)
        st.floats(min_value=0, max_value=10**9, allow_infinity=False, allow_nan=False).map(lambda f: json_string_literal(str(f))),
    )

    # Strategy for amount field: string, but sometimes a number or null to cause divergence
    amount_strategy = st.one_of(
        # normal string amount
        st.text(min_size=1, max_size=10).map(json_string_literal),
        # numeric unquoted (should be rejected by some)
        st.floats(min_value=0, max_value=10000, allow_infinity=False, allow_nan=False).map(lambda f: str(f)),
        # null literal (unquoted)
        st.just("null"),
        # numeric quoted string
        st.floats(min_value=0, max_value=10000, allow_infinity=False, allow_nan=False).map(lambda f: json_string_literal(str(f))),
    )

    # Strategy for name field: string or null, but sometimes number or boolean or missing (simulate by null)
    name_strategy = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=15).map(json_string_literal),
        # number as string literal (quoted)
        st.integers(min_value=-1000, max_value=1000).map(lambda i: json_string_literal(str(i))),
        # number unquoted (should cause divergence)
        st.integers(min_value=-1000, max_value=1000).map(str),
        # boolean unquoted (should cause divergence)
        st.booleans().map(lambda b: "true" if b else "false"),
    )

    # Strategy for status field: one of the three strings, but sometimes unquoted or wrong string
    status_strategy = st.one_of(
        st.sampled_from(statuses),
        # unquoted correct strings (should cause divergence)
        st.sampled_from(["active", "inactive", "unknown"]),
        # wrong string quoted
        st.text(min_size=1, max_size=7).filter(lambda s: s not in ["active", "inactive", "unknown"]).map(json_string_literal),
        # null literal
        st.just("null"),
    )

    # Strategy for tags field: array of strings, but sometimes null, or array with non-string elements
    tags_strategy = st.one_of(
        # normal array of strings
        st.lists(st.text(min_size=0, max_size=10).map(json_string_literal), min_size=0, max_size=5).map(
            lambda lst: "[" + ",".join(lst) + "]"
        ),
        # null literal
        st.just("null"),
        # array with some numbers unquoted
        st.lists(
            st.one_of(
                st.text(min_size=0, max_size=10).map(json_string_literal),
                st.integers(min_value=0, max_value=100).map(str),
            ),
            min_size=0,
            max_size=5,
        ).map(lambda lst: "[" + ",".join(lst) + "]"),
        # array with booleans unquoted
        st.lists(
            st.one_of(
                st.text(min_size=0, max_size=10).map(json_string_literal),
                st.booleans().map(lambda b: "true" if b else "false"),
            ),
            min_size=0,
            max_size=5,
        ).map(lambda lst: "[" + ",".join(lst) + "]"),
    )

    # Recursive strategy for child field: either null or a nested record (one level deep max)
    # To avoid infinite recursion, we limit depth to 1.
    # We define a helper function to build the record JSON string.

    def record_json(depth: int) -> st.SearchStrategy[str]:
        # At depth 1, child must be null to stop recursion
        if depth > 1:
            child_val = st.just("null")
        else:
            child_val = st.deferred(lambda: record_json(depth + 1)).map(lambda s: s)

        return st.tuples(
            id_strategy,
            amount_strategy,
            name_strategy,
            status_strategy,
            tags_strategy,
            child_val,
        ).map(
            lambda fields: (
                '{'
                + '"id":' + fields[0] + ','
                + '"amount":' + fields[1] + ','
                + '"name":' + fields[2] + ','
                + '"status":' + fields[3] + ','
                + '"tags":' + fields[4] + ','
                + '"child":' + fields[5]
                + '}'
            )
        )

    # Generate the top-level record JSON string
    json_str = draw(record_json(0))

    return json_str.encode("utf-8")