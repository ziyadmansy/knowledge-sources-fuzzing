from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Basic building blocks for fields, mostly valid but with small controlled deviations
    # to provoke divergences among the four deserializers.

    # id: normally integer, but allow null or string to provoke type errors
    id_val = draw(
        st.one_of(
            st.integers(min_value=0, max_value=10**6),
            st.just(None),  # null to provoke rejection
            st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()),  # non-numeric string
        )
    )

    # amount: normally string, but allow int or null to provoke type errors
    amount_val = draw(
        st.one_of(
            st.text(min_size=1, max_size=10),
            st.integers(min_value=0, max_value=10**6),
            st.just(None),
        )
    )

    # name: string or null, missing treated as null by all, so we always include it to avoid trivial agreement
    name_val = draw(
        st.one_of(
            st.none(),
            st.text(min_size=0, max_size=10),
        )
    )

    # status: enum "active", "inactive", "unknown"
    # Also try invalid enum values and null to provoke different error types
    status_val = draw(
        st.one_of(
            st.sampled_from(["active", "inactive", "unknown"]),
            st.text(min_size=1, max_size=10).filter(lambda s: s.lower() not in {"active", "inactive", "unknown"}),
            st.just(None),
        )
    )

    # tags: array of strings normally, but built_value accepts null as empty list
    # others reject null. Also try arrays with ints or mixed types to provoke type errors.
    tags_val = draw(
        st.one_of(
            st.lists(st.text(min_size=1, max_size=5), max_size=3),
            st.just(None),
            st.lists(st.one_of(st.text(min_size=1, max_size=5), st.integers()), max_size=3),
        )
    )

    # child: either null or a nested record (one level only)
    # Nested record uses same strategy but limited to valid values or null to keep complexity bounded.
    # To provoke divergences, child can have one field slightly off type.
    def child_record():
        # child record fields: id, amount, name, status, tags, child=null only (no recursion deeper)
        id_c = draw(st.integers(min_value=0, max_value=10**6))
        amount_c = draw(st.text(min_size=1, max_size=10))
        name_c = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        status_c = draw(st.sampled_from(["active", "inactive", "unknown"]))
        tags_c = draw(st.lists(st.text(min_size=1, max_size=5), max_size=3))
        # child child is always null (no deeper recursion)
        return {
            "id": id_c,
            "amount": amount_c,
            "name": name_c,
            "status": status_c,
            "tags": tags_c,
            "child": None,
        }

    child_val = draw(
        st.one_of(
            st.none(),
            st.builds(child_record),
            # Also try child with one field wrong type to provoke nested type errors
            st.builds(
                lambda id_, amount, name, status, tags: {
                    "id": id_,
                    "amount": amount,
                    "name": name,
                    "status": status,
                    "tags": tags,
                    "child": None,
                },
                id_=st.one_of(st.integers(min_value=0, max_value=10**6), st.text(min_size=1, max_size=5)),
                amount=st.one_of(st.text(min_size=1, max_size=10), st.integers()),
                name=st.one_of(st.none(), st.text(min_size=0, max_size=10)),
                status=st.sampled_from(["active", "inactive", "unknown"]),
                tags=st.lists(st.text(min_size=1, max_size=5), max_size=3),
            ),
        )
    )

    # Helper to encode JSON strings with minimal escaping (only backslash and quote)
    def json_str(s):
        # s is str or None
        if s is None:
            return "null"
        # escape backslash and quote
        esc = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'

    # Encode tags array or null
    def json_tags(t):
        if t is None:
            return "null"
        # t is list of strings or mixed types
        elems = []
        for x in t:
            if isinstance(x, str):
                elems.append(json_str(x))
            elif isinstance(x, int):
                elems.append(str(x))
            else:
                # fallback to null if unexpected type
                elems.append("null")
        return "[" + ",".join(elems) + "]"

    # Encode child recursively or null
    def json_child(c):
        if c is None:
            return "null"
        # c is dict with fields
        parts = []
        parts.append(f'"id":{c["id"]}' if isinstance(c["id"], int) else f'"id":{json_str(c["id"])}')
        parts.append(f'"amount":{json_str(c["amount"])}')
        parts.append(f'"name":{json_str(c["name"])}')
        parts.append(f'"status":{json_str(c["status"])}')
        parts.append(f'"tags":{json_tags(c["tags"])}')
        parts.append(f'"child":null')
        return "{" + ",".join(parts) + "}"

    # Compose top-level JSON object string
    parts = []

    # id
    if isinstance(id_val, int):
        parts.append(f'"id":{id_val}')
    elif id_val is None:
        parts.append(f'"id":null')
    else:
        parts.append(f'"id":{json_str(id_val)}')

    # amount
    if isinstance(amount_val, str):
        parts.append(f'"amount":{json_str(amount_val)}')
    elif amount_val is None:
        parts.append(f'"amount":null')
    else:
        parts.append(f'"amount":{amount_val}')

    # name
    parts.append(f'"name":{json_str(name_val)}')

    # status
    parts.append(f'"status":{json_str(status_val)}')

    # tags
    parts.append(f'"tags":{json_tags(tags_val)}')

    # child
    parts.append(f'"child":{json_child(child_val)}')

    json_text = "{" + ",".join(parts) + "}"
    return json_text.encode("utf-8")