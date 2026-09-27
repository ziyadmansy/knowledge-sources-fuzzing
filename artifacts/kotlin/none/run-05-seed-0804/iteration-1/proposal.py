from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with quotes escaped
    def json_string(s: str) -> str:
        # Escape backslash and double quotes minimally
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return '"' + s + '"'

    # Recursive generator for a Record JSON text, with bounded depth
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # At depth limit, child is always null
        if depth <= 0:
            child_strat = st.just("null")
        else:
            # child can be null or a nested record (one less depth)
            child_strat = st.one_of(
                st.just("null"),
                record_json(depth - 1)
            )

        # id: integer, but allow some edge cases as strings or floats to cause divergence
        # We produce either a valid integer, or a string containing an integer, or a float
        # to trigger type confusion in some deserializers.
        id_strat = st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            # integer as string literal (wrong type)
            st.integers(min_value=0, max_value=2**31-1).map(lambda i: json_string(str(i))),
            # float number (wrong type)
            st.floats(min_value=0, max_value=2**31-1, allow_nan=False, allow_infinity=False).map(lambda f: repr(f))
        )

        # amount: string, but sometimes a number or null to cause divergence
        amount_strat = st.one_of(
            # valid string amount
            st.text(min_size=1, max_size=10).map(json_string),
            # number instead of string
            st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False).map(lambda f: repr(f)),
            # null instead of string
            st.just("null")
        )

        # name: string or null, but also try number or boolean to cause divergence
        name_strat = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=15).map(json_string),
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.booleans().map(lambda b: "true" if b else "false")
        )

        # status: one of the three strings, but also try null or a wrong string to cause divergence
        status_strat = st.one_of(
            st.sampled_from(statuses),
            st.just("null"),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string)
        )

        # tags: array of strings, but also try null, array of numbers, or array with mixed types
        # limit size to 0..3 for performance
        tag_str = st.text(min_size=1, max_size=10).map(json_string)
        tags_strat = st.one_of(
            # valid array of strings
            st.lists(tag_str, min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]"),
            # null instead of array
            st.just("null"),
            # array of numbers
            st.lists(st.integers(min_value=0, max_value=100).map(str), min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]"),
            # mixed array (string and number)
            st.lists(st.one_of(tag_str, st.integers(min_value=0, max_value=100).map(str)), min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
        )

        # Compose the JSON object fields in random order to test order independence
        # But keep all fields present (except child can be null)
        # We produce a dict of fieldname -> JSON text, then join with commas
        def make_obj(idv, amountv, namev, statusv, tagsv, childv):
            fields = [
                '"id":' + idv,
                '"amount":' + amountv,
                '"name":' + namev,
                '"status":' + statusv,
                '"tags":' + tagsv,
                '"child":' + childv,
            ]
            # Shuffle fields order to increase variation
            import random
            random.shuffle(fields)
            return "{" + ",".join(fields) + "}"

        # We cannot import random in the function, so shuffle by Hypothesis draw of permutation
        # Draw a permutation of 6 indices and reorder fields accordingly
        def shuffled_obj(idv, amountv, namev, statusv, tagsv, childv):
            fields = [
                '"id":' + idv,
                '"amount":' + amountv,
                '"name":' + namev,
                '"status":' + statusv,
                '"tags":' + tagsv,
                '"child":' + childv,
            ]
            perm = draw(st.permutations(range(6)))
            shuffled_fields = [fields[i] for i in perm]
            return "{" + ",".join(shuffled_fields) + "}"

        return st.tuples(id_strat, amount_strat, name_strat, status_strat, tags_strat, child_strat).map(
            lambda t: shuffled_obj(*t)
        )

    # Generate a record with max recursion depth 1 (one level of child)
    json_text = draw(record_json(depth=1))
    return json_text.encode("utf-8")