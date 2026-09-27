from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for " and \ to keep JSON valid
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id: integer (always present)
    id_val = draw(st.integers(min_value=-(2**31), max_value=2**31-1))

    # amount: string (always present)
    # Strategy: mostly normal decimal strings, sometimes edge cases like empty, zero, negative-looking, or numeric strings with spaces
    amount_str = draw(st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in '.-+eE ' for c in s)),
        st.just("0"),
        st.just(""),
        st.just(" 123 "),
        st.just("-0.0"),
        st.just("+1.23e4"),
        st.just("NaN"),  # Not a number string, but still a string
        st.just("Infinity"),
        st.just("-Infinity"),
    ))

    # name: string or null (always present)
    # Strategy: sometimes null, sometimes string including empty string, unicode, or strings with escape chars
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20).map(lambda s: s),
    ))

    # status: one of "active", "inactive", "unknown" (always present)
    # Strategy: mostly valid enum strings, sometimes invalid strings or wrong types (to cause divergence)
    # But to keep JSON valid, we must produce a string literal or a non-string literal (e.g. number) to test type divergence
    status_val = draw(st.one_of(
        st.sampled_from(STATUS_VALUES),
        # invalid enum string but still string type
        st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string),
        # sometimes a number literal (not string) to test type divergence
        st.integers(min_value=0, max_value=10).map(str),
        # sometimes null literal (not string)
        st.just("null"),
    ))

    # tags: array of strings (always present)
    # Strategy: mostly arrays of strings, sometimes empty array, sometimes array with null or numbers (wrong types)
    def tags_array():
        # Elements: mostly strings, sometimes null or numbers (to cause divergence)
        elem = draw(st.one_of(
            st.text(min_size=0, max_size=10).map(json_string),
            st.just("null"),
            st.integers(min_value=0, max_value=100).map(str),
        ))
        # Array length 0 to 5
        length = draw(st.integers(min_value=0, max_value=5))
        elems = []
        for _ in range(length):
            elems.append(draw(st.one_of(
                st.text(min_size=0, max_size=10).map(json_string),
                st.just("null"),
                st.integers(min_value=0, max_value=100).map(str),
            )))
        return "[" + ",".join(elems) + "]"

    tags_val = tags_array()

    # child: Record or null (one level recursion)
    # To keep bounded recursion, child is either null or a record with no child (child=null)
    # We vary one or two fields in child to cause divergence
    def child_record():
        # 50% null
        if draw(st.booleans()):
            return "null"
        else:
            # child record with no further child (child=null)
            # id: integer
            cid = draw(st.integers(min_value=-(2**31), max_value=2**31-1))
            # amount: string (simple decimal string)
            camount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in '.-+' for c in s)))
            camount_json = json_string(camount)
            # name: string or null
            cname = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            cname_json = "null" if cname is None else json_string(cname)
            # status: valid enum string only here to reduce complexity in child
            cstatus = draw(st.sampled_from(STATUS_VALUES))
            # tags: array of strings (empty or small)
            ctags_len = draw(st.integers(min_value=0, max_value=3))
            ctags_elems = []
            for _ in range(ctags_len):
                ctags_elems.append(json_string(draw(st.text(min_size=0, max_size=10))))
            ctags_json = "[" + ",".join(ctags_elems) + "]"
            # child: null always here
            return (
                "{" +
                f'"id":{cid},' +
                f'"amount":{camount_json},' +
                f'"name":{cname_json},' +
                f'"status":{cstatus},' +
                f'"tags":{ctags_json},' +
                f'"child":null' +
                "}"
            )

    child_val = child_record()

    # Compose the top-level JSON object as string
    # id: integer literal
    # amount: string literal (quoted)
    # name: string literal or null
    # status: string literal or other literal (int or null)
    # tags: array literal
    # child: object literal or null

    amount_json = json_string(amount_str)
    name_json = "null" if name_val is None else json_string(name_val)

    json_text = (
        "{" +
        f'"id":{id_val},' +
        f'"amount":{amount_json},' +
        f'"name":{name_json},' +
        f'"status":{status_val},' +
        f'"tags":{tags_val},' +
        f'"child":{child_val}' +
        "}"
    )

    return json_text.encode("utf-8")