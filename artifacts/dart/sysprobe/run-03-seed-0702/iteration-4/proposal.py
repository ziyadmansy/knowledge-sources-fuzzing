from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum "status"
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal with proper escaping of " and \
    def json_string(s: str) -> str:
        # minimal escaping for " and \ only, enough for this context
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id: integer, required, non-null
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))

    # amount: string, required, non-null
    # Use decimal-like strings, but also test boundary cases like empty string or "0"
    amount_val = draw(st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s)),
        st.just("0"),
        st.just("123.45"),
        st.just("0.0"),
    ))

    # name: nullable string, required (present, can be null)
    # To maximize divergence, sometimes produce null, sometimes string, never missing
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))

    # status: enum string, required, non-null, case-sensitive
    # To maximize divergence, mostly valid, but sometimes invalid casing or unknown to trigger rejection
    # But per known facts, all reject invalid enum values, so keep valid here to avoid all rejecting
    status_val = draw(st.sampled_from(statuses))

    # tags: array of strings, required, non-null
    # built_value accepts null tags as empty array, others reject null tags
    # To maximize divergence, sometimes produce null tags (to trigger built_value acceptance but others reject)
    # or produce empty array or array of strings
    tags_null_or_array = draw(st.one_of(
        st.none(),
        st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5)
    ))

    # child: nullable Record, required (present, can be null)
    # To keep recursion bounded, limit to one level of recursion
    # child can be null or a valid record with same rules but no further nesting (child.child always null)
    # To maximize divergence, sometimes produce child with null tags (built_value accepts, others reject)
    # or child with null name, or child with null child (allowed)
    # Also test child with missing fields is rejected by all except built_value (which accepts missing tags and child)
    # But missing fields cause rejection by all except built_value only for tags and child, so we keep all fields present for child to avoid all rejecting

    # Compose child record fields similarly but with no further recursion (child.child always null)
    def child_record():
        child_id = draw(st.integers(min_value=0, max_value=2**31-1))
        child_amount = draw(st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s)),
            st.just("0"),
            st.just("123.45"),
            st.just("0.0"),
        ))
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        child_status = draw(st.sampled_from(statuses))
        child_tags = draw(st.one_of(
            st.none(),  # built_value accepts null tags in child
            st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5)
        ))
        # child.child always null to keep one-level recursion
        child_child = None

        # Build JSON text for child record
        # Always include all six fields (id, amount, name, status, tags, child)
        # name and child can be null, tags can be null or array
        parts = []
        parts.append('"id":' + str(child_id))
        parts.append('"amount":' + json_string(child_amount))
        parts.append('"name":' + ("null" if child_name is None else json_string(child_name)))
        parts.append('"status":' + json_string(child_status))
        if child_tags is None:
            parts.append('"tags":null')
        else:
            tags_json = "[" + ",".join(json_string(t) for t in child_tags) + "]"
            parts.append('"tags":' + tags_json)
        parts.append('"child":null')

        return "{" + ",".join(parts) + "}"

    # Decide child presence: null or a child record
    child_val = draw(st.one_of(st.none(), st.just(child_record())))

    # Compose top-level JSON object fields
    # Always include all six fields (id, amount, name, status, tags, child)
    # name and child can be null, tags can be null or array
    parts = []
    parts.append('"id":' + str(id_val))
    parts.append('"amount":' + json_string(amount_val))
    parts.append('"name":' + ("null" if name_val is None else json_string(name_val)))
    parts.append('"status":' + json_string(status_val))
    if tags_null_or_array is None:
        parts.append('"tags":null')
    else:
        tags_json = "[" + ",".join(json_string(t) for t in tags_null_or_array) + "]"
        parts.append('"tags":' + tags_json)
    if child_val is None:
        parts.append('"child":null')
    else:
        parts.append('"child":' + child_val)

    json_text = "{" + ",".join(parts) + "}"

    return json_text.encode("utf-8")