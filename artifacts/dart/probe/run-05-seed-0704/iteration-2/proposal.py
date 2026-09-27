from hypothesis import strategies as st

# Constants for allowed values
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper: produce a JSON string literal from a Hypothesis string,
# escaping backslash and double quote minimally for valid JSON strings.
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    # Also escape control chars for safety (e.g. newline)
    s = s.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return f'"{s}"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.
    """

    # --- Primitive fields generators ---

    # id: integer normally, but sometimes string (known to cause uniform rejection)
    # We avoid id as string to not cause uniform rejection.
    # Instead, id as int, but near boundary values or as int but in string form (to test).
    # But string id is known to cause uniform rejection, so avoid that.
    # So id always int, but vary values near boundaries.
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))

    # amount: normally string, but sometimes int (known uniform rejection)
    # So amount always string, but sometimes empty string or numeric string.
    amount_str = draw(st.one_of(
        st.text(min_size=0, max_size=10).map(json_string_literal),
        # numeric strings to test subtle differences
        st.integers(min_value=0, max_value=999999).map(lambda i: f'"{i}"'),
    ))

    # name: string or null
    # To provoke divergence, sometimes null, sometimes string, sometimes empty string
    # Avoid non-string non-null (known uniform rejection)
    name_val = draw(st.one_of(
        st.just("null"),
        st.text(min_size=0, max_size=20).map(json_string_literal),
    ))

    # status: one of allowed strings, but sometimes with whitespace or case variation
    # Known uniform rejection if not exact string, so keep exact but vary which allowed string
    status_val = draw(st.sampled_from(STATUS_VALUES))

    # tags: array of strings
    # To provoke divergence, sometimes empty array, sometimes array with empty string,
    # sometimes array with multiple strings, sometimes array with duplicates
    # Avoid non-string elements (uniform rejection)
    tags_len = draw(st.integers(min_value=0, max_value=3))
    tags_elems = []
    for _ in range(tags_len):
        # strings with possible empty or normal strings
        s = draw(st.text(min_size=0, max_size=10).map(json_string_literal))
        tags_elems.append(s)
    tags_val = "[" + ",".join(tags_elems) + "]"

    # child: null or a nested Record (one level deep normally)
    # To provoke divergence, sometimes null, sometimes valid nested record,
    # sometimes nested record with one field subtly off (e.g. missing field or extra field)
    # But missing fields cause uniform rejection, so avoid missing fields.
    # Extra unknown fields are accepted by all, so no divergence there.
    # Instead, vary one field subtly in child to provoke divergence.

    # Define a helper to generate a child record JSON string (one level deep, no recursion)
    def gen_child_record():
        # id int near boundary
        cid = draw(st.integers(min_value=0, max_value=2**31-1))
        # amount string numeric or empty
        camount = draw(st.one_of(
            st.text(min_size=0, max_size=10).map(json_string_literal),
            st.integers(min_value=0, max_value=999999).map(lambda i: f'"{i}"'),
        ))
        # name string or null
        cname = draw(st.one_of(
            st.just("null"),
            st.text(min_size=0, max_size=20).map(json_string_literal),
        ))
        # status one of allowed strings
        cstatus = draw(st.sampled_from(STATUS_VALUES))
        # tags array of strings, length 0 to 2
        clen = draw(st.integers(min_value=0, max_value=2))
        celems = []
        for _ in range(clen):
            s = draw(st.text(min_size=0, max_size=10).map(json_string_literal))
            celems.append(s)
        ctags = "[" + ",".join(celems) + "]"
        # child field: always null (to avoid deeper recursion)
        cchild = "null"

        # Compose child record JSON object string
        # Possibly add an extra unknown field sometimes (known accepted by all)
        extra_field = draw(st.booleans())
        extra_field_str = ',"extra_field":123' if extra_field else ''

        return (
            '{'
            f'"id":{cid},'
            f'"amount":{camount},'
            f'"name":{cname},'
            f'"status":{cstatus},'
            f'"tags":{ctags},'
            f'"child":{cchild}'
            f'{extra_field_str}'
            '}'
        )

    # Decide if child is null or a nested record
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_val = "null"
    else:
        child_val = gen_child_record()

    # Compose top-level JSON object string
    # Possibly add an extra unknown field sometimes (known accepted by all)
    extra_top_field = draw(st.booleans())
    extra_top_field_str = ',"extra_top":true' if extra_top_field else ''

    json_obj = (
        '{'
        f'"id":{id_val},'
        f'"amount":{amount_str},'
        f'"name":{name_val},'
        f'"status":{status_val},'
        f'"tags":{tags_val},'
        f'"child":{child_val}'
        f'{extra_top_field_str}'
        '}'
    )

    # Return bytes
    return json_obj.encode("utf-8")