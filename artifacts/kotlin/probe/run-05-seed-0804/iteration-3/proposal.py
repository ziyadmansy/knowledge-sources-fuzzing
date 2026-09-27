from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars)
def json_string_escape(s: str) -> str:
    # Escape backslash and double quote only for simplicity
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    # We build a JSON text string representing the record schema with controlled variations
    # to maximize divergence among Gson, Moshi, kotlinx.serialization, Jackson.
    #
    # Strategy:
    # - id: int or numeric string (both accepted by all)
    # - amount: string normally, but sometimes number (kotlinx rejects number)
    # - name: string, null, or non-string (number, bool) (kotlinx rejects non-string)
    # - status: valid enum string or invalid string or null (Gson accepts null/invalid as null, others reject)
    # - tags: array of strings normally, sometimes with null or non-string elements (kotlinx rejects non-string/ null elements)
    # - child: null or nested record (one level recursion)
    #   - child can be empty object (Gson accepts with defaults, others reject)
    #   - child can have extra fields (Gson, Moshi accept; kotlinx, Jackson reject)
    #
    # We pick one or two fields to vary off from well-formed at a time.
    #
    # We produce JSON text manually with string concatenation.

    # id field: int or numeric string (both accepted)
    id_int = draw(st.integers(min_value=0, max_value=10**6))
    id_as_string = draw(st.booleans())
    if id_as_string:
        id_json = '"' + str(id_int) + '"'
    else:
        id_json = str(id_int)

    # amount field: string normally, or number (kotlinx rejects number)
    # 70% string, 30% number
    amount_is_number = draw(st.booleans().filter(lambda b: b or True))  # no bias here, but let's keep 50/50
    if amount_is_number:
        # number as int or float string
        amount_num = draw(st.one_of(st.integers(min_value=0, max_value=10**6), st.floats(min_value=0, max_value=10**6, allow_nan=False, allow_infinity=False)))
        # format floats with minimal decimal places
        if isinstance(amount_num, float):
            amount_json = str(round(amount_num, 3))
        else:
            amount_json = str(amount_num)
    else:
        # string amount, random digits or decimal string
        amount_str = draw(st.text(alphabet='0123456789.', min_size=1, max_size=10))
        # sanitize to avoid empty or invalid JSON string
        if amount_str == '' or amount_str == '.':
            amount_str = '0'
        amount_json = '"' + json_string_escape(amount_str) + '"'

    # name field: string, null, or non-string (number, bool)
    # 50% string or null, 50% non-string (number or bool)
    name_type = draw(st.sampled_from(['string', 'null', 'number', 'bool']))
    if name_type == 'string':
        # string or null string
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        if name_val is None:
            name_json = 'null'
        else:
            name_json = '"' + json_string_escape(name_val) + '"'
    elif name_type == 'null':
        name_json = 'null'
    elif name_type == 'number':
        n = draw(st.one_of(st.integers(min_value=-1000, max_value=1000), st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
        if isinstance(n, float):
            name_json = str(round(n, 3))
        else:
            name_json = str(n)
    else:  # bool
        b = draw(st.booleans())
        name_json = 'true' if b else 'false'

    # status field: valid enum string or invalid string or null
    # valid: "active", "inactive", "unknown"
    # invalid: random string not in enum
    # null allowed only by Gson
    status_choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
    if status_choice == 'valid':
        status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        status_json = '"' + status_val + '"'
    elif status_choice == 'invalid':
        # random string not in enum
        invalid_str = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']))
        status_json = '"' + json_string_escape(invalid_str) + '"'
    else:
        status_json = 'null'

    # tags field: array of strings normally, sometimes with null or non-string elements
    # 60% all strings, 40% some null or non-string elements (kotlinx rejects non-string or null elements)
    tags_type = draw(st.sampled_from(['all_strings', 'mixed']))
    if tags_type == 'all_strings':
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        # encode as JSON array of strings
        tags_json = '[' + ','.join('"' + json_string_escape(t) + '"' for t in tags_list) + ']'
    else:
        # mixed: strings, null, numbers, bools
        tag_elem = st.one_of(
            st.text(min_size=0, max_size=10).map(lambda s: '"' + json_string_escape(s) + '"'),
            st.just('null'),
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.booleans().map(lambda b: 'true' if b else 'false'),
        )
        tags_list = draw(st.lists(tag_elem, min_size=1, max_size=5))
        tags_json = '[' + ','.join(tags_list) + ']'

    # child field: null or nested record
    # We limit recursion to one level only.
    # child can be null, empty object, well-formed, or with extra fields
    child_type = draw(st.sampled_from(['null', 'empty_object', 'well_formed', 'extra_fields', 'empty_child_in_child']))
    if child_type == 'null':
        child_json = 'null'
    elif child_type == 'empty_object':
        # empty object {}
        child_json = '{}'
    elif child_type == 'well_formed':
        # well-formed nested record with all fields present and valid
        # id: int or numeric string
        c_id_int = draw(st.integers(min_value=0, max_value=10**6))
        c_id_as_string = draw(st.booleans())
        if c_id_as_string:
            c_id_json = '"' + str(c_id_int) + '"'
        else:
            c_id_json = str(c_id_int)
        # amount: string only (to avoid kotlinx rejection here)
        c_amount_str = draw(st.text(alphabet='0123456789.', min_size=1, max_size=10))
        if c_amount_str == '' or c_amount_str == '.':
            c_amount_str = '0'
        c_amount_json = '"' + json_string_escape(c_amount_str) + '"'
        # name: string or null only
        c_name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        if c_name_val is None:
            c_name_json = 'null'
        else:
            c_name_json = '"' + json_string_escape(c_name_val) + '"'
        # status: valid enum string only
        c_status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        c_status_json = '"' + c_status_val + '"'
        # tags: array of strings only
        c_tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        c_tags_json = '[' + ','.join('"' + json_string_escape(t) + '"' for t in c_tags_list) + ']'
        # child: null (no recursion deeper)
        c_child_json = 'null'

        child_json = (
            '{'
            + '"id":' + c_id_json + ','
            + '"amount":' + c_amount_json + ','
            + '"name":' + c_name_json + ','
            + '"status":' + c_status_json + ','
            + '"tags":' + c_tags_json + ','
            + '"child":' + c_child_json
            + '}'
        )
    elif child_type == 'extra_fields':
        # well-formed nested record plus extra fields (Gson, Moshi accept; kotlinx, Jackson reject)
        # reuse well_formed but add extra fields
        c_id_int = draw(st.integers(min_value=0, max_value=10**6))
        c_id_as_string = draw(st.booleans())
        if c_id_as_string:
            c_id_json = '"' + str(c_id_int) + '"'
        else:
            c_id_json = str(c_id_int)
        c_amount_str = draw(st.text(alphabet='0123456789.', min_size=1, max_size=10))
        if c_amount_str == '' or c_amount_str == '.':
            c_amount_str = '0'
        c_amount_json = '"' + json_string_escape(c_amount_str) + '"'
        c_name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        if c_name_val is None:
            c_name_json = 'null'
        else:
            c_name_json = '"' + json_string_escape(c_name_val) + '"'
        c_status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        c_status_json = '"' + c_status_val + '"'
        c_tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        c_tags_json = '[' + ','.join('"' + json_string_escape(t) + '"' for t in c_tags_list) + ']'
        c_child_json = 'null'
        # extra fields
        extra_field_name = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['id','amount','name','status','tags','child']))
        extra_field_value = draw(st.one_of(
            st.integers(min_value=0, max_value=1000).map(str),
            st.text(min_size=0, max_size=10).map(lambda s: '"' + json_string_escape(s) + '"'),
            st.just('null'),
            st.booleans().map(lambda b: 'true' if b else 'false'),
        ))
        child_json = (
            '{'
            + '"id":' + c_id_json + ','
            + '"amount":' + c_amount_json + ','
            + '"name":' + c_name_json + ','
            + '"status":' + c_status_json + ','
            + '"tags":' + c_tags_json + ','
            + '"child":' + c_child_json + ','
            + '"' + json_string_escape(extra_field_name) + '":' + extra_field_value
            + '}'
        )
    else:  # empty_child_in_child
        # child with child = empty object {}
        # This triggers Gson accept with defaults, others reject
        c_id_int = draw(st.integers(min_value=0, max_value=10**6))
        c_id_as_string = draw(st.booleans())
        if c_id_as_string:
            c_id_json = '"' + str(c_id_int) + '"'
        else:
            c_id_json = str(c_id_int)
        c_amount_str = draw(st.text(alphabet='0123456789.', min_size=1, max_size=10))
        if c_amount_str == '' or c_amount_str == '.':
            c_amount_str = '0'
        c_amount_json = '"' + json_string_escape(c_amount_str) + '"'
        c_name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        if c_name_val is None:
            c_name_json = 'null'
        else:
            c_name_json = '"' + json_string_escape(c_name_val) + '"'
        c_status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        c_status_json = '"' + c_status_val + '"'
        c_tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        c_tags_json = '[' + ','.join('"' + json_string_escape(t) + '"' for t in c_tags_list) + ']'
        c_child_json = '{}'

        child_json = (
            '{'
            + '"id":' + c_id_json + ','
            + '"amount":' + c_amount_json + ','
            + '"name":' + c_name_json + ','
            + '"status":' + c_status_json + ','
            + '"tags":' + c_tags_json + ','
            + '"child":' + c_child_json
            + '}'
        )

    # Compose top-level JSON object string
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