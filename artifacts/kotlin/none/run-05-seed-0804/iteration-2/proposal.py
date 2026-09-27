from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal with proper escaping for quotes and backslashes
    def json_string(s: str) -> str:
        # Escape backslash and double quote
        s_escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s_escaped}"'

    # Helper to produce JSON array of strings
    def json_string_array(strings) -> str:
        return "[" + ",".join(json_string(s) for s in strings) + "]"

    # Helper to produce JSON null or a JSON string or null for "name"
    # We want to sometimes produce null, sometimes a string, sometimes a wrong type (to cause divergence)
    # But mostly keep it valid or almost valid.
    # We'll do this at the record level.

    # Recursive record generator with bounded depth
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # At max depth, child must be null or omitted (we always include child field, but can be null)
        max_depth = 1

        # id: integer, but we can try to sometimes produce a string or float to cause divergence
        # amount: string, but sometimes produce a number or null or boolean
        # name: string or null, sometimes produce a number or boolean or missing (but missing is not allowed, so produce null or wrong type)
        # status: one of "active", "inactive", "unknown", sometimes produce a wrong string or null or number
        # tags: array of strings, sometimes empty, sometimes with wrong types inside or null
        # child: record or null

        # To keep "almost" well-formed, we mostly produce correct types, but sometimes one field is off.

        # We pick one field to "corrupt" per record to cause divergence.

        # Choose which field to corrupt or None for no corruption
        corrupt_field = draw(st.one_of(
            st.just(None),
            st.sampled_from(["id", "amount", "name", "status", "tags", "child"])
        ))

        # id field
        if corrupt_field == "id":
            # corrupt id: produce string or float or null instead of integer
            id_val = draw(st.one_of(
                st.integers(min_value=0, max_value=10**9).map(str),
                st.floats(allow_nan=False, allow_infinity=False).map(lambda f: f"{f}"),
                st.just("null"),
                st.text(min_size=1, max_size=5).map(json_string)
            ))
            id_json = id_val if id_val in ("null",) or id_val.replace(".", "", 1).isdigit() else id_val
        else:
            id_json = str(draw(st.integers(min_value=0, max_value=10**9)))

        # amount field
        if corrupt_field == "amount":
            # corrupt amount: produce number, null, boolean, or malformed string (unquoted)
            amount_val = draw(st.one_of(
                st.text(min_size=0, max_size=10).map(json_string),
                st.integers(min_value=0, max_value=10**9).map(str),
                st.floats(allow_nan=False, allow_infinity=False).map(lambda f: f"{f}"),
                st.just("null"),
                st.just("true"),
                st.just("false"),
                st.text(min_size=1, max_size=5)  # unquoted string (invalid JSON string)
            ))
            # If unquoted string, use as is, else if string literal, use as is
            if amount_val in ("null", "true", "false") or amount_val.replace(".", "", 1).isdigit():
                amount_json = amount_val
            elif amount_val.startswith('"') and amount_val.endswith('"'):
                amount_json = amount_val
            else:
                # unquoted string (invalid JSON string)
                amount_json = amount_val
        else:
            # valid string amount
            amount_json = json_string(draw(st.text(min_size=1, max_size=10)))

        # name field
        if corrupt_field == "name":
            # corrupt name: produce number, boolean, or missing (we never omit fields, so produce null or wrong type)
            name_val = draw(st.one_of(
                st.none().map(lambda _: "null"),
                st.text(min_size=0, max_size=10).map(json_string),
                st.integers(min_value=0, max_value=10**9).map(str),
                st.just("true"),
                st.just("false"),
                st.text(min_size=1, max_size=5)  # unquoted string (invalid JSON string)
            ))
            if name_val in ("null", "true", "false") or name_val.replace(".", "", 1).isdigit():
                name_json = name_val
            elif name_val.startswith('"') and name_val.endswith('"'):
                name_json = name_val
            else:
                name_json = name_val
        else:
            # valid string or null
            name_json = draw(st.one_of(
                st.none().map(lambda _: "null"),
                st.text(min_size=0, max_size=10).map(json_string)
            ))

        # status field
        if corrupt_field == "status":
            # corrupt status: produce invalid string, null, number, boolean
            status_val = draw(st.one_of(
                st.sampled_from(statuses).map(json_string),
                st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses).map(json_string),
                st.just("null"),
                st.integers(min_value=0, max_value=10**9).map(str),
                st.just("true"),
                st.just("false"),
            ))
            status_json = status_val
        else:
            status_json = json_string(draw(st.sampled_from(statuses)))

        # tags field
        if corrupt_field == "tags":
            # corrupt tags: produce null, array with non-string elements, or string instead of array
            tags_val = draw(st.one_of(
                st.none().map(lambda _: "null"),
                st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=5).map(json_string_array),
                st.lists(st.one_of(
                    st.text(min_size=0, max_size=5).map(json_string),
                    st.integers(min_value=0, max_value=10**9).map(str),
                    st.just("null"),
                    st.just("true"),
                    st.just("false"),
                ), min_size=0, max_size=5).map(lambda arr: "[" + ",".join(arr) + "]"),
                st.text(min_size=1, max_size=5).map(json_string)  # string instead of array
            ))
            tags_json = tags_val
        else:
            tags_json = json_string_array(draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=5)))

        # child field
        if depth >= max_depth:
            # must be null or corrupt (if corrupt_field == "child")
            if corrupt_field == "child":
                child_val = draw(st.one_of(
                    st.none().map(lambda _: "null"),
                    st.text(min_size=1, max_size=10),  # invalid JSON value (unquoted string)
                    st.just("true"),
                    st.just("false"),
                    st.integers(min_value=0, max_value=10**9).map(str),
                ))
                child_json = child_val if child_val == "null" or child_val in ("true", "false") or child_val.isdigit() else json_string(child_val)
            else:
                child_json = "null"
        else:
            if corrupt_field == "child":
                # corrupt child: produce invalid JSON or wrong type
                child_val = draw(st.one_of(
                    st.none().map(lambda _: "null"),
                    st.text(min_size=1, max_size=10),  # invalid JSON value (unquoted string)
                    st.just("true"),
                    st.just("false"),
                    st.integers(min_value=0, max_value=10**9).map(str),
                ))
                child_json = child_val if child_val == "null" or child_val in ("true", "false") or child_val.isdigit() else json_string(child_val)
            else:
                # valid child record or null
                use_child = draw(st.booleans())
                if use_child:
                    child_json = draw(record_json(depth + 1))
                else:
                    child_json = "null"

        # Compose JSON object string with all fields in order
        json_obj = (
            "{" +
            f'"id":{id_json},' +
            f'"amount":{amount_json},' +
            f'"name":{name_json},' +
            f'"status":{status_json},' +
            f'"tags":{tags_json},' +
            f'"child":{child_json}' +
            "}"
        )
        return json_obj

    # Draw top-level record JSON string
    json_text = draw(record_json(0))
    return json_text.encode("utf-8")