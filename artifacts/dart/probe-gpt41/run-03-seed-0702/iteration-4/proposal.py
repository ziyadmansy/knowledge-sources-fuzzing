from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for "status" field
    statuses = st.sampled_from(["active", "inactive", "unknown"])
    # "name" is string or null
    name_str_or_null = st.one_of(st.none(), st.text(min_size=0, max_size=20))
    # "amount" is any string
    amount_str = st.text(min_size=0, max_size=20)
    # "id" is integer
    id_int = st.integers(min_value=0, max_value=1000)
    # "tags" normal: array of strings (possibly empty)
    tags_array = st.lists(st.text(min_size=0, max_size=10), max_size=5)
    # "tags" special: null or object ({}), accepted only by built_value as empty list
    tags_null = st.just("null")
    tags_object = st.just("{}")
    # "tags" normal or special, but never string or array with non-string elements
    tags_choice = st.one_of(
        tags_array.map(lambda arr: "[" + ",".join('"' + s.replace('"', '\\"') + '"' for s in arr) + "]"),
        tags_null,
        tags_object,
    )
    # "name" field presence: present or missing (missing means omit field)
    name_present = st.booleans()
    # "child" is null or a record (one level recursion)
    # We'll define a helper for child record with bounded recursion depth
    def record_strategy(depth):
        if depth <= 0:
            # child must be null at max depth
            return st.just("null")
        else:
            # Compose child record with same fields, but no further recursion (depth-1)
            return st.deferred(lambda: record_strategy(depth - 1)).flatmap(
                lambda child_json: st.tuples(
                    id_int,
                    amount_str,
                    name_str_or_null,
                    statuses,
                    tags_choice,
                    st.just(child_json),
                    name_present,
                ).map(
                    lambda t: _make_record_json(*t)
                )
            )

    def _make_record_json(
        id_val, amount_val, name_val, status_val, tags_val, child_val, name_is_present
    ):
        # Compose JSON object text with proper escaping for strings
        def esc_str(s):
            # Escape backslash and double quote for JSON string
            return s.replace("\\", "\\\\").replace('"', '\\"')

        parts = []
        parts.append('"id":' + str(id_val))
        parts.append('"amount":"' + esc_str(amount_val) + '"')
        if name_is_present:
            if name_val is None:
                parts.append('"name":null')
            else:
                parts.append('"name":"' + esc_str(name_val) + '"')
        # else omit "name"
        parts.append('"status":"' + status_val + '"')
        parts.append('"tags":' + tags_val)
        parts.append('"child":' + child_val)
        return "{" + ",".join(parts) + "}"

    # Top-level record with depth=1 recursion for child
    # Compose top-level record fields
    # We draw child JSON text recursively
    child_json = draw(record_strategy(1))
    id_val = draw(id_int)
    amount_val = draw(amount_str)
    name_val = draw(name_str_or_null)
    status_val = draw(statuses)
    tags_val = draw(tags_choice)
    name_is_present = draw(name_present)

    top_json = _make_record_json(
        id_val, amount_val, name_val, status_val, tags_val, child_json, name_is_present
    )

    # Return bytes
    return top_json.encode("utf-8")