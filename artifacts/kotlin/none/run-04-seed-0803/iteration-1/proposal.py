from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with quotes escaped
    def json_string(s: str) -> str:
        # Escape backslash and double quotes minimally
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return '"' + s + '"'

    # Strategy for id: mostly integer, but sometimes a stringified int or float to cause divergence
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=10**9).map(str),
        st.text(min_size=1, max_size=10).filter(lambda x: x.isdigit()).map(lambda x: json_string(x)),  # string digits
        st.floats(min_value=0, max_value=1e9, allow_infinity=False, allow_nan=False).map(lambda f: str(f))  # float as number
    )

    # Strategy for amount: string, sometimes numeric string, sometimes with weird chars
    amount_strategy = st.one_of(
        st.text(min_size=1, max_size=10).map(json_string),
        st.integers(min_value=0, max_value=10**6).map(str),  # number instead of string
        st.just('null'),  # null instead of string
    )

    # Strategy for name: string or null, sometimes number or boolean to cause divergence
    name_strategy = st.one_of(
        st.none().map(lambda _: 'null'),
        st.text(min_size=0, max_size=10).map(json_string),
        st.integers(min_value=0, max_value=100).map(str),  # number instead of string or null
        st.sampled_from(['true', 'false']),  # boolean instead of string or null
    )

    # Strategy for status: one of the three strings, sometimes null or wrong string
    status_strategy = st.one_of(
        st.sampled_from(statuses),
        st.text(min_size=1, max_size=10).filter(lambda x: x not in ['active', 'inactive', 'unknown']).map(json_string),
        st.just('null'),
        st.integers(min_value=0, max_value=2).map(str),  # number instead of string
    )

    # Strategy for tags: array of strings, sometimes null, sometimes array with non-string elements
    tags_strategy = st.one_of(
        st.lists(st.text(min_size=0, max_size=10).map(json_string), min_size=0, max_size=5).map(
            lambda lst: '[' + ','.join(lst) + ']'),
        st.just('null'),
        st.lists(st.one_of(
            st.text(min_size=0, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=100).map(str),
            st.just('null'),
            st.sampled_from(['true', 'false'])
        ), min_size=0, max_size=5).map(lambda lst: '[' + ','.join(lst) + ']'),
        st.text(min_size=1, max_size=10).map(json_string),  # string instead of array
    )

    # Recursive strategy for child: either null or a nested record (one level only)
    # To avoid deep recursion, child can only be null or a record with child=null
    @st.composite
    def child_strategy(draw):
        # 50% null, 50% nested record with child=null
        if draw(st.booleans()):
            return 'null'
        else:
            # Nested record with child=null
            nested_id = draw(id_strategy)
            nested_amount = draw(amount_strategy)
            nested_name = draw(name_strategy)
            nested_status = draw(status_strategy)
            nested_tags = draw(tags_strategy)
            # child is null here to limit recursion depth
            nested_child = 'null'
            nested_obj = (
                '{'
                f'"id":{nested_id},'
                f'"amount":{nested_amount},'
                f'"name":{nested_name},'
                f'"status":{nested_status},'
                f'"tags":{nested_tags},'
                f'"child":{nested_child}'
                '}'
            )
            return nested_obj

    # Compose top-level record
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_strategy)
    status_val = draw(status_strategy)
    tags_val = draw(tags_strategy)
    child_val = draw(child_strategy())

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

    return json_obj.encode('utf-8')