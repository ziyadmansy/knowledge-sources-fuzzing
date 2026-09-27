from hypothesis import strategies as st

# Helper to produce JSON string literals with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    # Also escape control characters minimally (newline, tab)
    s = s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return f'"{s}"'

# Compose a JSON array of strings from a list of strings
def json_string_array(lst) -> str:
    return '[' + ','.join(json_string_literal(s) for s in lst) + ']'

# Compose a JSON enum string for "status"
def json_status_literal(s: str) -> str:
    # s is one of "active", "inactive", "unknown"
    return json_string_literal(s)

@st.composite
def generated_json(draw) -> bytes:
    # To maximize divergence, produce mostly valid documents with one or two fields subtly off:
    # - id: normally integer, but sometimes stringified integer or float or null (should reject)
    # - amount: normally string, but sometimes number or null (should reject)
    # - name: string or null, but sometimes number or boolean (should reject)
    # - status: enum string, but sometimes invalid string or null (should reject)
    # - tags: array of strings, but sometimes array with non-string elements, or empty array, or null (should reject)
    # - child: either null or a nested record (one level only), but sometimes malformed or missing fields
    
    # Strategy for id field: mostly integer, sometimes stringified integer, sometimes float, sometimes null
    id_val = draw(
        st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            st.integers(min_value=0, max_value=2**31-1),
            st.floats(allow_infinity=False, allow_nan=False).map(lambda f: f"{f:.6g}"),
            st.just("null"),
        )
    )
    # id_val is either int, str (stringified int or float), or "null" string (to be inserted raw)
    
    # Strategy for amount: mostly string, sometimes number, sometimes null literal
    amount_val = draw(
        st.one_of(
            st.text(min_size=1, max_size=20).map(json_string_literal),
            st.floats(allow_infinity=False, allow_nan=False).map(lambda f: f"{f:.6g}"),
            st.integers(min_value=-1000000, max_value=1000000).map(str),
            st.just("null"),
        )
    )
    
    # Strategy for name: string or null, sometimes number or boolean
    name_val = draw(
        st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=20).map(json_string_literal),
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
        )
    )
    
    # status: mostly valid enum strings, sometimes invalid string or null
    status_val = draw(
        st.one_of(
            st.sampled_from(["active", "inactive", "unknown"]).map(json_string_literal),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in {"active","inactive","unknown"}).map(json_string_literal),
            st.just("null"),
        )
    )
    
    # tags: mostly array of strings, sometimes array with non-string elements, sometimes empty array, sometimes null
    # Build array elements first
    tag_elem = draw(
        st.one_of(
            st.text(min_size=1, max_size=10).map(json_string_literal),
            st.integers(min_value=-10, max_value=10).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
            st.just("null"),
        )
    )
    # Generate array length 0 to 5
    tags_len = draw(st.integers(min_value=0, max_value=5))
    tags_list = []
    for _ in range(tags_len):
        tags_list.append(draw(
            st.one_of(
                st.text(min_size=1, max_size=10).map(lambda s: s),
                st.integers(min_value=-10, max_value=10).map(str),
                st.booleans().map(lambda b: "true" if b else "false"),
                st.just("null"),
            )
        ))
    # Compose tags array string, but some elements may be non-string literals
    # So we must produce a JSON array string with mixed element types
    def json_tag_elem(e):
        # e is either string (to be quoted) or a literal string like "true", "null", or a number string
        # We guess if e is a valid JSON string literal or not by checking if it starts and ends with quotes
        # But here e is raw string, so we must quote if it is not a valid literal
        # To simplify, if e is from text, quote it; else leave as is
        try:
            # If e is a valid JSON literal (true, false, null, number), leave as is
            if e in {"true", "false", "null"}:
                return e
            float(e)  # if convertible to float, leave as is
            return e
        except Exception:
            # else quote it
            return json_string_literal(e)
    tags_json = '[' + ','.join(json_tag_elem(e) for e in tags_list) + ']'
    # Sometimes tags is null
    tags_val = draw(st.one_of(st.just(tags_json), st.just("null")))
    
    # child: either null or a nested record with same schema but no further recursion
    # To keep bounded recursion, child is either null or a record with all fields present but with simpler values
    def gen_child():
        # child fields: id int, amount string, name string or null, status enum, tags array of strings, child null
        cid = draw(st.integers(min_value=0, max_value=1000))
        camount = draw(st.text(min_size=1, max_size=10).map(json_string_literal))
        cname = draw(st.one_of(st.none().map(lambda _: "null"), st.text(min_size=0, max_size=10).map(json_string_literal)))
        cstatus = draw(st.sampled_from(["active", "inactive", "unknown"]).map(json_string_literal))
        ctags_list = draw(st.lists(st.text(min_size=1, max_size=10), max_size=3))
        ctags = json_string_array(ctags_list)
        cchild = "null"
        child_obj = (
            '{'
            f'"id":{cid},'
            f'"amount":{camount},'
            f'"name":{cname},'
            f'"status":{cstatus},'
            f'"tags":{ctags},'
            f'"child":{cchild}'
            '}'
        )
        return child_obj
    
    child_val = draw(st.one_of(st.just("null"), st.deferred(gen_child)))
    
    # Compose the final JSON object string with all fields
    # id: if id_val is int, output as number; if string, output as string literal; if "null" output null literal
    if isinstance(id_val, int):
        id_json = str(id_val)
    elif isinstance(id_val, str):
        if id_val == "null":
            id_json = "null"
        else:
            # Try to detect if id_val is a number string or float string
            try:
                float(id_val)
                # output as number literal
                id_json = id_val
            except Exception:
                # output as string literal
                id_json = json_string_literal(id_val)
    else:
        # fallback
        id_json = "null"
    
    # amount_val is already a JSON literal string (quoted string or number or null)
    amount_json = amount_val
    
    # name_val is already a JSON literal string or literal (true/false/null/number)
    name_json = name_val
    
    # status_val is JSON string literal or null
    status_json = status_val
    
    # tags_val is JSON array string or null
    tags_json_final = tags_val
    
    # child_val is JSON object string or null
    child_json = child_val
    
    json_obj = (
        '{'
        f'"id":{id_json},'
        f'"amount":{amount_json},'
        f'"name":{name_json},'
        f'"status":{status_json},'
        f'"tags":{tags_json_final},'
        f'"child":{child_json}'
        '}'
    )
    
    return json_obj.encode("utf-8")