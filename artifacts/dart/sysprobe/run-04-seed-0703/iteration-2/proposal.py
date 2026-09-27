from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum status
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # minimal escaping for " and \ to keep valid JSON strings
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Strategy for "id": integer (required, non-null)
    id_strat = st.integers(min_value=-(2**53), max_value=2**53-1).map(str)

    # Strategy for "amount": string (required, non-null)
    # Use decimal-like strings, but also allow edge cases like empty string or "0"
    amount_strat = st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string)

    # Strategy for "name": string or null
    # null is literal null, string is JSON string literal
    name_strat = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=20).filter(lambda s: '"' not in s and '\\' not in s).map(json_string),
    )

    # Strategy for "status": one of the three valid enum strings (always lowercase)
    status_strat = st.sampled_from(statuses).map(json_string)

    # Strategy for "tags": array of strings (non-null except built_value accepts null)
    # We want to produce either:
    # - a valid array of strings (including empty array)
    # - or null (to test built_value acceptance)
    # We'll produce mostly valid arrays, but sometimes null to trigger divergence.
    tags_array_strat = st.lists(
        st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string),
        max_size=5,
    ).map(lambda lst: "[" + ",".join(lst) + "]")

    tags_strat = st.one_of(
        tags_array_strat,
        st.just("null"),
    )

    # Forward declaration for child record, to allow one level recursion
    # We limit recursion depth to 1 (child can be null or a record with child=null)
    # To avoid infinite recursion, we pass a parameter _depth
    def record_strat(_depth=0):
        # If depth > 0, child must be null (to limit recursion)
        # If depth == 0, child can be null or a record with depth=1
        child_strat = st.one_of(
            st.just("null"),
            record_strat(_depth=1) if _depth == 0 else st.just("null"),
        )

        # Compose fields as strings, then join with commas inside {}
        # We will produce a dict with all six fields always present (except child can be null)
        # We will vary one or two fields to be slightly off to trigger divergence:
        # - sometimes tags=null (allowed only by built_value)
        # - sometimes missing fields is rejected by all, so we won't omit fields here
        # - sometimes wrong type for a field (e.g. id as string number vs integer number) is rejected by all, so avoid that
        # - instead, we produce mostly valid fields but vary tags and child as above

        id_val = draw(id_strat)
        amount_val = draw(amount_strat)
        name_val = draw(name_strat)
        status_val = draw(status_strat)
        tags_val = draw(tags_strat)
        child_val = draw(child_strat)

        # Build JSON object string
        # All keys quoted, values are JSON literals or objects
        # Order keys as per schema: id, amount, name, status, tags, child
        obj = (
            '{'
            + '"id":' + id_val + ','
            + '"amount":' + amount_val + ','
            + '"name":' + name_val + ','
            + '"status":' + status_val + ','
            + '"tags":' + tags_val + ','
            + '"child":' + child_val
            + '}'
        )
        return obj

    # Generate top-level record with depth=0
    json_obj = draw(record_strat(_depth=0))

    # Return as bytes
    return json_obj.encode("utf-8")