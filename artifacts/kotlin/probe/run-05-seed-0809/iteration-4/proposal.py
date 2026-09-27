from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # We will produce JSON text manually, carefully controlling recursion depth.

    # To avoid max recursion depth, limit child nesting to 1 level max.
    # We produce a record JSON text, with optional child.

    # Helper: produce a JSON string literal from a Hypothesis string, escaping quotes and backslashes.
    def json_string_literal(s: str) -> str:
        # Escape backslash and double quote
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        # Also escape control chars minimally (newline, tab)
        s = s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return '"' + s + '"'

    # Strategy for "id": integer or string convertible to int (Probe 2)
    # To maximize divergence, sometimes produce int, sometimes string int, sometimes string non-int (should reject)
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=10000).map(str),  # as string number
        st.integers(min_value=0, max_value=10000).map(str),  # as string number (duplicate to bias)
        st.integers(min_value=0, max_value=10000),           # as integer
        st.text(min_size=1, max_size=3).filter(lambda x: not x.isdigit())  # invalid string id (should cause rejection)
    )

    # Strategy for "amount": string normally, but also number (Probe 3)
    # Also try invalid types (bool, null) rarely to cause divergence.
    amount_strategy = st.one_of(
        st.text(min_size=1, max_size=10).map(json_string_literal),
        st.integers(min_value=0, max_value=100000).map(str),  # number (accepted by Gson, Moshi, Jackson; rejected by kotlinx)
        st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False).map(str),
        st.just('null'),  # null amount (should cause rejection)
        st.booleans().map(lambda b: "true" if b else "false")  # boolean amount (should cause rejection)
    )

    # Strategy for "name": string or null normally, but also number (Probe 4)
    # Also try missing or empty string.
    name_strategy = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(json_string_literal),
        st.integers(min_value=0, max_value=10000).map(str),  # number (accepted by Gson, Moshi, Jackson; rejected by kotlinx)
        st.just('true'),  # boolean (should cause rejection)
    )

    # Strategy for "status": enum string, null, invalid string (Probe 5, 13)
    status_strategy = st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.just('null'),  # null status (Gson accepts with null, others reject)
        st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string_literal),  # invalid enum string
    )

    # Strategy for "tags": array of strings normally, but also test:
    # - string instead of array (Probe 6)
    # - array with numeric elements (Probe 7)
    # - array with null elements (Probe 14)
    # - mixed types in array (Probe 15)
    # - empty array
    def tags_array_strategy():
        # string instead of array (rare)
        string_instead = st.text(min_size=1, max_size=10).map(json_string_literal)
        # array of strings
        strings_array = st.lists(st.text(min_size=0, max_size=10).map(json_string_literal), min_size=0, max_size=5).map(
            lambda lst: "[" + ",".join(lst) + "]"
        )
        # array with numeric elements coerced to strings (Gson, Moshi, Jackson accept; kotlinx rejects)
        mixed_array = st.lists(
            st.one_of(
                st.text(min_size=0, max_size=10).map(json_string_literal),
                st.integers(min_value=0, max_value=10000).map(str),
                st.none().map(lambda _: "null"),
            ),
            min_size=0, max_size=5
        ).map(lambda lst: "[" + ",".join(lst) + "]")

        # array with null elements (Probe 14)
        nulls_array = st.lists(
            st.one_of(
                st.text(min_size=0, max_size=10).map(json_string_literal),
                st.none().map(lambda _: "null"),
            ),
            min_size=0, max_size=5
        ).map(lambda lst: "[" + ",".join(lst) + "]")

        return st.one_of(
            string_instead,
            strings_array,
            mixed_array,
            nulls_array,
        )

    tags_strategy = tags_array_strategy()

    # Strategy for "child": null or nested record (one level only)
    # Also test empty object {} (Probe 11)
    # Also test missing fields in child (Probe 11)
    # Also test child with "id" as string convertible to int (Probe 9)
    # To avoid recursion depth, child has no further child.
    @st.composite
    def child_strategy(draw):
        choice = draw(st.integers(min_value=0, max_value=4))
        if choice == 0:
            # null child (Probe 12)
            return "null"
        elif choice == 1:
            # empty object {} (Probe 11)
            return "{}"
        elif choice == 2:
            # child with all fields correct, no further child
            child_id = draw(st.one_of(
                st.integers(min_value=0, max_value=10000).map(str),
                st.integers(min_value=0, max_value=10000)
            ))
            child_amount = draw(st.text(min_size=1, max_size=10).map(json_string_literal))
            child_name = draw(st.one_of(
                st.none().map(lambda _: "null"),
                st.text(min_size=0, max_size=10).map(json_string_literal)
            ))
            child_status = draw(st.sampled_from(STATUS_VALUES))
            child_tags = draw(st.lists(st.text(min_size=0, max_size=10).map(json_string_literal), min_size=0, max_size=3)).map(
                lambda lst: "[" + ",".join(lst) + "]"
            )
            # Compose child JSON text
            child_json = (
                '{'
                + '"id":' + (str(child_id) if isinstance(child_id, int) else child_id) + ','
                + '"amount":' + child_amount + ','
                + '"name":' + child_name + ','
                + '"status":' + child_status + ','
                + '"tags":' + child_tags + ','
                + '"child":null'
                + '}'
            )
            return child_json
        elif choice == 3:
            # child missing some fields (should cause rejection except Gson)
            # We'll omit "name" and "tags"
            child_id = draw(st.integers(min_value=0, max_value=10000))
            child_amount = draw(st.text(min_size=1, max_size=10).map(json_string_literal))
            child_status = draw(st.sampled_from(STATUS_VALUES))
            child_json = (
                '{'
                + '"id":' + str(child_id) + ','
                + '"amount":' + child_amount + ','
                + '"status":' + child_status + ','
                + '"child":null'
                + '}'
            )
            return child_json
        else:
            # child with "id" as string convertible to int (Probe 9)
            child_id = draw(st.integers(min_value=0, max_value=10000).map(str))
            child_amount = draw(st.text(min_size=1, max_size=10).map(json_string_literal))
            child_name = draw(st.one_of(
                st.none().map(lambda _: "null"),
                st.text(min_size=0, max_size=10).map(json_string_literal)
            ))
            child_status = draw(st.sampled_from(STATUS_VALUES))
            child_tags = draw(st.lists(st.text(min_size=0, max_size=10).map(json_string_literal), min_size=0, max_size=3)).map(
                lambda lst: "[" + ",".join(lst) + "]"
            )
            child_json = (
                '{'
                + '"id":' + child_id + ','
                + '"amount":' + child_amount + ','
                + '"name":' + child_name + ','
                + '"status":' + child_status + ','
                + '"tags":' + child_tags + ','
                + '"child":null'
                + '}'
            )
            return child_json

    # Compose the root record JSON text
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_strategy)
    status_val = draw(status_strategy)
    tags_val = draw(tags_strategy)
    child_val = draw(child_strategy())

    # Compose JSON text for root record
    # Always include all six fields (Probe 1)
    # We do not omit fields at root to avoid all rejecting.
    json_text = (
        '{'
        + '"id":' + (id_val if id_val.isdigit() or (id_val.startswith('"') and id_val.endswith('"')) else json_string_literal(id_val)) + ','
        + '"amount":' + amount_val + ','
        + '"name":' + name_val + ','
        + '"status":' + status_val + ','
        + '"tags":' + tags_val + ','
        + '"child":' + child_val
        + '}'
    )

    return json_text.encode('utf-8')