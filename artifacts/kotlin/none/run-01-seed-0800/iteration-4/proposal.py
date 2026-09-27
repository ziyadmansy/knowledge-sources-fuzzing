from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with proper escaping for quotes and backslashes
    def json_string(s: str) -> str:
        # minimal escaping for " and \ to keep JSON valid
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Recursive generator for a Record JSON object as text
    # depth controls recursion depth (0 means no child)
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # id: integer (always present)
        id_strat = st.integers(min_value=0, max_value=2**31-1).map(str)

        # amount: string (always present)
        # To induce divergence, sometimes produce numeric strings, sometimes strings with spaces, etc.
        amount_strat = st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '\n\r\t"\\')),  # safe strings
            st.integers(min_value=0, max_value=10**6).map(str),
            st.just("0"),
            st.just("123.45"),
            st.just("1e10"),
        ).map(json_string)

        # name: string or null (always present)
        # To induce divergence, sometimes null, sometimes string, sometimes empty string
        name_strat = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=20).filter(lambda s: all(c not in s for c in '\n\r\t"\\')).map(json_string),
        )

        # status: one of "active", "inactive", "unknown" (always present)
        # To induce divergence, sometimes produce invalid strings or numbers or null
        # But since the schema says always one of three strings, mostly produce valid ones,
        # but occasionally produce invalid to cause rejection divergence.
        status_strat = st.one_of(
            st.sampled_from(statuses),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string),
            st.integers(min_value=0, max_value=10).map(str),
            st.none().map(lambda _: "null"),
        )

        # tags: array of strings (always present)
        # To induce divergence, sometimes empty array, sometimes array with empty strings,
        # sometimes array with nulls (invalid), sometimes array with numbers (invalid)
        # But mostly valid arrays of strings.
        def tag_strat():
            # valid string tags
            valid_tag = st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in '\n\r\t"\\')).map(json_string)
            # invalid tags: null or numbers as strings (to cause divergence)
            invalid_tag = st.one_of(
                st.none().map(lambda _: "null"),
                st.integers(min_value=0, max_value=100).map(str),
            )
            # mix valid and invalid tags to cause divergence
            return st.lists(st.one_of(valid_tag, invalid_tag), min_size=0, max_size=5).map(
                lambda lst: "[" + ",".join(lst) + "]"
            )

        tags_strat = tag_strat()

        # child: Record or null (one level recursion normally)
        # To induce divergence, sometimes null, sometimes a valid record, sometimes invalid type (number, string)
        # Limit recursion depth to 1 (depth=0 means no child)
        if depth <= 0:
            child_strat = st.one_of(
                st.none().map(lambda _: "null"),
                # invalid types to cause divergence
                st.integers(min_value=0, max_value=100).map(str),
                st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '\n\r\t"\\')).map(json_string),
            )
        else:
            # child is either null or a record with depth-1
            child_strat = st.one_of(
                st.none().map(lambda _: "null"),
                record_json(depth - 1),
                # invalid types to cause divergence
                st.integers(min_value=0, max_value=100).map(str),
                st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '\n\r\t"\\')).map(json_string),
            )

        # To induce divergence, sometimes omit a field (invalid), or produce wrong type for a field
        # But mostly produce all fields present and correct type or slightly off type.

        # Decide which fields to omit or corrupt (at most one or two per record)
        # Use a small probability to omit or corrupt a field
        omit_field = draw(st.sampled_from([None, "id", "amount", "name", "status", "tags", "child"]))
        corrupt_field = draw(st.sampled_from([None, "id", "amount", "name", "status", "tags", "child"]))

        # Compose fields as strings
        fields = []

        # id field
        if omit_field != "id":
            if corrupt_field == "id":
                # corrupt id: produce string instead of integer
                corrupt_id = draw(st.text(min_size=1, max_size=5).filter(lambda s: all(c not in s for c in '\n\r\t"\\')))
                fields.append('"id":' + json_string(corrupt_id))
            else:
                id_val = draw(id_strat)
                fields.append('"id":' + id_val)

        # amount field
        if omit_field != "amount":
            if corrupt_field == "amount":
                # corrupt amount: produce number instead of string
                corrupt_amount = draw(st.integers(min_value=0, max_value=100000))
                fields.append('"amount":' + str(corrupt_amount))
            else:
                amount_val = draw(amount_strat)
                fields.append('"amount":' + amount_val)

        # name field
        if omit_field != "name":
            if corrupt_field == "name":
                # corrupt name: produce number instead of string/null
                corrupt_name = draw(st.integers(min_value=0, max_value=1000))
                fields.append('"name":' + str(corrupt_name))
            else:
                name_val = draw(name_strat)
                fields.append('"name":' + name_val)

        # status field
        if omit_field != "status":
            if corrupt_field == "status":
                # corrupt status: produce array instead of string
                corrupt_status = draw(st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(c not in s for c in '\n\r\t"\\')), min_size=1, max_size=3))
                corrupt_status_json = "[" + ",".join(json_string(s) for s in corrupt_status) + "]"
                fields.append('"status":' + corrupt_status_json)
            else:
                status_val = draw(status_strat)
                fields.append('"status":' + status_val)

        # tags field
        if omit_field != "tags":
            if corrupt_field == "tags":
                # corrupt tags: produce string instead of array
                corrupt_tags = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '\n\r\t"\\')))
                fields.append('"tags":' + json_string(corrupt_tags))
            else:
                tags_val = draw(tags_strat)
                fields.append('"tags":' + tags_val)

        # child field
        if omit_field != "child":
            if corrupt_field == "child":
                # corrupt child: produce boolean instead of object/null
                corrupt_child = draw(st.booleans())
                fields.append('"child":' + ("true" if corrupt_child else "false"))
            else:
                child_val = draw(child_strat)
                fields.append('"child":' + child_val)

        # Shuffle fields order to increase diversity
        draw_fields = draw(st.permutations(fields))
        json_obj = "{" + ",".join(draw_fields) + "}"

        return json_obj

    # Generate record with depth=1 (one level of recursion)
    json_text = draw(record_json(depth=1))
    return json_text.encode("utf-8")