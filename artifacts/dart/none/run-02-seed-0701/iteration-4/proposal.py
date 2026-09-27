from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # To avoid infinite recursion, limit depth to 1 for "child"
    # Compose a record as JSON text (string), then encode to bytes at the end.

    # Helper to produce JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Escape backslash and double quotes
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars (minimal)
        s = s.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{s}"'

    # Strategy for "id": integer
    id_strat = st.integers(min_value=-(2**31), max_value=2**31-1).map(str)

    # Strategy for "amount": string, but try some edge cases that might confuse parsers
    # e.g. numeric strings, empty string, strings with spaces, signs, decimals
    amount_strat = st.one_of(
        st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in '\\"\b\f\n\r\t')),  # safe strings without quotes or control chars
        st.just("0"),
        st.just("0.0"),
        st.just("-0"),
        st.just("+0"),
        st.just("1e10"),
        st.just("-1e-10"),
        st.just(" 123 "),  # spaces around digits
        st.just(""),  # empty string
    ).map(json_string_literal)

    # Strategy for "name": either null or string (including empty string, unicode, or tricky chars)
    name_strat = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(max_size=20).map(json_string_literal),
    )

    # Strategy for "status": one of the three strings, but also try to produce a wrong type or wrong string sometimes
    # To cause divergence, sometimes produce a wrong string or a number or null
    status_strat = st.one_of(
        st.sampled_from(statuses).map(json_string_literal),
        # Introduce some "almost valid" variants
        st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses).map(json_string_literal),
        st.integers(min_value=-10, max_value=10).map(str),
        st.none().map(lambda _: "null"),
    )

    # Strategy for "tags": array of strings (strings can be empty or normal)
    # Also try empty array, or array with nulls (which is invalid per schema but might cause divergence)
    tag_string = st.text(max_size=10).map(json_string_literal)
    tags_strat = st.one_of(
        st.lists(tag_string, max_size=5).map(lambda lst: "[" + ",".join(lst) + "]"),
        # Introduce null inside array sometimes
        st.lists(st.one_of(tag_string, st.just("null")), max_size=5).map(lambda lst: "[" + ",".join(lst) + "]"),
        # Empty array
        st.just("[]"),
        # Sometimes produce a string instead of array to cause divergence
        st.text(max_size=10).map(json_string_literal),
        # Sometimes produce null
        st.just("null"),
    )

    # Recursive "child" field: either null or a record (one level deep only)
    # To avoid infinite recursion, child record will have child=null always
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # If depth > 1, child must be null
        if depth > 1:
            child_val = st.just("null")
        else:
            child_val = st.deferred(lambda: record_json(depth + 1)).map(lambda s: s).one_of(st.just("null"))

        def build_record(id_s, amount_s, name_s, status_s, tags_s, child_s):
            # Compose JSON object string with fields in fixed order
            return (
                '{'
                + f'"id":{id_s},'
                + f'"amount":{amount_s},'
                + f'"name":{name_s},'
                + f'"status":{status_s},'
                + f'"tags":{tags_s},'
                + f'"child":{child_s}'
                + '}'
            )

        return st.tuples(
            id_strat,
            amount_strat,
            name_strat,
            status_strat,
            tags_strat,
            child_val,
        ).map(lambda t: build_record(*t))

    # Generate top-level record JSON string
    json_str = draw(record_json(0))

    # Return bytes
    return json_str.encode("utf-8")