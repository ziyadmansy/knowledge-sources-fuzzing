from hypothesis import strategies as st

# Constants for fields
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce JSON string literal with proper escaping for simple ASCII subset
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping for ASCII subset
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text for the record schema with subtle variations to provoke
    divergence among Gson, Moshi, kotlinx.serialization, and Jackson Kotlin module.

    Variations:
    - "id": integer or string integer (type divergence)
    - "amount": string normally, or number (type divergence)
    - "name": string, null, or missing (missing field)
    - "status": one of valid strings, or invalid string (type or enum divergence)
    - "tags": array of strings normally, or array with one non-string element, or empty array
    - "child": null, missing, or nested record (one level recursion only)
    """

    # Control recursion depth: 0 or 1
    depth = draw(st.integers(min_value=0, max_value=1))

    # id: mostly integer, sometimes string integer (to provoke type divergence)
    id_is_int = draw(st.booleans())
    if id_is_int:
        id_val = str(draw(st.integers(min_value=0, max_value=10**9)))
    else:
        # string integer
        id_val = json_string_literal(str(draw(st.integers(min_value=0, max_value=10**9))))

    # amount: mostly string decimal, sometimes number (type divergence)
    amount_is_string = draw(st.booleans())
    if amount_is_string:
        # decimal string, possibly with leading zeros or sign to provoke subtle parsing differences
        sign = draw(st.sampled_from(['', '-', '+']))
        int_part = draw(st.integers(min_value=0, max_value=9999))
        frac_part = draw(st.one_of(st.just(''), st.just('.'), st.text(min_size=1, max_size=3, alphabet='0123456789')))
        # frac_part can be empty string or digits, but if empty string, no dot
        if frac_part == '':
            amount_val = json_string_literal(sign + str(int_part))
        elif frac_part == '.':
            # malformed decimal string with trailing dot (likely rejected by some)
            amount_val = json_string_literal(sign + str(int_part) + '.')
        else:
            amount_val = json_string_literal(sign + str(int_part) + '.' + frac_part)
    else:
        # number directly, integer or float
        amount_val = draw(st.one_of(
            st.integers(min_value=-10**9, max_value=10**9).map(str),
            st.floats(allow_infinity=False, allow_nan=False, width=32).map(lambda f: format(f, '.6g'))
        ))

    # name: string, null, or missing (missing field to provoke divergence)
    name_choice = draw(st.sampled_from(['string', 'null', 'missing']))
    if name_choice == 'string':
        # simple ASCII string or empty string
        name_val = json_string_literal(draw(st.text(min_size=0, max_size=10, alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ')))
        name_field = f'"name":{name_val}'
    elif name_choice == 'null':
        name_field = '"name":null'
    else:
        name_field = None  # omit field

    # status: valid enum string or invalid string (to provoke enum parsing divergence)
    status_valid = draw(st.booleans())
    if status_valid:
        status_val = draw(st.sampled_from(STATUS_VALUES))
    else:
        # invalid enum string, random ASCII string not in STATUS_VALUES
        invalid_status = draw(st.text(min_size=1, max_size=10, alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'))
        # ensure invalid_status not in STATUS_VALUES (without quotes)
        while f'"{invalid_status}"' in STATUS_VALUES:
            invalid_status = draw(st.text(min_size=1, max_size=10, alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'))
        status_val = json_string_literal(invalid_status)

    # tags: array of strings normally, or array with one non-string element, or empty array
    tags_type = draw(st.sampled_from(['all_strings', 'one_non_string', 'empty']))
    if tags_type == 'all_strings':
        tags_list = draw(st.lists(st.text(min_size=0, max_size=8, alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'), min_size=1, max_size=5))
        tags_json = '[' + ','.join(json_string_literal(t) for t in tags_list) + ']'
    elif tags_type == 'one_non_string':
        # at least one element is non-string (number or null)
        n = draw(st.integers(min_value=1, max_value=5))
        # position of non-string element
        pos = draw(st.integers(min_value=0, max_value=n-1))
        elems = []
        for i in range(n):
            if i == pos:
                # non-string element: number or null
                non_str_choice = draw(st.sampled_from(['number', 'null']))
                if non_str_choice == 'number':
                    elems.append(str(draw(st.integers(min_value=-1000, max_value=1000))))
                else:
                    elems.append('null')
            else:
                elems.append(json_string_literal(draw(st.text(min_size=0, max_size=8, alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'))))
        tags_json = '[' + ','.join(elems) + ']'
    else:
        tags_json = '[]'

    # child: null, missing, or nested record (one level recursion only)
    if depth == 0:
        # no nested child, choose null or missing
        child_choice = draw(st.sampled_from(['null', 'missing']))
        if child_choice == 'null':
            child_field = '"child":null'
        else:
            child_field = None
    else:
        # nested record, generate with depth=0 to avoid deeper recursion
        nested_json_bytes = generated_json(draw)
        # nested_json_bytes is bytes, decode to str
        nested_json_str = nested_json_bytes.decode('utf-8')
        child_field = f'"child":{nested_json_str}'

    # Compose fields
    fields = []

    fields.append(f'"id":{id_val}')
    fields.append(f'"amount":{amount_val}')
    if name_field is not None:
        fields.append(name_field)
    fields.append(f'"status":{status_val}')
    fields.append(f'"tags":{tags_json}')
    if child_field is not None:
        fields.append(child_field)

    # Shuffle fields order to avoid positional bias
    fields = draw(st.permutations(fields))

    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')