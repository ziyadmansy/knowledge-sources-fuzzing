from hypothesis import strategies as st

# Helper to produce JSON string literals with proper escaping of " and \ only (minimal)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote for JSON string
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    statuses = ['"active"', '"inactive"', '"unknown"']
    # For "status" field, also sometimes produce unknown enum or null to trigger divergence
    # But only one or two fields off at a time, so mostly valid

    # Recursive limit: one level of child only
    # We'll produce a record as JSON text (string), then encode to bytes at the end

    # Strategy for "id": int or stringified int, or sometimes wrong type (float, bool, null)
    # But mostly valid or near-valid
    def id_strategy():
        # 80% int or string int, 20% wrong type (float, bool, null)
        base = st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            st.integers(min_value=0, max_value=2**31-1).map(lambda i: json_string_literal(str(i))),
        )
        wrong = st.one_of(
            st.floats(allow_infinity=False, allow_nan=False).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
            st.just("null"),
        )
        return st.one_of(base, wrong)

    # Strategy for "amount": string (usually numeric string), or number, or sometimes wrong type (bool, null)
    def amount_strategy():
        # 70% string numeric, 20% number, 10% wrong type
        str_num = st.integers(min_value=0, max_value=10**9).map(lambda i: json_string_literal(str(i)))
        num = st.integers(min_value=0, max_value=10**9).map(str)
        wrong = st.one_of(
            st.booleans().map(lambda b: "true" if b else "false"),
            st.just("null"),
            st.floats(allow_infinity=False, allow_nan=False).map(str),
        )
        return st.one_of(str_num, num, wrong)

    # Strategy for "name": string or null, sometimes number or bool to cause divergence
    def name_strategy():
        base = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=20).map(json_string_literal),
        )
        wrong = st.one_of(
            st.integers().map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
        )
        return st.one_of(base, wrong)

    # Strategy for "status": valid enum string, unknown enum string, null, or wrong type
    def status_strategy():
        valid = st.sampled_from(statuses)
        unknown_enum = st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string_literal)
        null = st.just("null")
        wrong = st.one_of(
            st.integers().map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
            st.just("[]"),
            st.just("{}"),
        )
        # Mostly valid, sometimes unknown enum or null or wrong
        return st.one_of(
            valid,
            unknown_enum,
            null,
            wrong,
        )

    # Strategy for "tags": array of strings normally, but sometimes with nulls or non-string elements or null array
    def tags_strategy():
        # Elements: mostly strings, sometimes numbers, bools, nulls
        str_elem = st.text(min_size=0, max_size=10).map(json_string_literal)
        num_elem = st.integers(min_value=0, max_value=100).map(str)
        bool_elem = st.booleans().map(lambda b: "true" if b else "false")
        null_elem = st.just("null")
        elem = st.one_of(str_elem, num_elem, bool_elem, null_elem)

        # Array or null (null array triggers divergence)
        # Array length 0 to 5
        arr = st.lists(elem, min_size=0, max_size=5).map(lambda elems: "[" + ",".join(elems) + "]")
        return st.one_of(arr, st.just("null"))

    # Strategy for "child": null or a record (one level recursion)
    # To avoid deep recursion, child record will never have a child itself (child=null)
    @st.composite
    def child_strategy(draw):
        # 70% null, 30% record with child=null
        is_null = draw(st.booleans())
        if is_null:
            return "null"
        else:
            # Compose child record with child=null
            id_val = draw(id_strategy())
            amount_val = draw(amount_strategy())
            name_val = draw(name_strategy())
            status_val = draw(status_strategy())
            tags_val = draw(tags_strategy())
            # child=null
            child_val = "null"
            fields = [
                '"id":' + id_val,
                '"amount":' + amount_val,
                '"name":' + name_val,
                '"status":' + status_val,
                '"tags":' + tags_val,
                '"child":' + child_val,
            ]
            return "{" + ",".join(fields) + "}"

    # Compose top-level record
    id_val = draw(id_strategy())
    amount_val = draw(amount_strategy())
    name_val = draw(name_strategy())
    status_val = draw(status_strategy())
    tags_val = draw(tags_strategy())
    child_val = draw(child_strategy())

    fields = [
        '"id":' + id_val,
        '"amount":' + amount_val,
        '"name":' + name_val,
        '"status":' + status_val,
        '"tags":' + tags_val,
        '"child":' + child_val,
    ]
    json_text = "{" + ",".join(fields) + "}"
    return json_text.encode("utf-8")