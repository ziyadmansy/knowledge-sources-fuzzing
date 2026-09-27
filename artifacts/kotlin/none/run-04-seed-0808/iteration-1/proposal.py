from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Escape backslash and double quote
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Strategy for id: integer, but sometimes as string (to provoke divergence)
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),
        st.text(min_size=1, max_size=5).filter(lambda x: not x.isdigit()).map(json_string),
        # Also try id as a quoted number string (valid JSON string but number inside)
        st.integers(min_value=0, max_value=2**31-1).map(lambda i: json_string(str(i))),
    )

    # Strategy for amount: string, but sometimes a number (to provoke divergence)
    amount_strategy = st.one_of(
        st.text(min_size=0, max_size=10).map(json_string),
        st.integers(min_value=-1000, max_value=1000).map(str),
        st.floats(allow_nan=False, allow_infinity=False).map(lambda f: format(f, '.6g')),
    )

    # Strategy for name: string or null, but sometimes a number or boolean (to provoke divergence)
    name_strategy = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(json_string),
        st.integers(min_value=-1000, max_value=1000).map(str),
        st.booleans().map(lambda b: "true" if b else "false"),
    )

    # Strategy for status: one of three strings, but sometimes null or wrong string
    status_strategy = st.one_of(
        st.sampled_from(statuses),
        st.none().map(lambda _: "null"),
        st.text(min_size=1, max_size=7).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string),
    )

    # Strategy for tags: array of strings, but sometimes null or array with non-string elements
    def tags_strategy():
        # Array of strings normally
        normal = st.lists(st.text(min_size=0, max_size=5).map(json_string), min_size=0, max_size=5).map(
            lambda lst: "[" + ",".join(lst) + "]"
        )
        # Null
        null = st.just("null")
        # Array with mixed types (string, number, boolean)
        mixed = st.lists(
            st.one_of(
                st.text(min_size=0, max_size=5).map(json_string),
                st.integers(min_value=-10, max_value=10).map(str),
                st.booleans().map(lambda b: "true" if b else "false"),
            ),
            min_size=0,
            max_size=5,
        ).map(lambda lst: "[" + ",".join(lst) + "]")
        return st.one_of(normal, null, mixed)

    # Recursive strategy for child: either null or a nested record (one level only)
    # To avoid deep recursion, child can be null or a record with child=null
    @st.composite
    def child_strategy(draw):
        # 50% null, 50% nested record with child=null
        is_null = draw(st.booleans())
        if is_null:
            return "null"
        else:
            # Nested record with child=null
            nested_id = draw(id_strategy)
            nested_amount = draw(amount_strategy)
            nested_name = draw(name_strategy)
            nested_status = draw(status_strategy)
            nested_tags = draw(tags_strategy())
            # child=null
            nested_child = "null"
            nested_fields = (
                '"id":' + nested_id + ","
                + '"amount":' + nested_amount + ","
                + '"name":' + nested_name + ","
                + '"status":' + nested_status + ","
                + '"tags":' + nested_tags + ","
                + '"child":' + nested_child
            )
            return "{" + nested_fields + "}"

    # Compose the top-level record fields
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_strategy)
    status_val = draw(status_strategy)
    tags_val = draw(tags_strategy())
    child_val = draw(child_strategy())

    # Compose JSON text
    json_text = (
        "{"
        + '"id":' + id_val + ","
        + '"amount":' + amount_val + ","
        + '"name":' + name_val + ","
        + '"status":' + status_val + ","
        + '"tags":' + tags_val + ","
        + '"child":' + child_val
        + "}"
    )

    return json_text.encode("utf-8")