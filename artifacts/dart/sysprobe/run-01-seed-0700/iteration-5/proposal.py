from hypothesis import strategies as st

# Constants for enum values
STATUS_VALUES = ['active', 'inactive', 'unknown']

# Helper to produce a JSON string literal with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # Minimal escaping for JSON string: backslash and double quote
    # Hypothesis strings are unicode, but we keep it simple here
    escaped = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + escaped + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to maximize behavioral divergence among four Dart JSON deserializers.
    """

    # --- Primitive field strategies ---

    # id: integer normally, but also try floats and exponent forms (as strings) to trigger divergence
    # We produce the JSON text for the value directly (not Python int/float)
    id_type = draw(st.sampled_from(['int', 'float', 'exponent']))
    if id_type == 'int':
        # 32-bit range and beyond (to cover large ints)
        id_val = draw(st.integers(min_value=-2**40, max_value=2**40))
        id_json = str(id_val)
    elif id_type == 'float':
        # float with decimal point, e.g. 123.0 or -5.5
        f = draw(st.floats(min_value=-1e6, max_value=1e6, allow_infinity=False, allow_nan=False))
        # Format with decimal point, no exponent
        id_json = ('%.6f' % f).rstrip('0').rstrip('.')
        if id_json == '-0':
            id_json = '0'
    else:
        # exponent form, e.g. 1e3, -2E4
        base = draw(st.integers(min_value=1, max_value=1000))
        exp = draw(st.integers(min_value=-10, max_value=10))
        sign = draw(st.sampled_from(['', '-']))
        id_json = f'{sign}{base}e{exp}'

    # amount: string, numeric strings including fractional, or non-numeric strings
    # Also try empty string and strings with spaces to test edge cases
    amount_type = draw(st.sampled_from(['numeric_str', 'non_numeric_str', 'empty', 'spaces']))
    if amount_type == 'numeric_str':
        # numeric string, possibly fractional
        # Use decimal strings, no exponent to avoid confusion
        whole = draw(st.integers(min_value=0, max_value=10**6))
        frac = draw(st.one_of(st.just(''), st.text(min_size=1, max_size=6, alphabet='0123456789')))
        if frac == '':
            amount_str = str(whole)
        else:
            amount_str = f"{whole}.{frac}"
    elif amount_type == 'non_numeric_str':
        # arbitrary string, possibly with digits but not a valid number
        amount_str = draw(st.text(min_size=1, max_size=10).filter(lambda s: not s.replace('.', '', 1).isdigit()))
    elif amount_type == 'empty':
        amount_str = ''
    else:
        # spaces only string
        amount_str = ' ' * draw(st.integers(min_value=1, max_value=5))

    amount_json = json_string_literal(amount_str)

    # name: string or null (null allowed only here)
    # Also test empty string, unicode, and strings with quotes/backslashes
    name_type = draw(st.sampled_from(['null', 'empty', 'normal', 'quotes', 'unicode']))
    if name_type == 'null':
        name_json = 'null'
    elif name_type == 'empty':
        name_json = '""'
    elif name_type == 'normal':
        name_val = draw(st.text(min_size=1, max_size=20).filter(lambda s: '"' not in s and '\\' not in s))
        name_json = json_string_literal(name_val)
    elif name_type == 'quotes':
        # string with quotes and backslashes to test escaping
        name_val = draw(st.text(min_size=1, max_size=20).filter(lambda s: '"' in s or '\\' in s))
        name_json = json_string_literal(name_val)
    else:
        # unicode string with some non-ASCII chars
        name_val = draw(st.text(min_size=1, max_size=20).filter(lambda s: any(ord(c) > 127 for c in s)))
        name_json = json_string_literal(name_val)

    # status: enum, test valid and invalid casing/values
    status_type = draw(st.sampled_from(['valid', 'invalid_case', 'invalid_value']))
    if status_type == 'valid':
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_json = json_string_literal(status_val)
    elif status_type == 'invalid_case':
        # uppercase variants of valid values
        status_val = draw(st.sampled_from([v.upper() for v in STATUS_VALUES]))
        status_json = json_string_literal(status_val)
    else:
        # unknown value
        status_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES))
        status_json = json_string_literal(status_val)

    # tags: array of strings, or null or missing (built_value accepts null or missing as empty list)
    # We try:
    # - well-formed array with strings
    # - empty array
    # - null
    # - missing (omit field)
    # - array with non-string elements (should be rejected by all)
    tags_variant = draw(st.sampled_from(['array_strings', 'empty_array', 'null', 'missing', 'array_nonstring']))
    if tags_variant == 'array_strings':
        # array of 0-5 strings, some empty, some normal, some unicode
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=1, max_size=5))
        tags_json = '[' + ','.join(json_string_literal(t) for t in tags_list) + ']'
        tags_field = f'"tags":{tags_json}'
    elif tags_variant == 'empty_array':
        tags_field = '"tags":[]'
    elif tags_variant == 'null':
        tags_field = '"tags":null'
    elif tags_variant == 'missing':
        tags_field = None
    else:
        # array with non-string elements: mix of ints, bools, nulls
        non_str_elems = draw(st.lists(st.one_of(
            st.integers(min_value=-10, max_value=10).map(str),
            st.sampled_from(['true', 'false', 'null'])
        ), min_size=1, max_size=5))
        tags_json = '[' + ','.join(non_str_elems) + ']'
        tags_field = f'"tags":{tags_json}'

    # child: either null, missing, or a nested Record (one level only)
    # We limit recursion depth to 1 (child.child is always null)
    child_variant = draw(st.sampled_from(['null', 'missing', 'nested']))
    if child_variant == 'null':
        child_field = '"child":null'
    elif child_variant == 'missing':
        child_field = None
    else:
        # nested child record, all fields present and well-formed except:
        # - child.child is always null to limit recursion
        # We reuse some of the above strategies but simpler and valid to avoid too many rejections
        # id: int only
        child_id = draw(st.integers(min_value=0, max_value=1000))
        child_id_json = str(child_id)
        # amount: numeric string only
        child_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: s.replace('.', '', 1).isdigit()))
        child_amount_json = json_string_literal(child_amount)
        # name: string or null
        child_name = draw(st.one_of(st.none(), st.text(min_size=1, max_size=10)))
        if child_name is None:
            child_name_json = 'null'
        else:
            child_name_json = json_string_literal(child_name)
        # status: valid enum only
        child_status = draw(st.sampled_from(STATUS_VALUES))
        child_status_json = json_string_literal(child_status)
        # tags: non-empty array of strings
        child_tags_list = draw(st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=3))
        child_tags_json = '[' + ','.join(json_string_literal(t) for t in child_tags_list) + ']'
        # child.child: null
        child_child_json = 'null'

        child_field = (
            '{'
            f'"id":{child_id_json},'
            f'"amount":{child_amount_json},'
            f'"name":{child_name_json},'
            f'"status":{child_status_json},'
            f'"tags":{child_tags_json},'
            f'"child":{child_child_json}'
            '}'
        )
        child_field = f'"child":{child_field}'

    # id, amount, name, status fields are always present
    # tags and child may be missing (None) or present

    # Compose fields list
    fields = [
        f'"id":{id_json}',
        f'"amount":{amount_json}',
        f'"name":{name_json}',
        f'"status":{status_json}',
    ]
    if tags_field is not None:
        fields.append(tags_field)
    if child_field is not None:
        fields.append(child_field)

    # To increase divergence, randomly duplicate one key with a different value (last wins)
    # Only do this sometimes
    if draw(st.booleans()):
        # Pick a key to duplicate from those present
        dup_key = draw(st.sampled_from(['id', 'amount', 'name', 'status', 'tags', 'child']))
        # Generate a different value for that key
        if dup_key == 'id':
            # Different int value
            dup_val = str(draw(st.integers(min_value=-1000, max_value=1000)))
        elif dup_key == 'amount':
            dup_val = json_string_literal(draw(st.text(min_size=1, max_size=5)))
        elif dup_key == 'name':
            dup_val = json_string_literal(draw(st.text(min_size=1, max_size=5)))
        elif dup_key == 'status':
            dup_val = json_string_literal(draw(st.sampled_from(STATUS_VALUES)))
        elif dup_key == 'tags':
            dup_val = '[]'  # empty array
        else:  # child
            dup_val = 'null'
        fields.append(f'"{dup_key}":{dup_val}')

    # Shuffle fields to vary order (including duplicates)
    fields = draw(st.permutations(fields))

    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')