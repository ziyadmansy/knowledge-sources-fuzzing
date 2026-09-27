from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Escape backslash and double quotes for JSON string
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Strategy for "id": integer, but sometimes as string (to induce divergence)
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=2**31 - 1).map(str),
        st.text(min_size=1, max_size=5).map(json_string_literal),  # string instead of int
    )

    # Strategy for "amount": string normally representing a decimal number, but sometimes a number (no quotes)
    amount_decimal_str = st.decimals(min_value=0, max_value=1e6, places=2).map(lambda d: json_string_literal(format(d, 'f')))
    amount_number = st.decimals(min_value=0, max_value=1e6, places=2).map(lambda d: format(d, 'f'))  # number, no quotes
    amount_strategy = st.one_of(amount_decimal_str, amount_number)

    # Strategy for "name": string or null, but sometimes number or boolean (to induce divergence)
    name_string = st.text(min_size=0, max_size=10).map(json_string_literal)
    name_null = st.just("null")
    name_number = st.integers(min_value=-100, max_value=100).map(str)
    name_boolean = st.booleans().map(lambda b: "true" if b else "false")
    name_strategy = st.one_of(name_string, name_null, name_number, name_boolean)

    # Strategy for "status": one of the three strings, but sometimes null or invalid string
    status_valid = st.sampled_from(statuses)
    status_null = st.just("null")
    status_invalid_string = st.text(min_size=1, max_size=7).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string_literal)
    status_strategy = st.one_of(status_valid, status_null, status_invalid_string)

    # Strategy for "tags": array of strings, but sometimes null or array of numbers or mixed
    tag_string = st.text(min_size=0, max_size=5).map(json_string_literal)
    tag_number = st.integers(min_value=0, max_value=100).map(str)
    tags_strings = st.lists(tag_string, min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_numbers = st.lists(tag_number, min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_mixed = st.lists(st.one_of(tag_string, tag_number), min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_null = st.just("null")
    tags_strategy = st.one_of(tags_strings, tags_numbers, tags_mixed, tags_null)

    # Recursive strategy for "child": either null or a nested record (one level only)
    # To avoid deep recursion, child can only be null or a record with child=null
    @st.defines_strategy
    def record_strategy():
        # Compose the record fields as strings
        id_val = draw(id_strategy)
        amount_val = draw(amount_strategy)
        name_val = draw(name_strategy)
        status_val = draw(status_strategy)
        tags_val = draw(tags_strategy)
        # child is either null or a record with child=null (no deeper)
        child_null = st.just("null")
        # child record with child=null
        def child_record():
            id_c = draw(id_strategy)
            amount_c = draw(amount_strategy)
            name_c = draw(name_strategy)
            status_c = draw(status_strategy)
            tags_c = draw(tags_strategy)
            child_c = "null"
            return (
                '{'
                + '"id":' + id_c + ','
                + '"amount":' + amount_c + ','
                + '"name":' + name_c + ','
                + '"status":' + status_c + ','
                + '"tags":' + tags_c + ','
                + '"child":' + child_c
                + '}'
            )
        child_val = draw(st.one_of(child_null, st.deferred(child_record)))
        record_json = (
            '{'
            + '"id":' + id_val + ','
            + '"amount":' + amount_val + ','
            + '"name":' + name_val + ','
            + '"status":' + status_val + ','
            + '"tags":' + tags_val + ','
            + '"child":' + child_val
            + '}'
        )
        return record_json

    # Draw the top-level record JSON string
    json_text = draw(record_strategy())

    # Return as bytes (UTF-8)
    return json_text.encode("utf-8")