from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper: produce a JSON string literal with proper escaping for simple ASCII only
    # (Hypothesis strings are unicode, but we limit to ASCII for simplicity)
    def json_string(s: str) -> str:
        # Escape backslash and double quote only, minimal escaping
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Recursive strategy for a Record JSON text (string)
    # depth controls recursion depth, max 1 for child
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # id: integer
        id_strat = st.integers(min_value=0, max_value=2**31-1).map(str)

        # amount: string (any string)
        # To induce divergence, sometimes produce numeric strings, sometimes with spaces, etc.
        amount_strat = st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).map(json_string)

        # name: string or null
        # To induce divergence, sometimes produce null, sometimes string, sometimes empty string
        name_strat = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).map(json_string),
        )

        # status: one of "active", "inactive", "unknown"
        # To induce divergence, sometimes produce invalid strings or null or missing (handled outside)
        status_strat = st.sampled_from(statuses)

        # tags: array of strings (possibly empty)
        # To induce divergence, sometimes empty array, sometimes array with empty string, sometimes array with null (invalid)
        tag_str = st.text(min_size=0, max_size=8, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).map(json_string)
        tags_strat = st.lists(tag_str, min_size=0, max_size=3).map(
            lambda lst: "[" + ",".join(lst) + "]"
        )

        # child: Record or null
        if depth <= 0:
            child_strat = st.just("null")
        else:
            # To induce divergence, sometimes null, sometimes a nested record
            child_strat = st.one_of(
                st.just("null"),
                record_json(depth - 1)
            )

        # To induce divergence, we vary presence and type of fields slightly:
        # We produce a dict of fields as strings, then join with commas.
        # We always produce all six fields, but sometimes with wrong types or nulls.

        # For each field, produce a (key, value) string pair
        # We will vary one or two fields to be wrong or missing by replacing value with null or wrong type string

        # To induce subtle divergence, we pick one or two fields to "corrupt" per record
        fields = ["id", "amount", "name", "status", "tags", "child"]
        corrupt_count = draw(st.integers(min_value=0, max_value=2))
        corrupt_fields = draw(st.lists(st.sampled_from(fields), min_size=corrupt_count, max_size=corrupt_count, unique=True))

        # Build each field string, corrupting if chosen
        def field_str(field):
            if field == "id":
                if "id" in corrupt_fields:
                    # corrupt id: produce string instead of int, or null
                    corrupt_id = draw(st.one_of(
                        st.text(min_size=1, max_size=5, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).map(json_string),
                        st.just("null"),
                    ))
                    return '"id":' + corrupt_id
                else:
                    return '"id":' + draw(id_strat)

            elif field == "amount":
                if "amount" in corrupt_fields:
                    # corrupt amount: produce number instead of string, or null
                    corrupt_amount = draw(st.one_of(
                        st.integers(min_value=-1000, max_value=1000).map(str),
                        st.just("null"),
                    ))
                    return '"amount":' + corrupt_amount
                else:
                    return '"amount":' + draw(amount_strat)

            elif field == "name":
                if "name" in corrupt_fields:
                    # corrupt name: produce number instead of string or null
                    corrupt_name = draw(st.one_of(
                        st.integers(min_value=-1000, max_value=1000).map(str),
                        st.just("null"),
                    ))
                    return '"name":' + corrupt_name
                else:
                    return '"name":' + draw(name_strat)

            elif field == "status":
                if "status" in corrupt_fields:
                    # corrupt status: produce invalid string, number, or null
                    corrupt_status = draw(st.one_of(
                        st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string),
                        st.integers(min_value=0, max_value=10).map(str),
                        st.just("null"),
                    ))
                    return '"status":' + corrupt_status
                else:
                    return '"status":' + draw(status_strat)

            elif field == "tags":
                if "tags" in corrupt_fields:
                    # corrupt tags: produce array with null elements, or string instead of array, or null
                    corrupt_tags = draw(st.one_of(
                        # array with null element
                        st.just('[null]'),
                        # string instead of array
                        st.text(min_size=1, max_size=5, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).map(json_string),
                        st.just("null"),
                    ))
                    return '"tags":' + corrupt_tags
                else:
                    return '"tags":' + draw(tags_strat)

            elif field == "child":
                if "child" in corrupt_fields:
                    # corrupt child: produce number, string, or invalid object (missing fields)
                    corrupt_child = draw(st.one_of(
                        st.integers(min_value=0, max_value=1000).map(str),
                        st.text(min_size=1, max_size=5, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).map(json_string),
                        # invalid object missing fields: e.g. {"foo":123}
                        st.just('{"foo":123}'),
                        st.just("null"),
                    ))
                    return '"child":' + corrupt_child
                else:
                    return '"child":' + draw(child_strat)

        # Compose fields in fixed order for consistency
        field_strs = [field_str(f) for f in fields]

        json_obj = "{" + ",".join(field_strs) + "}"
        return st.just(json_obj)

    # Draw the top-level record with depth=1 (one level of recursion allowed)
    json_text = draw(record_json(depth=1))
    return json_text.encode("utf-8")