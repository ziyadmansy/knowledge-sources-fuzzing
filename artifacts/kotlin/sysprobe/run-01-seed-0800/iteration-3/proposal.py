from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and nullability
    STATUS_VALUES = ["active", "inactive", "unknown"]
    STATUS_INVALIDS = ["Active", "inactivee", "unknown ", "null", ""]

    # Helper: produce a JSON string literal with proper escaping for simple ASCII (no escapes needed here)
    def q(s: str) -> str:
        # Minimal escaping for quotes and backslashes
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Strategy for "id": integer normally, but also try missing or null or wrong type for divergence
    # Gson accepts missing (->0), Moshi/kotlinx/Jackson reject missing
    # Gson accepts null (->0?), others reject null for non-nullable int
    # Gson accepts string "0" for int? Not known, so skip string for int.
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=1000).map(str),
        st.just("null"),       # null for non-nullable int
        st.just("0"),          # zero as string (wrong type)
        st.just(None),         # missing field (handled by omitting)
    )

    # Strategy for "amount": string normally, but also number, null, missing
    # Gson accepts string or number or null (even though non-nullable string)
    # Moshi rejects number and null
    # kotlinx rejects number and null
    # Jackson rejects null and number
    amount_strategy = st.one_of(
        st.text(min_size=0, max_size=10).map(q),
        st.integers(min_value=0, max_value=1000).map(str),  # number (unquoted)
        st.just("null"),
        st.just(None),  # missing
    )

    # Strategy for "name": nullable string
    # Gson and Jackson accept null, Moshi and kotlinx reject null for non-nullable fields but name is nullable
    # So all accept null for "name"
    # Also try missing (should be rejected by Moshi/kotlinx/Jackson, accepted by Gson)
    name_strategy = st.one_of(
        st.none(),  # null
        st.text(min_size=0, max_size=10).map(q),
        st.just(None),  # missing
    )

    # Strategy for "status": enum string normally, also invalid enum string, null, missing
    # Gson accepts invalid enum as null, others reject invalid enum
    # Gson rejects null? Known: Gson accepts null for nullable fields, status is non-nullable, so null rejected?
    # Known: Gson accepts unknown enum as null, so null is accepted? Not explicitly stated, but safer to test null.
    status_strategy = st.one_of(
        st.sampled_from(STATUS_VALUES).map(q),
        st.sampled_from(STATUS_INVALIDS).map(q),
        st.just("null"),
        st.just(None),  # missing
    )

    # Strategy for "tags": array of strings, non-nullable
    # Gson accepts null? Known: Gson accepts null for non-nullable fields? For tags, no explicit mention, but "tags" is non-nullable array
    # Moshi/kotlinx/Jackson reject null or missing
    # Try empty array, array with strings, null, missing
    tags_strategy = st.one_of(
        st.lists(st.text(min_size=0, max_size=5), max_size=3).map(
            lambda lst: "[" + ",".join(q(s) for s in lst) + "]"
        ),
        st.just("null"),
        st.just(None),  # missing
    )

    # Recursive "child" field: nullable Record or null or missing
    # Gson accepts missing child as null, Moshi/kotlinx reject missing, Jackson accepts missing
    # Gson accepts empty object with missing fields for child.child, others reject
    # Limit recursion depth to 1 (child.child is null or empty object)
    # We'll generate child as:
    # - null
    # - missing
    # - a record with all fields present (recursion depth 1)
    # - a record with empty object (all fields missing) for child.child (depth 2)
    # - a record with one field missing or wrong type for divergence

    # To avoid infinite recursion, define a helper for child record generation with depth control
    def child_record(draw, depth=0):
        # At depth 1, child.child must be null or empty object (no further recursion)
        if depth >= 1:
            # child.child is null or empty object
            child_child_choice = draw(st.sampled_from(["null", "empty"]))
            if child_child_choice == "null":
                child_child_json = "null"
            else:
                # empty object: {}
                child_child_json = "{}"
            # Compose child record with all fields present and valid except child replaced by above
            id_val = draw(st.integers(min_value=0, max_value=1000))
            amount_val = draw(st.text(min_size=0, max_size=10))
            name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            status_val = draw(st.sampled_from(STATUS_VALUES))
            tags_val = draw(st.lists(st.text(min_size=0, max_size=5), max_size=3))
            # Build JSON string for child record
            parts = [
                '"id":' + str(id_val),
                '"amount":' + q(amount_val),
                '"name":' + ("null" if name_val is None else q(name_val)),
                '"status":' + q(status_val),
                '"tags":[' + ",".join(q(t) for t in tags_val) + "]",
                '"child":' + child_child_json,
            ]
            return "{" + ",".join(parts) + "}"
        else:
            # depth 0: child can be null, missing, or a record with depth=1
            choice = draw(st.sampled_from(["null", "missing", "record"]))
            if choice == "null":
                return "null"
            elif choice == "missing":
                return None
            else:
                return child_record(draw, depth=1)

    # Compose top-level record with possibility of missing fields or nulls or wrong types for divergence
    # We vary one or two fields at a time to maximize divergence

    # Draw id
    id_choice = draw(st.one_of(
        st.integers(min_value=0, max_value=1000).map(str),
        st.just("null"),
        st.just(None),  # missing
        st.just("0"),   # string zero (wrong type)
    ))

    # Draw amount
    amount_choice = draw(st.one_of(
        st.text(min_size=0, max_size=10).map(q),
        st.integers(min_value=0, max_value=1000).map(str),
        st.just("null"),
        st.just(None),  # missing
    ))

    # Draw name
    name_choice = draw(st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(q),
        st.just(None),  # missing
    ))

    # Draw status
    status_choice = draw(st.one_of(
        st.sampled_from(STATUS_VALUES).map(q),
        st.sampled_from(STATUS_INVALIDS).map(q),
        st.just("null"),
        st.just(None),  # missing
    ))

    # Draw tags
    tags_choice = draw(st.one_of(
        st.lists(st.text(min_size=0, max_size=5), max_size=3).map(
            lambda lst: "[" + ",".join(q(s) for s in lst) + "]"
        ),
        st.just("null"),
        st.just(None),  # missing
    ))

    # Draw child
    child_choice = child_record(draw, depth=0)

    # Build JSON parts, omitting fields with None (missing)
    parts = []
    if id_choice is not None:
        parts.append('"id":' + id_choice)
    if amount_choice is not None:
        parts.append('"amount":' + amount_choice)
    if name_choice is not None:
        parts.append('"name":' + name_choice)
    if status_choice is not None:
        parts.append('"status":' + status_choice)
    if tags_choice is not None:
        parts.append('"tags":' + tags_choice)
    if child_choice is not None:
        parts.append('"child":' + child_choice)

    json_text = "{" + ",".join(parts) + "}"
    return json_text.encode("utf-8")