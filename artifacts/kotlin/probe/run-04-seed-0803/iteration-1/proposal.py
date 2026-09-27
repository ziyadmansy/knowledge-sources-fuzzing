from hypothesis import strategies as st

# Helper to produce JSON string literals with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote for JSON string literal
    escaped = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + escaped + '"'

@st.composite
def generated_json(draw) -> bytes:
    # We implement bounded recursion for "child" field, max depth 1 (root + child)
    # We'll produce a JSON string representing the whole record, as bytes.

    # Constants for enum values and null
    status_values = ['"active"', '"inactive"', '"unknown"']
    # Also add known "null" and unknown enum values for divergence
    # We will sometimes produce unknown enum values or null to trigger divergence

    # Strategy for "id": integer or string integer (to trigger coercion)
    id_int = st.integers(min_value=0, max_value=10**9)
    id_as_int_or_string = st.one_of(
        id_int.map(str),  # as JSON number (no quotes)
        id_int.map(lambda i: json_string_literal(str(i)))  # as JSON string
    )

    # Strategy for "amount": string normally, but sometimes numeric to trigger divergence
    # amount can be string or number (Gson, Moshi, Jackson accept number coercion; kotlinx rejects)
    amount_str = st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s)
    amount_as_string = amount_str.map(json_string_literal)
    amount_as_number = st.integers(min_value=0, max_value=10**9).map(str)
    amount_field = st.one_of(amount_as_string, amount_as_number)

    # Strategy for "name": string or null
    name_str = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string_literal)
    )

    # Strategy for "status": enum string, unknown enum string, or null (to trigger divergence)
    known_status = st.sampled_from(status_values)
    unknown_status = st.sampled_from(['"pending"', '"disabled"', '"foo"'])
    status_field = st.one_of(
        known_status,
        unknown_status,
        st.just("null")
    )

    # Strategy for "tags": array of strings, but sometimes with integers inside (to trigger divergence)
    # Gson, Moshi, Jackson accept integer coercion inside string arrays; kotlinx rejects
    tag_str = st.text(min_size=1, max_size=8).filter(lambda s: '"' not in s and '\\' not in s)
    tag_as_string = tag_str.map(json_string_literal)
    tag_as_int = st.integers(min_value=0, max_value=100).map(str)
    tag_element = st.one_of(tag_as_string, tag_as_int)
    tags_array = st.lists(tag_element, min_size=0, max_size=4).map(
        lambda lst: "[" + ",".join(lst) + "]"
    )

    # Strategy for "child": either null, empty object {}, or a nested record (one level only)
    # Gson accepts empty object for nullable child, others reject
    # Nested record is same schema but no further recursion (depth=1)
    # We'll produce either "null", "{}", or nested record JSON string

    # To avoid infinite recursion, define a helper for child record without child field (child=null only)
    def child_record():
        # child inside child is always null to bound recursion
        # reuse all fields except child is always null here
        return st.tuples(
            id_int.map(str),
            amount_field,
            name_str,
            known_status,
            tags_array,
        ).map(lambda t: (
            '{'
            + '"id":' + t[0] + ','
            + '"amount":' + t[1] + ','
            + '"name":' + t[2] + ','
            + '"status":' + t[3] + ','
            + '"tags":' + t[4] + ','
            + '"child":null'
            + '}'
        ))

    child_field = st.one_of(
        st.just("null"),
        st.just("{}"),
        child_record()
    )

    # Compose the full record JSON string
    record = st.tuples(
        id_as_int_or_string,
        amount_field,
        name_str,
        status_field,
        tags_array,
        child_field
    ).map(lambda t: (
        '{'
        + '"id":' + t[0] + ','
        + '"amount":' + t[1] + ','
        + '"name":' + t[2] + ','
        + '"status":' + t[3] + ','
        + '"tags":' + t[4] + ','
        + '"child":' + t[5]
        + '}'
    ))

    json_text = draw(record)
    return json_text.encode('utf-8')