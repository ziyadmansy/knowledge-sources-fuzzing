from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal with proper escaping of " and \ only (minimal)
    def json_string(s: str) -> str:
        # minimal escaping for " and \
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id: integer, always present, non-null
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))

    # amount: string, always present, non-null
    # To maximize divergence, sometimes produce numeric strings that look like numbers,
    # sometimes empty string, sometimes normal strings.
    amount_val = draw(
        st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
            st.integers(min_value=0, max_value=100000).map(str),
            st.just("0"),
            st.just(""),
        )
    )

    # name: nullable string, always present (null or string)
    # To maximize divergence, sometimes null, sometimes empty string, sometimes normal string
    name_val = draw(
        st.one_of(
            st.none(),
            st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
        )
    )

    # status: enum string, always present, non-null
    # To maximize divergence, mostly valid enum, but sometimes invalid casing or unknown value
    # But from known probes, all reject invalid enum values, so mostly produce valid,
    # but occasionally produce a valid enum with trailing space or similar to test subtlety.
    # However, trailing spaces are invalid JSON strings, so we avoid that.
    # Instead, produce valid enum or invalid enum with one char off.
    status_val = draw(
        st.one_of(
            st.sampled_from(STATUS_VALUES),
            st.just("active").map(lambda s: s.upper()),  # "ACTIVE" (invalid)
            st.just("inactive").map(lambda s: s.capitalize()),  # "Inactive" (invalid)
            st.just("unknown").map(lambda s: s + "x"),  # "unknownx" (invalid)
        )
    )

    # tags: array of strings, always present, non-null
    # built_value accepts null tags as empty array, others reject null tags
    # So sometimes produce null tags to cause divergence
    tags_null = draw(st.booleans())
    if tags_null:
        tags_val = None
    else:
        # array of strings, possibly empty, strings without quotes or backslash
        tags_val = draw(
            st.lists(
                st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
                min_size=0,
                max_size=5,
            )
        )

    # child: nullable Record, always present (null or object)
    # built_value accepts missing child, others reject missing child, so always present here
    # To keep recursion bounded, only one level deep
    child_null = draw(st.booleans())
    if child_null:
        child_val = None
    else:
        # child record with same schema but no further recursion (child.child always null)
        # For child, to maximize divergence, sometimes produce null tags, sometimes invalid status, etc.
        child_id = draw(st.integers(min_value=0, max_value=2**31-1))
        child_amount = draw(
            st.one_of(
                st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
                st.integers(min_value=0, max_value=100000).map(str),
                st.just("0"),
                st.just(""),
            )
        )
        child_name = draw(
            st.one_of(
                st.none(),
                st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
            )
        )
        child_status = draw(
            st.one_of(
                st.sampled_from(STATUS_VALUES),
                st.just("active").map(lambda s: s.upper()),
                st.just("inactive").map(lambda s: s.capitalize()),
                st.just("unknown").map(lambda s: s + "x"),
            )
        )
        child_tags_null = draw(st.booleans())
        if child_tags_null:
            child_tags = None
        else:
            child_tags = draw(
                st.lists(
                    st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
                    min_size=0,
                    max_size=5,
                )
            )
        child_child = None  # no further recursion

        # Build child JSON text
        def render_tags(t):
            if t is None:
                return "null"
            else:
                return "[" + ",".join(json_string(x) for x in t) + "]"

        child_obj = (
            '{'
            + f'"id":{child_id},'
            + f'"amount":{json_string(child_amount)},'
            + f'"name":{"null" if child_name is None else json_string(child_name)},'
            + f'"status":{json_string(child_status)},'
            + f'"tags":{render_tags(child_tags)},'
            + f'"child":null'
            + "}"
        )
        child_val = child_obj

    # Build tags JSON text
    def render_tags(t):
        if t is None:
            return "null"
        else:
            return "[" + ",".join(json_string(x) for x in t) + "]"

    # Compose main JSON object text
    # All fields always present
    # For child_val, if None, output null, else output the prebuilt JSON text
    json_text = (
        "{"
        + f'"id":{id_val},'
        + f'"amount":{json_string(amount_val)},'
        + f'"name":{"null" if name_val is None else json_string(name_val)},'
        + f'"status":{json_string(status_val)},'
        + f'"tags":{render_tags(tags_val)},'
        + f'"child":{child_val if child_val is None else child_val}'
        + "}"
    )

    return json_text.encode("utf-8")