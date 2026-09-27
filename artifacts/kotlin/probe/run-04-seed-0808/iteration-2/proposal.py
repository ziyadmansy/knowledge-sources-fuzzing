from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper: JSON string with proper escaping for simple ASCII subset (no control chars)
    def json_string(s: str) -> str:
        # Escape backslash and double quote only, minimal escaping for ASCII printable
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id: integer or string integer (always valid int)
    id_val = draw(st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),
        st.integers(min_value=0, max_value=2**31-1)
    ))

    # amount: string or number (Gson/Moshi/Jackson accept number, kotlinx rejects number)
    # To maximize divergence, sometimes produce number, sometimes string
    amount_is_number = draw(st.booleans())
    if amount_is_number:
        # number as int or float string (float with decimal point)
        amount_num = draw(st.one_of(
            st.integers(min_value=0, max_value=10**6),
            st.floats(min_value=0, max_value=10**6, allow_nan=False, allow_infinity=False)
        ))
        # JSON number text
        if isinstance(amount_num, float):
            # format float with minimal decimal places
            amount_text = repr(amount_num)
        else:
            amount_text = str(amount_num)
        amount_json = amount_text
    else:
        # string amount, possibly numeric string or arbitrary string
        # To maximize divergence, sometimes numeric string, sometimes arbitrary string
        amount_str = draw(st.one_of(
            st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])),
            st.integers(min_value=0, max_value=10**6).map(str)
        ))
        amount_json = json_string(amount_str)

    # name: string or null, or number (Gson/Moshi/Jackson accept number as string, kotlinx rejects number)
    # Also test null (allowed)
    name_choice = draw(st.sampled_from(['string', 'null', 'number']))
    if name_choice == 'string':
        # string or empty string
        name_str = draw(st.text(min_size=0, max_size=20, alphabet=st.characters(blacklist_characters=['"', '\\'])))
        name_json = json_string(name_str)
    elif name_choice == 'null':
        name_json = 'null'
    else:
        # number as int or float
        name_num = draw(st.one_of(
            st.integers(min_value=-1000, max_value=1000),
            st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)
        ))
        if isinstance(name_num, float):
            name_json = repr(name_num)
        else:
            name_json = str(name_num)

    # status: enum string "active", "inactive", "unknown"
    # Known divergences:
    # Gson accepts unknown enum as null
    # Moshi, kotlinx, Jackson reject unknown enum values
    # Gson accepts null for status, others reject null
    # Jackson rejects null with KotlinInvalidNullException
    # So produce either valid enum, unknown enum string, or null
    status_choice = draw(st.sampled_from(['valid', 'unknown', 'null']))
    if status_choice == 'valid':
        status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        status_json = json_string(status_val)
    elif status_choice == 'unknown':
        # unknown enum string (not in enum)
        # use a string not in enum, e.g. "pending"
        status_json = json_string('pending')
    else:
        status_json = 'null'

    # tags: array of strings normally
    # Known divergences:
    # All reject non-array tags
    # Gson, Moshi, Jackson accept array with non-string elements converting to strings
    # kotlinx rejects non-string elements in array
    # So produce array with strings or array with mixed types (strings + numbers)
    tags_array_type = draw(st.sampled_from(['all_strings', 'mixed']))
    if tags_array_type == 'all_strings':
        tags_len = draw(st.integers(min_value=0, max_value=5))
        tags_elems = []
        for _ in range(tags_len):
            s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
            tags_elems.append(json_string(s))
        tags_json = '[' + ','.join(tags_elems) + ']'
    else:
        # mixed strings and numbers (int or float)
        tags_len = draw(st.integers(min_value=1, max_value=5))
        tags_elems = []
        for _ in range(tags_len):
            elem_type = draw(st.booleans())
            if elem_type:
                s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
                tags_elems.append(json_string(s))
            else:
                n = draw(st.one_of(
                    st.integers(min_value=-1000, max_value=1000),
                    st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)
                ))
                if isinstance(n, float):
                    tags_elems.append(repr(n))
                else:
                    tags_elems.append(str(n))
        tags_json = '[' + ','.join(tags_elems) + ']'

    # child: null or nested record (one level recursion)
    # To keep bounded recursion, only one level
    # child can be null or a record with same rules but no further child (child=null)
    child_present = draw(st.booleans())
    if child_present:
        # child record with child=null to avoid deep recursion
        # id in child: integer or string integer
        child_id_val = draw(st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            st.integers(min_value=0, max_value=2**31-1)
        ))

        # amount in child: string or number (same rules)
        child_amount_is_number = draw(st.booleans())
        if child_amount_is_number:
            child_amount_num = draw(st.one_of(
                st.integers(min_value=0, max_value=10**6),
                st.floats(min_value=0, max_value=10**6, allow_nan=False, allow_infinity=False)
            ))
            if isinstance(child_amount_num, float):
                child_amount_json = repr(child_amount_num)
            else:
                child_amount_json = str(child_amount_num)
        else:
            child_amount_str = draw(st.one_of(
                st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])),
                st.integers(min_value=0, max_value=10**6).map(str)
            ))
            child_amount_json = json_string(child_amount_str)

        # name in child: string or null or number
        child_name_choice = draw(st.sampled_from(['string', 'null', 'number']))
        if child_name_choice == 'string':
            child_name_str = draw(st.text(min_size=0, max_size=20, alphabet=st.characters(blacklist_characters=['"', '\\'])))
            child_name_json = json_string(child_name_str)
        elif child_name_choice == 'null':
            child_name_json = 'null'
        else:
            child_name_num = draw(st.one_of(
                st.integers(min_value=-1000, max_value=1000),
                st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)
            ))
            if isinstance(child_name_num, float):
                child_name_json = repr(child_name_num)
            else:
                child_name_json = str(child_name_num)

        # status in child: valid enum, unknown enum, or null (same rules)
        child_status_choice = draw(st.sampled_from(['valid', 'unknown', 'null']))
        if child_status_choice == 'valid':
            child_status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
            child_status_json = json_string(child_status_val)
        elif child_status_choice == 'unknown':
            child_status_json = json_string('pending')
        else:
            child_status_json = 'null'

        # tags in child: all strings or mixed (same rules)
        child_tags_array_type = draw(st.sampled_from(['all_strings', 'mixed']))
        if child_tags_array_type == 'all_strings':
            child_tags_len = draw(st.integers(min_value=0, max_value=5))
            child_tags_elems = []
            for _ in range(child_tags_len):
                s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
                child_tags_elems.append(json_string(s))
            child_tags_json = '[' + ','.join(child_tags_elems) + ']'
        else:
            child_tags_len = draw(st.integers(min_value=1, max_value=5))
            child_tags_elems = []
            for _ in range(child_tags_len):
                elem_type = draw(st.booleans())
                if elem_type:
                    s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
                    child_tags_elems.append(json_string(s))
                else:
                    n = draw(st.one_of(
                        st.integers(min_value=-1000, max_value=1000),
                        st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)
                    ))
                    if isinstance(n, float):
                        child_tags_elems.append(repr(n))
                    else:
                        child_tags_elems.append(str(n))
            child_tags_json = '[' + ','.join(child_tags_elems) + ']'

        # child.child is always null (no deeper recursion)
        child_json = (
            '{'
            + '"id":' + (json_string(child_id_val) if isinstance(child_id_val, str) else str(child_id_val)) + ','
            + '"amount":' + child_amount_json + ','
            + '"name":' + child_name_json + ','
            + '"status":' + child_status_json + ','
            + '"tags":' + child_tags_json + ','
            + '"child":null'
            + '}'
        )
    else:
        child_json = 'null'

    # Compose top-level JSON object fields in order
    # id, amount, name, status, tags, child
    id_json = json_string(id_val) if isinstance(id_val, str) else str(id_val)

    json_text = (
        '{'
        + '"id":' + id_json + ','
        + '"amount":' + amount_json + ','
        + '"name":' + name_json + ','
        + '"status":' + status_json + ','
        + '"tags":' + tags_json + ','
        + '"child":' + child_json
        + '}'
    )

    return json_text.encode('utf-8')