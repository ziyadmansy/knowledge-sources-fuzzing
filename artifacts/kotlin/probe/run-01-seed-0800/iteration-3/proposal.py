from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping for test purposes
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Compose JSON array from list of JSON elements (strings)
def json_array(elems):
    return '[' + ','.join(elems) + ']'

# Compose JSON object from list of (key, value) pairs (both strings)
def json_object(pairs):
    # pairs: list of (key, value) where key is unescaped string, value is JSON text string
    # keys must be JSON strings
    return '{' + ','.join(json_string(k) + ':' + v for k, v in pairs) + '}'

# Compose JSON null
json_null = 'null'

# Compose JSON boolean
def json_bool(b: bool) -> str:
    return 'true' if b else 'false'

# Compose JSON number from int or float (no exponent, no leading zeros)
def json_number(n: int) -> str:
    return str(n)

# Compose JSON enum "status" values or invalid variants
status_values = ['"active"', '"inactive"', '"unknown"']
invalid_status_values = ['"invalid"', 'null', '123', 'true', '{}', '[]']

@st.composite
def generated_json(draw) -> bytes:
    # We produce a JSON text string representing the root record, then encode utf-8 bytes
    
    # Strategy to produce a valid "id" field value: either number or string number
    id_num = draw(st.integers(min_value=0, max_value=1000000))
    id_as_number = draw(st.booleans())
    id_json = json_number(id_num) if id_as_number else json_string(str(id_num))
    
    # Strategy for "amount" field:
    # Known divergence: kotlinx.serialization rejects numeric amount; others accept numeric or string.
    # So we vary amount as string or number string or number.
    # Also try some invalid types (bool, null) to provoke divergence.
    amount_type = draw(st.sampled_from(['string', 'number', 'bool', 'null']))
    if amount_type == 'string':
        # amount as string numeric or arbitrary string
        amount_val = draw(st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '"\\')),
            st.integers(min_value=0, max_value=1000000).map(str)
        ))
        amount_json = json_string(amount_val)
    elif amount_type == 'number':
        amount_val = draw(st.integers(min_value=0, max_value=1000000))
        amount_json = json_number(amount_val)
    elif amount_type == 'bool':
        amount_json = json_bool(draw(st.booleans()))
    else:  # null
        amount_json = json_null
    
    # Strategy for "name" field:
    # Known divergence: kotlinx.serialization rejects non-string; others accept number or bool converting to string.
    # So vary name as string, null, number, bool.
    name_type = draw(st.sampled_from(['string', 'null', 'number', 'bool']))
    if name_type == 'string':
        # string or empty string or unicode-free ASCII string
        name_val = draw(st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in '"\\')))
        name_json = json_string(name_val)
    elif name_type == 'null':
        name_json = json_null
    elif name_type == 'number':
        name_json = json_number(draw(st.integers(min_value=-1000, max_value=1000)))
    else:  # bool
        name_json = json_bool(draw(st.booleans()))
    
    # Strategy for "status" field:
    # Known divergence: Gson accepts invalid enum and null, others reject.
    # So pick valid enum, invalid enum, or null.
    status_choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
    if status_choice == 'valid':
        status_json = draw(st.sampled_from(status_values))
    elif status_choice == 'invalid':
        status_json = draw(st.sampled_from(invalid_status_values))
    else:
        status_json = json_null
    
    # Strategy for "tags" field:
    # Known divergence: all reject non-array; Gson/Moshi/Jackson accept non-string elements converting to string; kotlinx.serialization rejects.
    # So tags can be array of strings, array with non-string elements, or non-array (string, number, bool, null).
    tags_type = draw(st.sampled_from(['array_strings', 'array_mixed', 'non_array']))
    if tags_type == 'array_strings':
        # array of strings (0 to 3 elements)
        tag_elems = draw(st.lists(st.text(min_size=0, max_size=5).filter(lambda s: all(c not in s for c in '"\\')), max_size=3))
        tags_json = json_array([json_string(t) for t in tag_elems])
    elif tags_type == 'array_mixed':
        # array of mixed elements (string, number, bool, null)
        def tag_elem():
            t = draw(st.sampled_from(['string', 'number', 'bool', 'null']))
            if t == 'string':
                return json_string(draw(st.text(min_size=0, max_size=5).filter(lambda s: all(c not in s for c in '"\\'))))
            elif t == 'number':
                return json_number(draw(st.integers(min_value=-10, max_value=10)))
            elif t == 'bool':
                return json_bool(draw(st.booleans()))
            else:
                return json_null
        tag_elems = draw(st.lists(st.deferred(tag_elem), max_size=3))
        tags_json = json_array(tag_elems)
    else:
        # non-array: string, number, bool, null
        non_array_type = draw(st.sampled_from(['string', 'number', 'bool', 'null']))
        if non_array_type == 'string':
            tags_json = json_string(draw(st.text(min_size=0, max_size=5).filter(lambda s: all(c not in s for c in '"\\'))))
        elif non_array_type == 'number':
            tags_json = json_number(draw(st.integers(min_value=-10, max_value=10)))
        elif non_array_type == 'bool':
            tags_json = json_bool(draw(st.booleans()))
        else:
            tags_json = json_null
    
    # Strategy for "child" field:
    # Known divergence:
    # - Gson accepts empty object for child, others reject.
    # - Gson/Moshi accept missing optional child in nested records; kotlinx.serialization rejects missing fields; Jackson accepts missing child.
    # So child can be null, missing (omit field), empty object, or a valid nested record.
    # We limit recursion to one level.
    child_choice = draw(st.sampled_from(['null', 'missing', 'empty_object', 'valid']))
    
    # Compose nested child record if needed
    def make_child():
        # child record must have all six fields present and well-formed (except we can vary some fields similarly)
        # For simplicity, child fields are well-formed with minimal variation to avoid too broad malformation.
        child_id_num = draw(st.integers(min_value=0, max_value=1000000))
        child_id_json = json_number(child_id_num)
        child_amount_json = json_string("123.45")
        child_name_json = json_null
        child_status_json = '"active"'
        child_tags_json = json_array([])
        child_child_json = json_null
        return json_object([
            ("id", child_id_json),
            ("amount", child_amount_json),
            ("name", child_name_json),
            ("status", child_status_json),
            ("tags", child_tags_json),
            ("child", child_child_json),
        ])
    
    if child_choice == 'null':
        child_json = json_null
        include_child = True
    elif child_choice == 'missing':
        # omit child field entirely
        include_child = False
        child_json = None
    elif child_choice == 'empty_object':
        child_json = '{}'
        include_child = True
    else:
        child_json = make_child()
        include_child = True
    
    # Compose root object fields
    fields = [
        ("id", id_json),
        ("amount", amount_json),
        ("name", name_json),
        ("status", status_json),
        ("tags", tags_json),
    ]
    if include_child:
        fields.append(("child", child_json))
    
    # Compose JSON text
    json_text = json_object(fields)
    
    return json_text.encode('utf-8')