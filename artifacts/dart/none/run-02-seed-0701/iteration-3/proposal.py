from hypothesis import strategies as st

# Helper: JSON string with proper escaping of quotes and backslashes only (minimal)
def json_string(draw, max_len=10):
    # Use ascii letters, digits, space, and a few safe punctuation chars except quotes and backslash
    safe_chars = st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd', 'Zs'),
        blacklist_characters=['"', '\\']
    )
    s = draw(st.text(safe_chars, max_size=max_len))
    # Escape backslash and quote if any slipped in (shouldn't, but just in case)
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + s + '"'

# Helper: JSON array of strings (tags)
@st.composite
def json_array_of_strings(draw):
    # 0 to 3 strings
    length = draw(st.integers(min_value=0, max_value=3))
    strs = [draw(json_string) for _ in range(length)]
    return '[' + ','.join(strs) + ']'

# Helper: JSON enum for status
def json_status(draw):
    # Intentionally sometimes produce invalid enum to provoke divergence
    # But mostly produce valid ones
    # We'll do this by drawing from a mixed strategy
    valid = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
    invalid = st.text(min_size=1, max_size=7).map(lambda s: '"' + s.replace('"', '\\"') + '"')
    # 80% valid, 20% invalid (to provoke divergence)
    return draw(st.one_of(st.just(None), valid, invalid)).replace('None', 'null') or '"unknown"'

# Main recursive record generator
@st.composite
def generated_json(draw, _depth=0):
    # Limit recursion depth to 1 (child can be null or a record with no child)
    # We'll produce a JSON object string with all six fields always present
    # but vary one or two fields to provoke divergence.

    # id: integer or sometimes string (wrong type)
    id_val = draw(st.one_of(
        st.integers(min_value=0, max_value=1000).map(str),
        st.text(min_size=1, max_size=5).map(lambda s: '"' + s.replace('"', '\\"') + '"')
    ))

    # amount: string representing a decimal number or sometimes a number (wrong type)
    # We produce a JSON string normally, but sometimes a bare number (no quotes)
    amount_str = draw(st.one_of(
        st.decimals(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False).map(lambda d: '"' + format(d, 'f') + '"'),
        st.decimals(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False).map(lambda d: format(d, 'f'))
    ))

    # name: string or null or sometimes number (wrong type)
    name_val = draw(st.one_of(
        st.just('null'),
        json_string,
        st.integers(min_value=0, max_value=1000).map(str)
    ))

    # status: mostly valid enum string, sometimes invalid string, sometimes null (wrong type)
    # We'll pick from valid enum strings or invalid strings or null
    status_val = draw(st.one_of(
        st.sampled_from(['"active"', '"inactive"', '"unknown"']),
        st.text(min_size=1, max_size=7).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
        st.just('null')
    ))

    # tags: array of strings or sometimes null or sometimes array with non-string elements
    # We'll produce mostly arrays of strings, sometimes null, sometimes array with a number inside
    tags_choice = draw(st.integers(min_value=0, max_value=4))
    if tags_choice == 0:
        tags_val = 'null'
    elif tags_choice == 1:
        # array of strings
        tags_val = draw(json_array_of_strings)
    elif tags_choice == 2:
        # array with one number element (wrong type)
        tags_val = '[123]'
    else:
        # empty array
        tags_val = '[]'

    # child: null or a nested record with no child (depth limit)
    if _depth >= 1:
        child_val = 'null'
    else:
        # 70% null, 30% nested record with child=null
        if draw(st.booleans()):
            child_val = 'null'
        else:
            nested = draw(generated_json(_depth=_depth + 1))
            # forcibly replace child's "child" field with null to avoid deeper recursion
            # We do this by parsing the nested string and replacing the child field's value with null
            # But we cannot parse JSON, so instead we generate nested with _depth=1 so child is null already
            child_val = nested

    # Compose JSON object string
    # Fields order: id, amount, name, status, tags, child
    json_obj = (
        '{'
        f'"id":{id_val},'
        f'"amount":{amount_str},'
        f'"name":{name_val},'
        f'"status":{status_val},'
        f'"tags":{tags_val},'
        f'"child":{child_val}'
        '}'
    )
    return json_obj.encode('utf-8')