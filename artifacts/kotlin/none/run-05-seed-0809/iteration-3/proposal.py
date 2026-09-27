from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    MAX_DEPTH = 1  # only one level of recursion for "child"

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Escape backslash and double quote
        esc = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{esc}"'

    # Strategy for "id": integer as JSON number (no quotes)
    id_strat = st.integers(min_value=0, max_value=10**9).map(str)

    # Strategy for "amount": string, but sometimes inject malformed types or boundary cases
    # Mostly strings that look like numbers, but sometimes numbers or null or boolean to provoke divergence
    amount_base = st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '"\\'))
    amount_strat = st.one_of(
        amount_base.map(json_string_literal),
        st.integers(min_value=-1000, max_value=1000).map(str),  # number, no quotes
        st.just("null"),
        st.booleans().map(lambda b: "true" if b else "false"),
        st.just('""'),  # empty string
    )

    # Strategy for "name": string or null or sometimes number or boolean to provoke divergence
    name_base = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=15).filter(lambda s: all(c not in s for c in '"\\')).map(json_string_literal),
        st.integers(min_value=-1000, max_value=1000).map(str),
        st.booleans().map(lambda b: "true" if b else "false"),
    )

    # Strategy for "status": one of the three strings, or sometimes a wrong string or null or number to provoke divergence
    status_strat = st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown'] and all(c not in s for c in '"\\')).map(json_string_literal),
        st.just("null"),
        st.integers(min_value=0, max_value=10).map(str),
    )

    # Strategy for "tags": array of strings, or sometimes null, or array with non-string elements to provoke divergence
    tag_str = st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '"\\')).map(json_string_literal)
    tags_array_strat = st.lists(tag_str, min_size=0, max_size=5).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_malformed_strat = st.one_of(
        tags_array_strat,
        st.just("null"),
        st.lists(st.integers(min_value=0, max_value=10).map(str), min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]"),
        st.lists(st.booleans().map(lambda b: "true" if b else "false"), min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]"),
        st.just('""'),  # string instead of array
    )

    # Recursive strategy for "child": either null or a record (depth 1 only)
    # To avoid infinite recursion, pass current depth as argument
    def record_strat(depth: int):
        # If depth > MAX_DEPTH, child must be null
        if depth > MAX_DEPTH:
            return st.just("null")

        # Compose fields for a record at this depth
        def build_record():
            id_val = draw(id_strat)
            amount_val = draw(amount_strat)
            name_val = draw(name_base)
            status_val = draw(status_strat)
            tags_val = draw(tags_malformed_strat)
            child_val = draw(record_strat(depth + 1))

            # Build JSON object string with fields in fixed order
            # Intentionally sometimes omit quotes or use wrong types in fields to provoke divergence
            json_obj = (
                '{'
                f'"id":{id_val},'
                f'"amount":{amount_val},'
                f'"name":{name_val},'
                f'"status":{status_val},'
                f'"tags":{tags_val},'
                f'"child":{child_val}'
                '}'
            )
            return json_obj

        return st.deferred(lambda: st.builds(build_record))

    # Draw the top-level record JSON string
    json_text = draw(record_strat(0))

    # Return as bytes (UTF-8)
    return json_text.encode("utf-8")