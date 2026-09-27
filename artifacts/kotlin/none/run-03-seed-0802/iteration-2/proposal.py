from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Basic JSON string escaper for simple strings (no unicode escapes, minimal)
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars minimally
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        s = s.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return '"' + s + '"'

    # JSON null literal
    null = "null"

    # JSON boolean literals
    true = "true"
    false = "false"

    # Strategy for id: integer, but sometimes as string (to induce divergence)
    id_int = st.integers(min_value=0, max_value=2**31-1)
    id_as_int = id_int.map(str)
    id_as_str = id_int.map(lambda i: json_string(str(i)))
    # 80% chance integer, 20% chance string (wrong type)
    id_field = st.one_of(id_as_int, id_as_str)

    # amount: string, but sometimes number (wrong type)
    # amount is always string in schema, but we try number or string
    amount_str = st.text(min_size=1, max_size=10).map(json_string)
    amount_num = st.integers(min_value=0, max_value=1000000).map(str)
    amount_field = st.one_of(amount_str, amount_num)

    # name: string or null, but sometimes number or boolean (wrong type)
    name_null = st.just(null)
    name_str = st.text(min_size=0, max_size=20).map(json_string)
    name_num = st.integers(min_value=-1000, max_value=1000).map(str)
    name_bool = st.booleans().map(lambda b: true if b else false)
    # 70% correct (string or null), 30% wrong type (number or bool)
    name_field = st.one_of(
        name_null,
        name_str,
        name_num,
        name_bool,
    )

    # status: one of "active", "inactive", "unknown"
    # sometimes wrong string or number or null
    valid_statuses = ["active", "inactive", "unknown"]
    status_valid = st.sampled_from(valid_statuses).map(json_string)
    status_invalid_str = st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_statuses).map(json_string)
    status_num = st.integers(min_value=0, max_value=10).map(str)
    status_null = st.just(null)
    # 80% valid, 20% invalid (string or number or null)
    status_field = st.one_of(
        status_valid,
        status_invalid_str,
        status_num,
        status_null,
    )

    # tags: array of strings, sometimes empty, sometimes with wrong types inside
    tag_str = st.text(min_size=0, max_size=10).map(json_string)
    tag_num = st.integers(min_value=0, max_value=100).map(str)
    tag_bool = st.booleans().map(lambda b: true if b else false)
    tag_null = st.just(null)
    # tags array length 0..3
    # elements mostly strings, sometimes wrong types
    tag_element = st.one_of(tag_str, tag_num, tag_bool, tag_null)
    tags_array = st.lists(tag_element, min_size=0, max_size=3).map(
        lambda elems: "[" + ",".join(elems) + "]"
    )

    # child: either null or a nested record (one level recursion max)
    # To avoid infinite recursion, child record fields are always well-formed (no wrong types)
    # but child can be null or a well-formed record.

    # Well-formed record generator (no wrong types)
    def well_formed_record():
        id_wf = id_int.map(str)
        amount_wf = st.text(min_size=1, max_size=10).map(json_string)
        name_wf = st.one_of(st.just(null), st.text(min_size=0, max_size=20).map(json_string))
        status_wf = st.sampled_from(valid_statuses).map(json_string)
        tags_wf = st.lists(st.text(min_size=0, max_size=10).map(json_string), min_size=0, max_size=3).map(
            lambda elems: "[" + ",".join(elems) + "]"
        )
        # child null only (no recursion deeper)
        child_wf = st.just(null)

        return st.tuples(id_wf, amount_wf, name_wf, status_wf, tags_wf, child_wf).map(
            lambda t: (
                '{'
                + '"id":' + t[0] + ','
                + '"amount":' + t[1] + ','
                + '"name":' + t[2] + ','
                + '"status":' + t[3] + ','
                + '"tags":' + t[4] + ','
                + '"child":' + t[5]
                + '}'
            )
        )

    child_field = st.one_of(st.just(null), well_formed_record())

    # Compose top-level record with mostly possibly wrong types in fields
    record = st.tuples(id_field, amount_field, name_field, status_field, tags_array, child_field).map(
        lambda t: (
            '{'
            + '"id":' + t[0] + ','
            + '"amount":' + t[1] + ','
            + '"name":' + t[2] + ','
            + '"status":' + t[3] + ','
            + '"tags":' + t[4] + ','
            + '"child":' + t[5]
            + '}'
        )
    )

    json_text = draw(record)
    return json_text.encode("utf-8")