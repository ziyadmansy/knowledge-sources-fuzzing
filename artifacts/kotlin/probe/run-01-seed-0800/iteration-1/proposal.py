from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string_escape(s: str) -> str:
    # Escape backslash and double quote only for simplicity
    return s.replace('\\', '\\\\').replace('"', '\\"')

# Compose JSON string literal from Python str
def json_string(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

# Compose JSON array of strings
def json_array_of_strings(lst) -> str:
    return '[' + ','.join(json_string(x) for x in lst) + ']'

# Compose JSON object from dict of {str: str} where values are raw JSON fragments
def json_object(d: dict) -> str:
    # keys are always strings, values are raw JSON text
    items = []
    for k, v in d.items():
        items.append(json_string(k) + ':' + v)
    return '{' + ','.join(items) + '}'

# Compose JSON null literal
json_null = 'null'

# Compose JSON boolean literals
json_true = 'true'
json_false = 'false'

# Compose JSON number literal from int or float or str (if str, emit as is)
def json_number(n) -> str:
    if isinstance(n, str):
        return n
    return str(n)

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON documents for the record schema with subtle variations to trigger divergence:
    - "id": int or stringified int or (rarely) float string
    - "amount": string normally, but sometimes number (Gson/Moshi/Jackson accept number, kotlinx rejects)
    - "name": string or null normally, sometimes number or boolean (Gson/Moshi/Jackson accept, kotlinx rejects)
    - "status": enum string ("active","inactive","unknown") normally,
        sometimes invalid enum string (Gson accepts as null, others reject),
        sometimes null (Gson accepts as null, others reject)
    - "tags": array of strings normally,
        sometimes array with non-string elements (Gson/Moshi/Jackson accept, kotlinx rejects),
        never non-array (all reject)
    - "child": null or nested record normally,
        sometimes empty object (Gson accepts, others reject),
        sometimes missing (Gson/Moshi/Jackson accept, kotlinx rejects)
    - Extra unknown fields at root level sometimes (Gson/Moshi accept, kotlinx/Jackson reject)
    - Missing optional "child" field sometimes (Gson/Moshi/Jackson accept, kotlinx rejects)
    """

    # id: int or stringified int or stringified float (rare)
    id_val = draw(st.integers(min_value=0, max_value=10000))
    id_type = draw(st.sampled_from(['int', 'str_int', 'str_float']))
    if id_type == 'int':
        id_json = json_number(id_val)
    elif id_type == 'str_int':
        id_json = json_string(str(id_val))
    else:  # str_float
        # float string close to int_val, e.g. "1234.0"
        id_json = json_string(str(float(id_val)) + '.0')

    # amount: string normally, sometimes number (Gson/Moshi/Jackson accept number, kotlinx rejects)
    amount_val = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
    # To increase chance of numeric string, mix digits and dots
    amount_val = draw(st.one_of(
        st.text(alphabet='0123456789.', min_size=1, max_size=10),
        st.just(amount_val)
    ))
    amount_type = draw(st.sampled_from(['str', 'num']))
    if amount_type == 'str':
        amount_json = json_string(amount_val)
    else:
        # Try to parse amount_val as float, fallback to 0 if invalid
        try:
            f = float(amount_val)
            # Emit as number literal without quotes
            amount_json = json_number(f)
        except Exception:
            amount_json = json_string(amount_val)

    # name: string or null normally, sometimes number or boolean (Gson/Moshi/Jackson accept, kotlinx rejects)
    name_type = draw(st.sampled_from(['str', 'null', 'num', 'bool']))
    if name_type == 'str':
        # string or null
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20, alphabet=st.characters(blacklist_characters='"\\'))))
        if name_val is None:
            name_json = json_null
        else:
            name_json = json_string(name_val)
    elif name_type == 'null':
        name_json = json_null
    elif name_type == 'num':
        # number as int or float
        n = draw(st.one_of(st.integers(min_value=-1000, max_value=1000), st.floats(allow_nan=False, allow_infinity=False)))
        name_json = json_number(n)
    else:
        # bool
        b = draw(st.booleans())
        name_json = json_true if b else json_false

    # status: enum string normally, sometimes invalid enum string or null
    status_choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
    if status_choice == 'valid':
        status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        status_json = json_string(status_val)
    elif status_choice == 'invalid':
        # invalid enum string (not one of the three)
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active','inactive','unknown']))
        status_json = json_string(invalid_status)
    else:
        # null
        status_json = json_null

    # tags: array of strings normally,
    # sometimes array with non-string elements (Gson/Moshi/Jackson accept, kotlinx rejects),
    # never non-array (all reject)
    tags_type = draw(st.sampled_from(['all_str', 'mixed']))
    if tags_type == 'all_str':
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\')), min_size=0, max_size=5))
        tags_json = json_array_of_strings(tags_list)
    else:
        # mixed types in array: strings, numbers, bools, nulls
        def json_value():
            t = draw(st.sampled_from(['str', 'num', 'bool', 'null']))
            if t == 'str':
                s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
                return json_string(s)
            elif t == 'num':
                n = draw(st.one_of(st.integers(min_value=-1000, max_value=1000), st.floats(allow_nan=False, allow_infinity=False)))
                return json_number(n)
            elif t == 'bool':
                b = draw(st.booleans())
                return json_true if b else json_false
            else:
                return json_null
        tags_list = draw(st.lists(st.deferred(lambda: json_value()), min_size=0, max_size=5))
        # tags_list is a list of JSON fragments (strings)
        tags_json = '[' + ','.join(tags_list) + ']'

    # child: null or nested record normally,
    # sometimes empty object (Gson accepts, others reject),
    # sometimes missing (Gson/Moshi/Jackson accept, kotlinx rejects)
    child_option = draw(st.sampled_from(['null', 'nested', 'empty_obj', 'missing']))

    # To avoid infinite recursion, limit depth to 1 level of recursion only
    # So nested child record has child=null always

    def make_child_record():
        # child record with child=null always
        # id: int or string int only (avoid float string here)
        cid_val = draw(st.integers(min_value=0, max_value=10000))
        cid_type = draw(st.sampled_from(['int', 'str_int']))
        if cid_type == 'int':
            cid_json = json_number(cid_val)
        else:
            cid_json = json_string(str(cid_val))

        # amount: string only (to keep simple)
        camount_val = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
        camount_json = json_string(camount_val)

        # name: string or null only
        cname_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20, alphabet=st.characters(blacklist_characters='"\\'))))
        if cname_val is None:
            cname_json = json_null
        else:
            cname_json = json_string(cname_val)

        # status: valid enum only
        cstatus_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        cstatus_json = json_string(cstatus_val)

        # tags: array of strings only
        ctags_list = draw(st.lists(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\')), min_size=0, max_size=5))
        ctags_json = json_array_of_strings(ctags_list)

        # child: null
        cchild_json = json_null

        child_obj = {
            "id": cid_json,
            "amount": camount_json,
            "name": cname_json,
            "status": cstatus_json,
            "tags": ctags_json,
            "child": cchild_json,
        }
        return json_object(child_obj)

    if child_option == 'null':
        child_json = json_null
    elif child_option == 'nested':
        child_json = make_child_record()
    elif child_option == 'empty_obj':
        child_json = '{}'
    else:  # missing
        child_json = None  # omit field

    # Compose root object fields
    root_fields = {
        "id": id_json,
        "amount": amount_json,
        "name": name_json,
        "status": status_json,
        "tags": tags_json,
    }
    if child_json is not None:
        root_fields["child"] = child_json

    # Extra unknown fields at root level sometimes (Gson/Moshi accept, kotlinx/Jackson reject)
    add_extra = draw(st.booleans())
    if add_extra:
        # Add one or two extra fields with simple values
        extra_fields = {}
        n_extra = draw(st.integers(min_value=1, max_value=2))
        for i in range(n_extra):
            key = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
            # Value: string or number or bool or null
            val_type = draw(st.sampled_from(['str', 'num', 'bool', 'null']))
            if val_type == 'str':
                val = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
                val_json = json_string(val)
            elif val_type == 'num':
                n = draw(st.one_of(st.integers(min_value=-1000, max_value=1000), st.floats(allow_nan=False, allow_infinity=False)))
                val_json = json_number(n)
            elif val_type == 'bool':
                b = draw(st.booleans())
                val_json = json_true if b else json_false
            else:
                val_json = json_null
            extra_fields[key] = val_json
        root_fields.update(extra_fields)

    json_text = json_object(root_fields)
    return json_text.encode('utf-8')