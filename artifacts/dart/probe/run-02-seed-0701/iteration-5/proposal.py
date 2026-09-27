from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]
    MAX_RECURSION_DEPTH = 1

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Minimal escaping for quotes and backslash
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return '"' + escaped + '"'

    # Helper to produce a JSON array of strings
    def json_array_of_strings(lst):
        # lst is list of strings
        return "[" + ",".join(json_string_literal(x) for x in lst) + "]"

    # Helper to produce a JSON integer literal
    def json_int(i: int) -> str:
        return str(i)

    # Helper to produce a JSON string literal for "amount" field (always string)
    # We'll produce strings that look like numbers, or edge cases like empty string, "0", "-0", "0.0", "1e10"
    # but always strings.
    amount_strat = st.one_of(
        st.just("0"),
        st.just("-0"),
        st.just("0.0"),
        st.just("1e10"),
        st.just("123.45"),
        st.just(""),
        st.text(min_size=1, max_size=10).filter(lambda s: all(c not in '"\\' for c in s)),  # safe string without quotes or backslash
    )

    # Helper to produce "name" field: string or null
    # We'll produce either null or a string (possibly empty)
    name_strat = st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20).filter(lambda s: all(c not in '"\\' for c in s)),
    )

    # Helper to produce "status" field: one of the enum strings
    status_strat = st.sampled_from(STATUS_VALUES)

    # Helper to produce "tags" field: array of strings (non-null)
    # We will produce either a non-empty or empty array of strings (strings safe for JSON)
    tags_strat = st.lists(
        st.text(min_size=0, max_size=10).filter(lambda s: all(c not in '"\\' for c in s)),
        min_size=0,
        max_size=5,
    )

    # Helper to produce "id" field: integer
    id_strat = st.integers(min_value=0, max_value=1000000)

    # Compose a record JSON object as string, with bounded recursion depth
    def record_json(depth=0):
        # Draw fields
        # id: integer (required)
        id_val = draw(id_strat)
        id_json = '"id":' + json_int(id_val)

        # amount: string (required)
        amount_val = draw(amount_strat)
        amount_json = '"amount":' + json_string_literal(amount_val)

        # name: string or null (nullable)
        name_val = draw(name_strat)
        if name_val is None:
            name_json = '"name":null'
        else:
            name_json = '"name":' + json_string_literal(name_val)

        # status: enum string (required)
        status_val = draw(status_strat)
        status_json = '"status":' + json_string_literal(status_val)

        # tags: array of strings (required, non-null)
        tags_val = draw(tags_strat)
        tags_json = '"tags":' + json_array_of_strings(tags_val)

        # child: nullable Record or null
        if depth < MAX_RECURSION_DEPTH:
            # 50% chance null, 50% chance nested record
            child_is_null = draw(st.booleans())
            if child_is_null:
                child_json = '"child":null'
            else:
                nested = record_json(depth + 1)
                child_json = '"child":' + nested
        else:
            # At max depth, child must be null
            child_json = '"child":null'

        # Compose fields in random order to avoid bias
        fields = [id_json, amount_json, name_json, status_json, tags_json, child_json]
        draw(st.permutations(fields))  # shuffle fields
        # Actually, Hypothesis does not support draw(st.permutations(...)) directly,
        # so shuffle manually:
        import random
        random.shuffle(fields)

        # Join fields with commas
        obj = "{" + ",".join(fields) + "}"
        return obj

    # Generate the top-level record JSON string
    json_str = record_json()

    # Return as bytes
    return json_str.encode("utf-8")