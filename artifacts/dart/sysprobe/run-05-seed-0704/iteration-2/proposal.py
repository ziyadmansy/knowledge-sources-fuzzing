from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum "status"
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # minimal escaping for " and \ to keep JSON valid
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Recursive record generator with bounded depth (max 2 levels: root + child)
    def record(depth: int) -> st.SearchStrategy[str]:
        # id: integer, always present, non-null
        id_strat = st.integers(min_value=-(2**31), max_value=2**31 - 1).map(str)

        # amount: string, always present, non-null
        # To maximize divergence, allow strings that look numeric or empty or whitespace
        amount_strat = st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
            st.just("0"),
            st.just(""),
            st.just(" "),
            st.just("123.45"),
            st.just("-0.01"),
        ).map(json_string)

        # name: nullable string (string or null)
        # To maximize divergence, allow null or string, including empty string
        name_strat = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string),
        )

        # status: enum string, always present, non-null
        # To maximize divergence, mostly valid enum but sometimes invalid or case variants
        # But known that invalid enum causes all reject, so mostly valid + some case variants
        status_strat = st.one_of(
            st.sampled_from(statuses).map(json_string),
            st.sampled_from(["ACTIVE", "Inactive", "Unknown"]).map(json_string),  # case variants known to reject all
            st.just(json_string("invalid")),  # known to reject all
        )

        # tags: array of strings, always present, non-null
        # built_value accepts null tags and converts to empty array, others reject null tags
        # So sometimes produce null tags to cause divergence
        # Also test empty array, array with empty string, array with multiple strings
        tags_strat = st.one_of(
            st.lists(
                st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
                min_size=0,
                max_size=3,
            ).map(lambda lst: "[" + ",".join(json_string(s) for s in lst) + "]"),
            st.just("null"),  # triggers divergence: built_value accepts, others reject
        )

        # child: nullable record or null
        # built_value accepts missing child (defaults null), others reject missing child
        # To maximize divergence, sometimes omit child field (simulate missing), sometimes present null, sometimes present valid child
        # But we must produce syntactically valid JSON objects with all six fields always present (per schema)
        # So we cannot omit child field at top-level, but can test null or nested record
        # To test nested missing fields or nulls beyond one level, produce child with some fields null or missing (but missing fields cause rejection)
        # So produce child with all fields present but sometimes null where allowed (name, child)
        # For child, limit depth to 1 (no grandchild)
        if depth >= 1:
            # At max depth, child must be null (to avoid infinite recursion)
            child_strat = st.just("null")
        else:
            # child can be null or a nested record with depth+1
            child_strat = st.one_of(
                st.just("null"),
                record(depth + 1),
            )

        # Compose the record JSON object string
        # To maximize divergence, sometimes produce wrong types for fields that cause divergence:
        # But known that all reject null for id, amount, status, tags (except built_value accepts null tags)
        # So we do not produce null for id, amount, status
        # But produce null tags sometimes
        # Also produce some invalid enum values sometimes (known to reject all)
        # Also produce some case variants of enum (known to reject all)
        # Also produce empty tags array, or null tags
        # Also produce child null or nested record

        # id field
        id_val = draw(id_strat)
        # amount field
        amount_val = draw(amount_strat)
        # name field
        name_val = draw(name_strat)
        # status field
        status_val = draw(status_strat)
        # tags field
        tags_val = draw(tags_strat)
        # child field
        child_val = draw(child_strat)

        # Build JSON object string with all six fields present, in fixed order
        # Use no extra whitespace to keep JSON minimal
        json_obj = (
            '{'
            + '"id":' + id_val + ','
            + '"amount":' + amount_val + ','
            + '"name":' + name_val + ','
            + '"status":' + status_val + ','
            + '"tags":' + tags_val + ','
            + '"child":' + child_val
            + '}'
        )
        return json_obj

    # Draw the top-level record string
    top_record = draw(record(0))
    # Return as bytes
    return top_record.encode("utf-8")