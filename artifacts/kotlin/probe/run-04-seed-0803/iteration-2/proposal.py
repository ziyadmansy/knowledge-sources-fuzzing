from hypothesis import strategies as st

# Helper to produce JSON string literals with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # Escape backslash and double quotes for JSON string
    escaped = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + escaped + '"'

@st.composite
def generated_json(draw) -> bytes:
    # We implement bounded recursion with max depth 1 for "child"
    # We produce JSON text as string, then encode to bytes at the end.

    # Constants for enum values and unknown enum values
    valid_statuses = ['"active"', '"inactive"', '"unknown"']
    unknown_statuses = ['"pending"', '"deleted"', '"null"', 'null', '123', 'true', '{}', '[]']

    # Strategy for "id": integer or string integer (to trigger coercion)
    id_int = st.integers(min_value=0, max_value=2**31-1)
    id_as_int_or_str = st.one_of(
        id_int.map(str),  # as JSON number
        id_int.map(lambda i: json_string_literal(str(i)))  # as JSON string
    )

    # Strategy for "amount": string normally, but sometimes numeric (to trigger known divergence)
    # Also sometimes null or missing is invalid, so always present.
    # We produce either:
    # - JSON string (normal)
    # - JSON number (to trigger kotlinx.serialization rejection)
    amount_str = st.text(min_size=0, max_size=10).map(json_string_literal)
    amount_num = st.floats(allow_infinity=False, allow_nan=False, width=32).map(lambda f: str(f) if f % 1 else str(int(f)))
    amount_field = st.one_of(amount_str, amount_num)

    # Strategy for "name": string or null
    name_str = st.one_of(st.none(), st.text(min_size=0, max_size=10)).map(
        lambda v: 'null' if v is None else json_string_literal(v)
    )

    # Strategy for "status": mostly valid enum, sometimes unknown enum, sometimes null
    # To maximize divergence, we sometimes produce unknown enum values or null
    status_field = st.one_of(
        st.sampled_from(valid_statuses),
        st.sampled_from(unknown_statuses)
    )

    # Strategy for "tags": array of strings, but sometimes with integer elements (to trigger coercion differences)
    # Also sometimes wrong type (string instead of array) to cause rejection by all (no score)
    # We want mostly arrays with mixed string/int elements to trigger divergence.
    tag_str = st.text(min_size=0, max_size=5)
    tag_int = st.integers(min_value=0, max_value=100)
    # Elements: string or int (to trigger coercion differences)
    tag_element = st.one_of(
        tag_str.map(json_string_literal),
        tag_int.map(str)
    )
    tags_array = st.lists(tag_element, min_size=0, max_size=5).map(
        lambda elems: '[' + ','.join(elems) + ']'
    )
    # Occasionally produce wrong type (string) to cause rejection by all (no score), so avoid that mostly
    tags_field = tags_array

    # Strategy for "child": null or a nested record (one level only)
    # For child present, produce a record with all fields present and well-formed except:
    # - sometimes child is empty object {} (Gson accepts, others reject)
    # - sometimes child is null
    # - sometimes child is missing (not allowed, always present)
    # To maximize divergence, sometimes produce empty object for child.
    # We limit recursion depth to 1.

    # Define a helper to produce a record JSON string (without child recursion)
    def record_json(draw, allow_empty_object=False):
        # id
        id_val = draw(id_as_int_or_str)
        # amount
        amount_val = draw(amount_field)
        # name
        name_val = draw(name_str)
        # status
        status_val = draw(status_field)
        # tags
        tags_val = draw(tags_field)
        # child: for nested record, no further nesting (child null or empty object or full record with child=null)
        # To avoid infinite recursion, child is either null or empty object or null child record
        child_choice = draw(st.sampled_from(['null', 'empty_object', 'full_null_child']))
        if allow_empty_object and child_choice == 'empty_object':
            child_val = '{}'
        elif child_choice == 'null':
            child_val = 'null'
        else:
            # full child record with child=null to avoid deeper recursion
            # Compose child record with child=null
            child_id = draw(id_as_int_or_str)
            child_amount = draw(amount_field)
            child_name = draw(name_str)
            child_status = draw(status_field)
            child_tags = draw(tags_field)
            child_val = (
                '{'
                f'"id":{child_id},'
                f'"amount":{child_amount},'
                f'"name":{child_name},'
                f'"status":{child_status},'
                f'"tags":{child_tags},'
                f'"child":null'
                '}'
            )
        return (
            '{'
            f'"id":{id_val},'
            f'"amount":{amount_val},'
            f'"name":{name_val},'
            f'"status":{status_val},'
            f'"tags":{tags_val},'
            f'"child":{child_val}'
            '}'
        )

    # Compose the top-level record, sometimes with child empty object to trigger divergence
    # We bias to produce child empty object sometimes to trigger known divergence (Gson accepts, others reject)
    # Also bias to produce unknown enum values or null enum values sometimes to trigger divergence
    # Also bias to produce amount as number sometimes to trigger divergence

    # We draw the top-level record JSON string here
    json_text = draw(record_json(allow_empty_object=True))

    # Return as bytes
    return json_text.encode('utf-8')