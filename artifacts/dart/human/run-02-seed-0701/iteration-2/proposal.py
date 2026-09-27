from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    status_values = ["active", "inactive", "unknown"]

    # Strategy for id field:
    # To exploit the known difference in id decoding:
    # manual and built_value require a true int (no double),
    # json_serializable and freezed accept double and call toInt().
    # jsonDecode turns integer literals outside 64-bit range into double.
    # So generate either:
    # - a normal int in 64-bit range (accepted by all)
    # - an integer outside 64-bit range encoded as a JSON number literal,
    #   which jsonDecode will parse as double, causing divergence.
    # We'll generate either:
    # - int in [-2**63, 2**63-1]
    # - int outside that range (e.g. 2**63 or -2**63-1)
    # We'll encode the number as a JSON number literal string later.
    in_range_int = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
    out_of_range_int = draw(st.sampled_from([2**63, -(2**63) - 1]))
    id_choice = draw(st.booleans())
    id_value = out_of_range_int if id_choice else in_range_int

    # Encode id_value as JSON number literal (no quotes)
    # Because jsonDecode will parse large int literals as double.
    id_json = str(id_value)

    # amount: string, always present, non-null
    # Generate a simple string, no surprises here.
    amount_str = draw(st.text(min_size=1, max_size=10))
    # JSON encode string with quotes and escape backslash and quotes minimally
    def json_string(s):
        # minimal escaping for " and \ and control chars
        # Hypothesis strings can contain anything, but we keep it simple:
        # replace \ with \\, " with \"
        # replace control chars with \u00XX
        res = []
        for c in s:
            o = ord(c)
            if c == '\\':
                res.append('\\\\')
            elif c == '"':
                res.append('\\"')
            elif o < 0x20:
                res.append('\\u%04x' % o)
            else:
                res.append(c)
        return '"' + ''.join(res) + '"'
    amount_json = json_string(amount_str)

    # name: nullable string, optional presence is accepted by all
    # We always include it (always present), but sometimes null, sometimes string
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        name_str = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        # If None, encode as null, else encode string
        if name_str is None:
            name_json = "null"
        else:
            name_json = json_string(name_str)

    # status: one of "active", "inactive", "unknown"
    # Always present, always valid string from the set
    status_json = json_string(draw(st.sampled_from(status_values)))

    # tags: array of strings
    # Known divergence: missing tags accepted only by built_value,
    # but we always include tags to avoid trivial rejection.
    # Generate array of strings, possibly empty.
    tags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=3))
    tags_json_items = [json_string(t) for t in tags_list]
    tags_json = "[" + ",".join(tags_json_items) + "]"

    # child: nullable Record or null
    # One level of recursion only, so child.child is always null.
    # We generate either null or a nested record with child=null.
    # To keep it simple, child record fields are always well-formed.
    # We can reuse the same strategies but with smaller size.
    # To avoid infinite recursion, child.child is always null.

    # Helper to generate a child record JSON string (no bytes, string only)
    def gen_child_record():
        # id: int in range (to avoid complexity in child)
        cid = draw(st.integers(min_value=0, max_value=1000))
        cid_json = str(cid)
        camount = draw(st.text(min_size=1, max_size=5))
        camount_json = json_string(camount)
        cname_is_null = draw(st.booleans())
        if cname_is_null:
            cname_json = "null"
        else:
            cname_json = json_string(draw(st.text(min_size=0, max_size=5)))
        cstatus_json = json_string(draw(st.sampled_from(status_values)))
        ctags_list = draw(st.lists(st.text(min_size=0, max_size=5), max_size=2))
        ctags_json_items = [json_string(t) for t in ctags_list]
        ctags_json = "[" + ",".join(ctags_json_items) + "]"
        # child is null at this level
        cchild_json = "null"
        # Compose child record JSON object string
        return (
            '{'
            + '"id":' + cid_json + ','
            + '"amount":' + camount_json + ','
            + '"name":' + cname_json + ','
            + '"status":' + cstatus_json + ','
            + '"tags":' + ctags_json + ','
            + '"child":' + cchild_json
            + '}'
        )

    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json = "null"
    else:
        child_json = gen_child_record()

    # Compose the full JSON object string
    # All six fields always present
    json_obj = (
        '{'
        + '"id":' + id_json + ','
        + '"amount":' + amount_json + ','
        + '"name":' + name_json + ','
        + '"status":' + status_json + ','
        + '"tags":' + tags_json + ','
        + '"child":' + child_json
        + '}'
    )

    # Return bytes as required
    return json_obj.encode("utf-8")