from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with quotes escaped
    def json_string(s: str) -> str:
        # Escape backslash and double quote for JSON string
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return '"' + s + '"'

    # Strategy for "amount" field: string, but try valid decimal strings or edge cases
    amount_strat = st.one_of(
        # valid decimal strings
        st.decimals(min_value=-1e10, max_value=1e10, allow_infinity=False, allow_nan=False)
          .map(lambda d: format(d, 'f').rstrip('0').rstrip('.') if '.' in format(d, 'f') else format(d, 'f')),
        # empty string
        st.just(''),
        # strings that look like numbers but with whitespace or signs
        st.sampled_from(['+123', '-0', ' 42', '3.14 ', '0.0']),
        # strings with non-numeric chars (to test deserializer tolerance)
        st.sampled_from(['NaN', 'Infinity', '-Infinity', '1e10', '1_000']),
        # random ascii strings (short)
        st.text(min_size=1, max_size=5).filter(lambda s: all(c not in '"\\' for c in s))
    ).map(json_string)

    # Strategy for "name": either null or string (including empty or special chars)
    name_strat = st.one_of(
        st.just('null'),
        st.text(min_size=0, max_size=10).map(json_string)
    )

    # Strategy for "status": sometimes invalid string to trigger divergence
    status_strat = st.one_of(
        st.sampled_from(statuses),
        # invalid status strings to test rejection or fallback
        st.sampled_from(['"Active"', '"INACTIVE"', '"unknown "', '"invalid"', '"null"', 'null'])
    )

    # Strategy for "tags": array of strings, sometimes empty, sometimes with weird strings
    tags_strat = st.lists(
        st.text(min_size=0, max_size=8).map(json_string),
        min_size=0,
        max_size=4
    ).map(lambda lst: '[' + ','.join(lst) + ']')

    # Recursive strategy for "child" field: either null or a record (one level)
    # To avoid deep recursion, child.child is always null
    @st.composite
    def record(draw, allow_child=True):
        # id: integer, but sometimes as string or float to test type divergence
        id_val = draw(st.one_of(
            st.integers(min_value=0, max_value=1000).map(str),
            # id as string number (should be integer, so this is invalid)
            st.integers(min_value=0, max_value=1000).map(lambda i: json_string(str(i))),
            # id as float string (invalid)
            st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)
              .map(lambda f: format(f, 'f')),
            # id as invalid string
            st.sampled_from(['"abc"', '"123abc"', 'null'])
        ))

        amount_val = draw(amount_strat)
        name_val = draw(name_strat)
        status_val = draw(status_strat)
        tags_val = draw(tags_strat)

        if allow_child:
            # child is either null or a record with allow_child=False (no deeper recursion)
            child_val = draw(st.one_of(
                st.just('null'),
                record(allow_child=False).map(lambda s: s.decode('utf-8'))
            ))
        else:
            child_val = 'null'

        # Compose JSON object string with fields in fixed order
        # Intentionally sometimes omit quotes around id to test divergence
        # id_val is already a string representing the JSON value (number or string)
        json_obj = (
            '{'
            + '"id":' + id_val + ','
            + '"amount":' + amount_val + ','
            + '"name":' + name_val + ','
            + '"status":' + status_val + ','
            + '"tags":' + tags_val + ','
            + '"child":' + child_val
            + '}'
        )
        return json_obj.encode('utf-8')

    return draw(record())