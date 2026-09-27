from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Basic atomic fields with valid values
    # id: integer
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    # amount: string, but we will sometimes produce strings that look like numbers or edge cases
    amount_val = draw(st.text(min_size=1, max_size=10))
    # name: string or null
    # We will sometimes produce null, sometimes string, sometimes empty string, sometimes unicode
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
    # status: one of allowed strings, but sometimes we will produce a string that looks similar but invalid
    # To maximize chance of divergence, we produce either valid or a close invalid string (e.g. "active " or "Active")
    status_val = draw(st.one_of(
        st.sampled_from(["active", "inactive", "unknown"]),
        st.text(min_size=1, max_size=8).filter(lambda s: s not in {"active","inactive","unknown"})
    ))
    # tags: array of strings (possibly empty)
    # To maximize chance of divergence, sometimes empty, sometimes with strings, sometimes with strings that look like numbers or empty strings
    tags_len = draw(st.integers(min_value=0, max_value=5))
    tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=tags_len, max_size=tags_len))
    # child: either null or a nested record (one level)
    # We will produce either null or a nested record with fields similar to top-level but with some subtle variations
    # To maximize divergence, child fields may have subtle type or value variations
    def gen_child():
        # id: integer or string (to cause rejection or divergence)
        child_id = draw(st.one_of(st.integers(min_value=0, max_value=2**31-1),
                                  st.text(min_size=1, max_size=5)))
        # amount: string or integer (to cause divergence)
        child_amount = draw(st.one_of(st.text(min_size=1, max_size=10),
                                     st.integers(min_value=0, max_value=1000)))
        # name: string or null or integer (to cause divergence)
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20), st.integers(min_value=0, max_value=1000)))
        # status: valid or invalid string
        child_status = draw(st.one_of(
            st.sampled_from(["active", "inactive", "unknown"]),
            st.text(min_size=1, max_size=8).filter(lambda s: s not in {"active","inactive","unknown"})
        ))
        # tags: list of strings or list with non-string (to cause divergence)
        child_tags_len = draw(st.integers(min_value=0, max_value=3))
        child_tags = draw(st.lists(st.one_of(st.text(min_size=0, max_size=10), st.integers(min_value=0, max_value=1000)),
                                   min_size=child_tags_len, max_size=child_tags_len))
        # child.child: always null to avoid deep recursion
        child_child = "null"
        # Build child JSON text
        # We must produce syntactically valid JSON with correct quoting and commas
        def json_str(v):
            if v is None:
                return "null"
            elif isinstance(v, int):
                return str(v)
            else:
                # escape quotes and backslashes in strings
                esc = v.replace('\\', '\\\\').replace('"', '\\"')
                return f'"{esc}"'
        # tags array
        tags_json = "[" + ",".join(json_str(t) for t in child_tags) + "]"
        child_json = (
            '{'
            f'"id":{json_str(child_id)},'
            f'"amount":{json_str(child_amount)},'
            f'"name":{json_str(child_name)},'
            f'"status":{json_str(child_status)},'
            f'"tags":{tags_json},'
            f'"child":{child_child}'
            '}'
        )
        return child_json

    child_val = draw(st.one_of(st.just("null"), gen_child()))

    # Helper to produce JSON string for top-level fields
    def json_str(v):
        if v is None:
            return "null"
        elif isinstance(v, int):
            return str(v)
        else:
            esc = v.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{esc}"'

    tags_json = "[" + ",".join(json_str(t) for t in tags_list) + "]"

    # Compose top-level JSON text
    # We produce all fields always present, no extra fields
    json_text = (
        '{'
        f'"id":{id_val},'
        f'"amount":{json_str(amount_val)},'
        f'"name":{json_str(name_val)},'
        f'"status":{json_str(status_val)},'
        f'"tags":{tags_json},'
        f'"child":{child_val}'
        '}'
    )

    return json_text.encode("utf-8")