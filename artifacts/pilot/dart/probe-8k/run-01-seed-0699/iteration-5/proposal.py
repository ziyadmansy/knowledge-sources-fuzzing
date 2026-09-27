from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Basic JSON string escaper for simple ASCII strings without control chars or quotes
    def json_string(s: str) -> str:
        # Escape backslash and quote only for safety
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id: integer
    id_strat = st.integers(min_value=-(2**31), max_value=2**31-1).map(str)

    # amount: string, but we will sometimes produce numeric-looking strings or empty strings
    # to test boundaries, but always a JSON string
    amount_strat = st.text(min_size=0, max_size=10).map(json_string)

    # name: string or null
    # To induce divergence, sometimes produce empty string, sometimes null, sometimes normal strings
    name_strat = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(json_string),
    )

    # status: enum string from allowed values
    status_strat = st.sampled_from(STATUS_VALUES)

    # tags: array of strings (strings can be empty, but no nulls)
    # To induce divergence, sometimes empty array, sometimes array with empty string, sometimes normal strings
    tags_elem_strat = st.text(min_size=0, max_size=5).map(json_string)
    tags_strat = st.lists(tags_elem_strat, min_size=0, max_size=3).map(
        lambda lst: '[' + ','.join(lst) + ']'
    )

    # child: null or a nested record (one level only)
    # To induce divergence, child can be null or a record with one field wrong or missing
    # but only one thing off at a time to maximize divergence chance

    # We'll define a helper to build a child record string with controlled deviations

    # Child record fields, mostly correct, but one field can be off or missing
    def child_record_with_one_deviation():
        # Decide which deviation to apply (or none)
        deviation = draw(st.one_of(
            st.just(None),  # no deviation, fully correct child
            st.sampled_from(['id_wrong_type', 'amount_wrong_type', 'name_wrong_type',
                             'status_invalid_enum', 'tags_wrong_type', 'tags_null_elem',
                             'child_missing', 'child_empty_object'])
        ))

        # id: integer or string (wrong type)
        if deviation == 'id_wrong_type':
            child_id = draw(st.text(min_size=1, max_size=3)).replace('"', '')  # string instead of int, no quotes
            child_id_str = json_string(child_id)  # string quoted, but id expects int -> will be string
        else:
            child_id_str = str(draw(st.integers(min_value=-(2**31), max_value=2**31-1)))

        # amount: string or integer (wrong type)
        if deviation == 'amount_wrong_type':
            child_amount_str = str(draw(st.integers(min_value=0, max_value=1000)))  # integer, no quotes
        else:
            child_amount_str = draw(st.text(min_size=0, max_size=10)).map(json_string).example()

        # name: string, null, or integer (wrong type)
        if deviation == 'name_wrong_type':
            child_name_str = str(draw(st.integers(min_value=0, max_value=1000)))  # integer, no quotes
        else:
            child_name_str = draw(st.one_of(
                st.none().map(lambda _: "null"),
                st.text(min_size=0, max_size=10).map(json_string)
            )).example()

        # status: valid enum or invalid enum string
        if deviation == 'status_invalid_enum':
            # invalid enum string
            child_status_str = json_string("invalid_status")
        else:
            child_status_str = draw(st.sampled_from(STATUS_VALUES)).example()

        # tags: array of strings, or wrong type (string), or contains null
        if deviation == 'tags_wrong_type':
            child_tags_str = json_string("not_an_array")
        elif deviation == 'tags_null_elem':
            # array with one null element
            child_tags_str = '[null]'
        else:
            tags_list = draw(st.lists(st.text(min_size=0, max_size=5).map(json_string), min_size=0, max_size=3))
            child_tags_str = '[' + ','.join(tags_list) + ']'

        # child field: normally null or a nested record (one level only)
        # For deviation 'child_missing' or 'child_empty_object', handle specially
        if deviation == 'child_missing':
            # omit child field entirely
            return None
        elif deviation == 'child_empty_object':
            # child: {}
            return '{}'
        else:
            # child: null or fully correct nested record (no further nesting)
            # To avoid infinite recursion, child.child is always null
            # Compose child record string
            # If deviation is None, all fields correct, else one field off as above
            # Compose JSON object string with all fields present
            # child.child is always null here
            child_child_str = 'null'

            # Compose fields
            fields = [
                '"id":' + child_id_str,
                '"amount":' + child_amount_str,
                '"name":' + child_name_str,
                '"status":' + child_status_str,
                '"tags":' + child_tags_str,
                '"child":' + child_child_str,
            ]
            return '{' + ','.join(fields) + '}'

    # Compose top-level record fields, mostly correct, but optionally one deviation in one field to induce divergence

    # Decide top-level deviation: None or one field wrong type or missing
    top_level_deviation = draw(st.one_of(
        st.just(None),
        st.sampled_from(['id_wrong_type', 'amount_wrong_type', 'name_wrong_type',
                         'status_invalid_enum', 'tags_wrong_type', 'tags_null_elem',
                         'child_missing', 'child_empty_object'])
    ))

    # id
    if top_level_deviation == 'id_wrong_type':
        id_val = draw(st.text(min_size=1, max_size=3)).replace('"', '')
        id_str = json_string(id_val)  # string instead of int
    else:
        id_str = draw(id_strat)

    # amount
    if top_level_deviation == 'amount_wrong_type':
        amount_str = str(draw(st.integers(min_value=0, max_value=1000)))  # integer, no quotes
    else:
        amount_str = draw(amount_strat)

    # name
    if top_level_deviation == 'name_wrong_type':
        name_str = str(draw(st.integers(min_value=0, max_value=1000)))  # integer, no quotes
    else:
        name_str = draw(name_strat)

    # status
    if top_level_deviation == 'status_invalid_enum':
        status_str = json_string("invalid_status")
    else:
        status_str = draw(status_strat)

    # tags
    if top_level_deviation == 'tags_wrong_type':
        tags_str = json_string("not_an_array")
    elif top_level_deviation == 'tags_null_elem':
        tags_str = '[null]'
    else:
        tags_str = draw(tags_strat)

    # child
    if top_level_deviation == 'child_missing':
        # omit child field entirely
        child_str = None
    elif top_level_deviation == 'child_empty_object':
        child_str = '{}'
    else:
        child_str = child_record_with_one_deviation()
        # child_record_with_one_deviation may return None if child_missing deviation inside child
        # If so, child field is omitted -> invalid child, triggers rejection
        # To keep child field present, if None, replace with null
        if child_str is None:
            child_str = 'null'

    # Compose fields list, omit child if None
    fields = [
        '"id":' + id_str,
        '"amount":' + amount_str,
        '"name":' + name_str,
        '"status":' + status_str,
        '"tags":' + tags_str,
    ]
    if child_str is not None:
        fields.append('"child":' + child_str)

    # Compose JSON object string
    json_obj = '{' + ','.join(fields) + '}'

    return json_obj.encode('utf-8')