from hypothesis import strategies as st

# Constants for fixed enum values and tags
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce a JSON string literal with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # Minimal escaping for JSON string: backslash and double quote
    # Hypothesis strings are unicode, but we keep it simple here
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects matching the schema with subtle
    variations designed to provoke divergence among four Dart JSON deserializers.
    """

    # id: integer, but sometimes as string or float to provoke type issues
    id_type = draw(st.sampled_from(['int', 'string_int', 'float_int']))
    if id_type == 'int':
        id_val = draw(st.integers(min_value=0, max_value=2**31-1))
        id_json = str(id_val)
    elif id_type == 'string_int':
        # id as a numeric string (should be rejected or parsed differently)
        id_val = draw(st.integers(min_value=0, max_value=2**31-1))
        id_json = json_string_literal(str(id_val))
    else:
        # id as a float with no fractional part (e.g. 42.0)
        id_val = draw(st.integers(min_value=0, max_value=2**31-1))
        id_json = f"{float(id_val):.1f}"

    # amount: string normally, but sometimes number or null to provoke divergence
    amount_type = draw(st.sampled_from(['string', 'number', 'null']))
    if amount_type == 'string':
        # amount string with digits, possibly with leading zeros or decimal point
        amount_str = draw(st.one_of(
            st.from_regex(r'0|[1-9]\d*', fullmatch=True),
            st.from_regex(r'\d+\.\d+', fullmatch=True),
            st.just('0'),
            st.just('00'),
            st.just('0.0'),
        ))
        amount_json = json_string_literal(amount_str)
    elif amount_type == 'number':
        # amount as a JSON number (int or float)
        amount_num = draw(st.one_of(
            st.integers(min_value=0, max_value=10**6),
            st.floats(min_value=0, max_value=10**6, allow_nan=False, allow_infinity=False)
        ))
        # Format floats to avoid scientific notation
        if isinstance(amount_num, float):
            amount_json = f"{amount_num:.6f}".rstrip('0').rstrip('.')
            if amount_json == '':
                amount_json = '0'
        else:
            amount_json = str(amount_num)
    else:
        # null amount (should be rejected or decoded differently)
        amount_json = "null"

    # name: string or null, but sometimes number or boolean to provoke divergence
    name_type = draw(st.sampled_from(['string', 'null', 'number', 'bool']))
    if name_type == 'string':
        # name string, possibly empty or with unicode
        name_val = draw(st.one_of(
            st.text(min_size=0, max_size=10),
            st.just(""),
            st.just("null"),
            st.just("true"),
            st.just("false"),
            st.just("123"),
        ))
        name_json = json_string_literal(name_val)
    elif name_type == 'null':
        name_json = "null"
    elif name_type == 'number':
        name_num = draw(st.integers(min_value=-1000, max_value=1000))
        name_json = str(name_num)
    else:
        # bool
        name_bool = draw(st.booleans())
        name_json = "true" if name_bool else "false"

    # status: one of the three strings normally, but sometimes null or unknown string
    status_type = draw(st.sampled_from(['valid', 'null', 'invalid_string']))
    if status_type == 'valid':
        status_json = draw(st.sampled_from(STATUS_VALUES))
    elif status_type == 'null':
        status_json = "null"
    else:
        # invalid string not in enum
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active','inactive','unknown']))
        status_json = json_string_literal(invalid_status)

    # tags: array of strings normally, but sometimes null, or array with non-string elements
    tags_type = draw(st.sampled_from(['valid', 'null', 'mixed_types', 'empty']))
    if tags_type == 'valid':
        # array of 0 to 5 strings
        tags_list = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=5))
        tags_json_items = [json_string_literal(t) for t in tags_list]
        tags_json = "[" + ",".join(tags_json_items) + "]"
    elif tags_type == 'null':
        tags_json = "null"
    elif tags_type == 'empty':
        tags_json = "[]"
    else:
        # mixed types: strings and numbers and nulls mixed in array
        mixed_items = []
        length = draw(st.integers(min_value=1, max_value=5))
        for _ in range(length):
            t = draw(st.sampled_from(['string', 'number', 'null']))
            if t == 'string':
                s = draw(st.text(min_size=0, max_size=5))
                mixed_items.append(json_string_literal(s))
            elif t == 'number':
                n = draw(st.integers(min_value=-10, max_value=10))
                mixed_items.append(str(n))
            else:
                mixed_items.append("null")
        tags_json = "[" + ",".join(mixed_items) + "]"

    # child: either null or a nested record with one level recursion
    # We limit recursion depth to 1 by generating a child with no further child (child=null)
    child_type = draw(st.sampled_from(['null', 'child']))
    if child_type == 'null':
        child_json = "null"
    else:
        # child record with all fields present, but with simpler values (no further child)
        # For child, we keep it mostly valid but tweak one field to provoke divergence
        # We'll reuse some of the above logic but simpler and fixed to avoid combinatorial explosion

        # child.id always int
        child_id = draw(st.integers(min_value=0, max_value=1000))
        child_id_json = str(child_id)

        # child.amount always string numeric
        child_amount = draw(st.from_regex(r'\d+(\.\d+)?', fullmatch=True))
        child_amount_json = json_string_literal(child_amount)

        # child.name string or null
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=5)))
        if child_name is None:
            child_name_json = "null"
        else:
            child_name_json = json_string_literal(child_name)

        # child.status always valid enum string
        child_status_json = draw(st.sampled_from(STATUS_VALUES))

        # child.tags always array of strings (0-3)
        child_tags_list = draw(st.lists(st.text(min_size=0, max_size=3), max_size=3))
        child_tags_json_items = [json_string_literal(t) for t in child_tags_list]
        child_tags_json = "[" + ",".join(child_tags_json_items) + "]"

        # child.child always null (no recursion)
        child_child_json = "null"

        child_json = (
            "{" +
            f'"id":{child_id_json},' +
            f'"amount":{child_amount_json},' +
            f'"name":{child_name_json},' +
            f'"status":{child_status_json},' +
            f'"tags":{child_tags_json},' +
            f'"child":{child_child_json}' +
            "}"
        )

    # Compose the top-level JSON object text
    json_text = (
        "{" +
        f'"id":{id_json},' +
        f'"amount":{amount_json},' +
        f'"name":{name_json},' +
        f'"status":{status_json},' +
        f'"tags":{tags_json},' +
        f'"child":{child_json}' +
        "}"
    )

    return json_text.encode('utf-8')