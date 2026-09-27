from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal from a Python string
    def json_string(s: str) -> str:
        # Minimal escaping for JSON string (only backslash and quote)
        # Hypothesis strings won't contain control chars by default, so minimal escaping is enough
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return '"' + s + '"'

    # Helper to produce JSON array of strings
    def json_string_array(lst):
        return "[" + ",".join(json_string(s) for s in lst) + "]"

    # Recursive record generator with bounded recursion depth
    @st.composite
    def record(draw, depth=0):
        # id: integer, but try to produce some borderline cases as strings or floats to cause divergence
        # but mostly integers as strings are invalid JSON for id field (which must be integer)
        # So we produce integer as number or as string (wrong type) to cause divergence
        id_value = draw(
            st.one_of(
                st.integers(min_value=-(2**31), max_value=2**31 - 1),
                st.text(min_size=1, max_size=5).filter(lambda x: x.isdigit()),  # string of digits (wrong type)
            )
        )
        if isinstance(id_value, int):
            id_json = str(id_value)
        else:
            id_json = json_string(id_value)

        # amount: string, but try to produce some numeric literals (wrong type) or null (wrong type)
        # or valid strings (including empty)
        amount_value = draw(
            st.one_of(
                st.text(min_size=0, max_size=10),
                st.integers(min_value=0, max_value=1000000).map(str),
                st.floats(allow_nan=False, allow_infinity=False).map(lambda f: format(f, "g")),
                st.just("null"),  # string "null"
            )
        )
        # amount must be a JSON string, so if amount_value is "null" string, encode as string
        # if amount_value is numeric string, encode as string
        # if amount_value is float string, encode as string
        amount_json = json_string(amount_value)

        # name: string or null
        # To cause divergence, sometimes produce null literal, sometimes string "null", sometimes empty string
        name_value = draw(
            st.one_of(
                st.none(),
                st.text(min_size=0, max_size=10),
                st.just("null"),
            )
        )
        if name_value is None:
            name_json = "null"
        else:
            name_json = json_string(name_value)

        # status: one of the three strings, but also try to produce wrong strings or null to cause divergence
        status_value = draw(
            st.one_of(
                st.sampled_from(statuses),
                st.text(min_size=1, max_size=7).filter(lambda s: s not in statuses),
                st.none(),
            )
        )
        if status_value is None:
            status_json = "null"
        else:
            status_json = json_string(status_value)

        # tags: array of strings
        # To cause divergence, sometimes produce empty array, sometimes array with null or numbers (wrong types)
        # but mostly array of strings
        tags_list = draw(
            st.lists(
                st.one_of(
                    st.text(min_size=0, max_size=5),
                    st.none(),
                    st.integers(min_value=0, max_value=10).map(str),
                ),
                min_size=0,
                max_size=4,
            )
        )
        # encode tags array, nulls as null literals, others as strings
        def encode_tag(t):
            if t is None:
                return "null"
            else:
                return json_string(t)

        tags_json = "[" + ",".join(encode_tag(t) for t in tags_list) + "]"

        # child: null or another record (one level recursion max)
        if depth >= 1:
            # no further recursion, only null
            child_json = "null"
        else:
            child_choice = draw(st.one_of(st.just("null"), record(depth=depth + 1)))
            if child_choice == "null":
                child_json = "null"
            else:
                child_json = child_choice

        # Compose JSON object string
        # To cause divergence, sometimes reorder fields or produce extra whitespace
        # But field order is usually stable, so keep order fixed for clarity

        # Compose fields with optional whitespace around colons and commas
        ws1 = draw(st.one_of(st.just(""), st.just(" "), st.just("\n"), st.just("\t")))
        ws2 = draw(st.one_of(st.just(""), st.just(" "), st.just("\n"), st.just("\t")))
        ws3 = draw(st.one_of(st.just(""), st.just(" "), st.just("\n"), st.just("\t")))
        ws4 = draw(st.one_of(st.just(""), st.just(" "), st.just("\n"), st.just("\t")))
        ws5 = draw(st.one_of(st.just(""), st.just(" "), st.just("\n"), st.just("\t")))
        ws6 = draw(st.one_of(st.just(""), st.just(" "), st.just("\n"), st.just("\t")))

        json_obj = (
            "{" +
            ws1 + '"id"' + ws2 + ":" + ws3 + id_json + "," +
            ws4 + '"amount"' + ws5 + ":" + ws6 + amount_json + "," +
            '"name":' + name_json + "," +
            '"status":' + status_json + "," +
            '"tags":' + tags_json + "," +
            '"child":' + child_json +
            "}"
        )
        return json_obj

    # Draw top-level record and encode as bytes
    json_text = draw(record())
    return json_text.encode("utf-8")