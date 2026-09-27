from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with quotes escaped
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally for JSON string
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Strategy for "amount" field: normally a string representing a decimal number,
    # but to induce divergence, sometimes produce a number literal (no quotes),
    # or a string with unusual content.
    amount_str = st.one_of(
        # Normal decimal string
        st.decimals(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False)
          .map(lambda d: json_string(format(d, 'f').rstrip('0').rstrip('.') if '.' in format(d, 'f') else format(d, 'f'))),
        # Number literal (no quotes) - invalid per schema but may be accepted by some libs
        st.decimals(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False)
          .map(lambda d: format(d, 'f').rstrip('0').rstrip('.') if '.' in format(d, 'f') else format(d, 'f')),
        # String with non-numeric content
        st.text(min_size=1, max_size=5).map(json_string),
        # Empty string
        st.just('""'),
    )

    # Strategy for "name": string or null, but also try number or boolean literals to induce divergence
    name_str = st.one_of(
        st.none().map(lambda _: 'null'),
        st.text(min_size=0, max_size=10).map(json_string),
        st.integers(min_value=-1000, max_value=1000).map(str),  # number literal
        st.booleans().map(lambda b: 'true' if b else 'false'),  # boolean literal
    )

    # Strategy for "status": one of the three strings, or a wrong string, or null, or number literal
    status_str = st.one_of(
        st.sampled_from(statuses),
        st.text(min_size=1, max_size=10).filter(lambda s: f'"{s}"' not in statuses).map(json_string),
        st.none().map(lambda _: 'null'),
        st.integers(min_value=0, max_value=10).map(str),
    )

    # Strategy for "tags": array of strings, or null, or array with non-string elements, or number literal
    tags_str = st.one_of(
        # Normal array of strings
        st.lists(st.text(min_size=0, max_size=5).map(json_string), min_size=0, max_size=5)
          .map(lambda lst: '[' + ','.join(lst) + ']'),
        # Null
        st.none().map(lambda _: 'null'),
        # Array with mixed types (string and number literals)
        st.lists(st.one_of(
            st.text(min_size=0, max_size=5).map(json_string),
            st.integers(min_value=0, max_value=100).map(str),
            st.booleans().map(lambda b: 'true' if b else 'false'),
            st.none().map(lambda _: 'null'),
        ), min_size=1, max_size=5).map(lambda lst: '[' + ','.join(lst) + ']'),
        # Number literal (invalid)
        st.integers(min_value=0, max_value=100).map(str),
    )

    # Recursive strategy for "child": either null or a nested record (one level only)
    # To avoid deep recursion, child.child is always null
    @st.composite
    def child_record(draw):
        # id: integer
        cid = draw(st.integers(min_value=0, max_value=10000))
        # amount: reuse amount_str
        camount = draw(amount_str)
        # name: reuse name_str
        cname = draw(name_str)
        # status: reuse status_str
        cstatus = draw(status_str)
        # tags: reuse tags_str
        ctags = draw(tags_str)
        # child: always null here to limit recursion
        cchild = 'null'

        rec = (
            '{'
            f'"id":{cid},'
            f'"amount":{camount},'
            f'"name":{cname},'
            f'"status":{cstatus},'
            f'"tags":{ctags},'
            f'"child":{cchild}'
            '}'
        )
        return rec

    # Top-level record fields
    tid = draw(st.integers(min_value=0, max_value=10000))
    tamount = draw(amount_str)
    tname = draw(name_str)
    tstatus = draw(status_str)
    ttags = draw(tags_str)
    # child: either null or a child record
    tchild = draw(st.one_of(
        st.just('null'),
        child_record()
    ))

    # Compose the full JSON document string
    json_text = (
        '{'
        f'"id":{tid},'
        f'"amount":{tamount},'
        f'"name":{tname},'
        f'"status":{tstatus},'
        f'"tags":{ttags},'
        f'"child":{tchild}'
        '}'
    )

    return json_text.encode('utf-8')