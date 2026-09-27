from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ['active', 'inactive', 'unknown']

    # Helper to produce JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for " and \ to keep JSON valid
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id field: test int vs float integral
    # Manual requires int exact, others accept integral floats
    # So produce either int or integral float (e.g. 1 or 1.0)
    id_is_float = draw(st.booleans())
    if id_is_float:
        # integral float as number with .0
        id_val_int = draw(st.integers(min_value=0, max_value=1000))
        id_val = f"{id_val_int}.0"
    else:
        id_val_int = draw(st.integers(min_value=0, max_value=1000))
        id_val = str(id_val_int)

    # amount: must be string exact, no coercion
    # produce string normally, but sometimes produce number to cause rejection
    # but we want mostly almost valid, so mostly string, sometimes number string
    amount_is_string = draw(st.booleans())
    if amount_is_string:
        amount_val = draw(st.text(min_size=1, max_size=10))
        amount_json = json_string(amount_val)
    else:
        # number as JSON number (not string) to cause rejection by manual and built_value
        amount_num = draw(st.integers(min_value=0, max_value=100000))
        amount_json = str(amount_num)

    # name: string or null or missing (missing treated as null by all)
    # built_value omits null on serialization but accepts null if present
    # manual and json_serializable/freezed accept null or string
    # So produce either string, null, or omit
    name_choice = draw(st.sampled_from(['string', 'null', 'missing']))
    if name_choice == 'string':
        name_val = draw(st.text(min_size=0, max_size=10))
        name_json = f'"name":{json_string(name_val)}'
    elif name_choice == 'null':
        name_json = '"name":null'
    else:
        name_json = None  # omit field

    # status: one of enum strings, or unknown string to cause error
    # manual throws raw ArgumentError on unknown string
    # json_serializable/freezed throw CheckedFromJsonException
    # built_value throws ArgumentError wrapped in BuiltValueNestedFieldError if nested
    # So produce either valid enum or invalid string (case sensitive)
    status_is_valid = draw(st.booleans())
    if status_is_valid:
        status_val = draw(st.sampled_from(STATUS_VALUES))
    else:
        # invalid enum string, e.g. "Active" (wrong case) or "invalid"
        invalid_status_candidates = ['Active', 'INACTIVE', 'unknowns', 'invalid', '']
        status_val = draw(st.sampled_from(invalid_status_candidates))
    status_json = f'"status":{json_string(status_val)}'

    # tags: must be non-null array of strings, no null or missing allowed
    # manual and others reject non-string elements or missing/null tags
    # So produce either valid array of strings or array with one non-string element to cause rejection
    tags_valid = draw(st.booleans())
    if tags_valid:
        # non-empty list of strings
        tags_list = draw(st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=5))
        tags_json = '"tags":[' + ','.join(json_string(t) for t in tags_list) + ']'
    else:
        # introduce one non-string element (int or null) in tags
        tags_list = draw(st.lists(st.text(min_size=1, max_size=5), min_size=0, max_size=4))
        # insert one non-string element at random position
        non_string_elem = draw(st.one_of(st.integers(min_value=0, max_value=100), st.just('null')))
        insert_pos = draw(st.integers(min_value=0, max_value=len(tags_list)))
        tags_list.insert(insert_pos, non_string_elem)
        # serialize tags with mixed types
        def serialize_tag(t):
            if isinstance(t, str):
                return json_string(t)
            elif t == 'null':
                return 'null'
            else:
                return str(t)
        tags_json = '"tags":[' + ','.join(serialize_tag(t) for t in tags_list) + ']'

    # child: null or nested object or missing (missing treated as null)
    # built_value requires null or valid BvRecord
    # if child present but not object/map, all reject
    # So produce either null, missing, or nested object with one level recursion
    # Limit recursion depth to 1 (no child.child)
    child_choice = draw(st.sampled_from(['null', 'missing', 'object', 'badtype']))
    if child_choice == 'null':
        child_json = '"child":null'
    elif child_choice == 'missing':
        child_json = None
    elif child_choice == 'badtype':
        # child present but not object/map, e.g. number or string
        bad_child_val = draw(st.one_of(st.integers(min_value=0, max_value=100), st.text(min_size=1, max_size=5)))
        if isinstance(bad_child_val, int):
            child_json = f'"child":{bad_child_val}'
        else:
            child_json = f'"child":{json_string(bad_child_val)}'
    else:
        # nested object with no child inside (child.child always null or missing)
        # reuse fields but no recursion deeper than 1
        # For nested child, use only valid fields to isolate divergences to top-level
        # id: int only (no float)
        child_id = draw(st.integers(min_value=0, max_value=1000))
        child_id_json = str(child_id)
        # amount: string only
        child_amount = draw(st.text(min_size=1, max_size=10))
        child_amount_json = json_string(child_amount)
        # name: string or null
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        if child_name is None:
            child_name_json = '"name":null'
        else:
            child_name_json = f'"name":{json_string(child_name)}'
        # status: valid enum only
        child_status = draw(st.sampled_from(STATUS_VALUES))
        child_status_json = f'"status":{json_string(child_status)}'
        # tags: valid list of strings, non-empty
        child_tags_list = draw(st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=3))
        child_tags_json = '"tags":[' + ','.join(json_string(t) for t in child_tags_list) + ']'
        # child.child omitted (missing)
        child_json = (
            '"child":{'
            + f'"id":{child_id_json},'
            + f'"amount":{child_amount_json},'
            + f'{child_name_json},'
            + f'{child_status_json},'
            + f'{child_tags_json}'
            + '}'
        )

    # Compose top-level JSON object fields
    # Fields order: id, amount, name?, status, tags, child?
    fields = [
        f'"id":{id_val}',
        f'"amount":{amount_json}',
    ]
    if name_json is not None:
        fields.append(name_json)
    fields.append(status_json)
    fields.append(tags_json)
    if child_json is not None:
        fields.append(child_json)

    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')