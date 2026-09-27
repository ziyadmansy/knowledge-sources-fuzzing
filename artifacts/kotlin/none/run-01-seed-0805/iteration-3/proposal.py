from hypothesis import strategies as st

# Helper to produce JSON string literals with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote for JSON string
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    # Also escape control characters minimally (newline, tab)
    s = s.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return '"' + s + '"'

@st.composite
def generated_json(draw, _depth=0) -> bytes:
    # Limit recursion depth to 1 for "child" field
    # We produce a JSON object string with all six fields always present.
    # We vary one or two fields to be slightly off to maximize divergence.
    # Fields:
    # "id": integer (sometimes as string to cause divergence)
    # "amount": string (sometimes number or null to cause divergence)
    # "name": string or null (sometimes number or missing to cause divergence)
    # "status": one of "active", "inactive", "unknown" (sometimes invalid string or null)
    # "tags": array of strings (sometimes array with non-string, or null)
    # "child": Record or null (one level recursion only)
    
    # Strategy to produce a valid integer or sometimes a string integer or float string or null
    id_int = draw(st.integers(min_value=0, max_value=1_000_000))
    id_variants = st.one_of(
        st.just(str(id_int)),  # id as string (wrong type)
        st.just(str(id_int) + ".0"),  # id as float string (wrong type)
        st.just(id_int),  # id as integer (correct)
        st.just(None),  # id as null (wrong type)
    )
    id_val = draw(id_variants)
    
    # amount: normally string, sometimes number, null, or empty string
    amount_str = draw(st.text(min_size=0, max_size=10))
    amount_variants = st.one_of(
        st.just(json_string_literal(amount_str)),  # correct string
        st.integers(min_value=0, max_value=10000).map(str),  # string of digits (correct)
        st.just(str(draw(st.floats(allow_nan=False, allow_infinity=False)))),  # string float (correct)
        st.integers(min_value=0, max_value=10000),  # number (wrong type)
        st.just("null"),  # null (wrong type)
        st.just('""'),  # empty string (correct)
    )
    amount_val = draw(amount_variants)
    if isinstance(amount_val, int):
        amount_json = str(amount_val)
    elif amount_val == "null":
        amount_json = "null"
    else:
        amount_json = amount_val
    
    # name: string or null normally, sometimes number, boolean, or missing (missing not allowed by schema, but test)
    name_str = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
    # Variants: string literal, null, number, boolean, empty string
    name_variants = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(json_string_literal),
        st.integers(min_value=0, max_value=1000).map(str),
        st.booleans().map(lambda b: "true" if b else "false"),
        st.just('""'),
    )
    name_val = draw(name_variants)
    
    # status: one of "active", "inactive", "unknown" normally
    # Variants: correct string, uppercase, misspelled, null, number
    status_correct = st.sampled_from(["active", "inactive", "unknown"]).map(json_string_literal)
    status_variants = st.one_of(
        status_correct,
        st.sampled_from(["ACTIVE", "Inactive", "unknwn"]).map(json_string_literal),
        st.just("null"),
        st.integers(min_value=0, max_value=2).map(str),
    )
    status_val = draw(status_variants)
    
    # tags: array of strings normally, sometimes array with non-string, empty array, null
    # Build array elements: mostly strings, sometimes numbers or booleans
    tag_string = st.text(min_size=0, max_size=10).map(json_string_literal)
    tag_nonstring = st.one_of(
        st.integers(min_value=0, max_value=1000).map(str),
        st.booleans().map(lambda b: "true" if b else "false"),
        st.just("null"),
    )
    # Mix mostly strings with occasional non-string
    def tags_array():
        # 0 to 5 elements
        length = draw(st.integers(min_value=0, max_value=5))
        elems = []
        for _ in range(length):
            # 80% string, 20% non-string
            if draw(st.booleans().filter(lambda x: x)):  # 50% chance True, but we want 80% string, so bias:
                elem = draw(tag_string)
            else:
                elem = draw(tag_nonstring)
            elems.append(elem)
        return "[" + ",".join(elems) + "]"
    # tags variants: array as above or null
    tags_val = draw(st.one_of(
        st.just(tags_array()),
        st.just("null"),
    ))
    
    # child: null or a nested record (one level only)
    # To avoid infinite recursion, if _depth > 0, child must be null
    if _depth == 0:
        child_val = draw(st.one_of(
            st.just("null"),
            generated_json(_depth=1).map(lambda b: b.decode("utf-8")),
        ))
    else:
        child_val = "null"
    
    # Compose JSON fields with some fields possibly malformed or type variants
    # id field: if id_val is int, output as number, else as string or null literal
    if isinstance(id_val, int):
        id_json = str(id_val)
    elif id_val is None:
        id_json = "null"
    else:
        # id_val is string like "123" or "123.0"
        id_json = json_string_literal(id_val)
    
    # Compose final JSON string
    # We always include all fields, no missing fields (missing fields cause all to reject)
    json_obj = (
        '{'
        f'"id":{id_json},'
        f'"amount":{amount_json},'
        f'"name":{name_val},'
        f'"status":{status_val},'
        f'"tags":{tags_val},'
        f'"child":{child_val}'
        '}'
    )
    
    return json_obj.encode("utf-8")