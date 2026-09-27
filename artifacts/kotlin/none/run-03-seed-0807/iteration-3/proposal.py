from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for quotes and backslash
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Helper to produce JSON array of strings
    def json_string_array(strings):
        return "[" + ",".join(json_string(s) for s in strings) + "]"

    # Recursive generator for the "child" field, bounded depth
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # At max depth, child is always null
        if depth <= 0:
            child_strat = st.just("null")
        else:
            # child can be null or a nested record
            child_strat = st.one_of(
                st.just("null"),
                record_json(depth - 1)
            )

        # id: integer, but we will sometimes produce a string or float to cause divergence
        # amount: string, but sometimes number or null or missing
        # name: string or null, sometimes number or missing
        # status: one of statuses, sometimes invalid string or number or missing
        # tags: array of strings, sometimes array with non-string or empty, or missing
        # child: as above

        # We produce a dict of fields as strings, then join with commas

        # id field: mostly integer, sometimes stringified integer, sometimes float, sometimes missing
        id_field = draw(st.one_of(
            st.integers(min_value=0, max_value=1000).map(lambda i: f'"id":{i}'),
            st.integers(min_value=0, max_value=1000).map(lambda i: f'"id":"{i}"'),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: f'"id":{f}'),
            st.just(None)  # missing field
        ))

        # amount field: mostly string, sometimes number, sometimes null, sometimes missing
        amount_field = draw(st.one_of(
            st.text(min_size=1, max_size=10).map(json_string).map(lambda s: f'"amount":{s}'),
            st.integers(min_value=0, max_value=1000).map(lambda i: f'"amount":{i}'),
            st.just('"amount":null'),
            st.just(None)  # missing
        ))

        # name field: string or null, sometimes number, sometimes missing
        name_field = draw(st.one_of(
            st.one_of(st.none(), st.text(min_size=0, max_size=10)).map(
                lambda v: f'"name":null' if v is None else f'"name":{json_string(v)}'),
            st.integers(min_value=0, max_value=1000).map(lambda i: f'"name":{i}'),
            st.just(None)  # missing
        ))

        # status field: mostly valid enum string, sometimes invalid string, sometimes number, sometimes missing
        status_field = draw(st.one_of(
            st.sampled_from(statuses).map(json_string).map(lambda s: f'"status":{s}'),
            st.text(min_size=1, max_size=10).filter(lambda x: x not in statuses).map(json_string).map(lambda s: f'"status":{s}'),
            st.integers(min_value=0, max_value=10).map(lambda i: f'"status":{i}'),
            st.just(None)  # missing
        ))

        # tags field: array of strings, sometimes array with non-string, sometimes empty array, sometimes missing
        tags_field = draw(st.one_of(
            st.lists(st.text(min_size=0, max_size=5), max_size=5).map(json_string_array).map(lambda s: f'"tags":{s}'),
            st.lists(st.one_of(st.text(min_size=0, max_size=5), st.integers()), max_size=5).map(
                lambda arr: "[" + ",".join(
                    (json_string(x) if isinstance(x, str) else str(x)) for x in arr) + "]"
            ).map(lambda s: f'"tags":{s}'),
            st.just('"tags":[]'),
            st.just(None)  # missing
        ))

        # child field: null or nested record
        child_field = draw(child_strat).map(lambda s: f'"child":{s}')

        # Collect fields, omit those that are None (missing)
        fields = [f for f in [id_field, amount_field, name_field, status_field, tags_field, child_field] if f is not None]

        # Shuffle fields to vary order
        draw(st.permutations(fields))  # just to consume draw, but permutations returns tuple
        # Actually shuffle fields:
        import random
        random.shuffle(fields)

        json_obj = "{" + ",".join(fields) + "}"
        return st.just(json_obj)

    # Generate top-level record with depth 1 recursion
    # We want to produce the string bytes, so we draw the string and encode utf-8
    # Use record_json(1) to allow one level of child recursion
    # But we cannot call record_json(1) directly because it returns a strategy, so we draw from it

    # Draw the JSON string from the strategy
    json_str = draw(record_json(1))

    # Return bytes
    return json_str.encode("utf-8")