from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and tags
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # We will produce JSON text manually, carefully controlling spacing and quotes.

    # Helper to produce JSON string literal with proper escaping of " and \
    def json_string_literal(s: str) -> str:
        # Minimal escaping for " and \ to keep JSON valid
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id: integer or string convertible integer (Probe 2)
    # We try to vary id as int or string int
    def gen_id():
        as_int = draw(st.integers(min_value=0, max_value=1000))
        as_str = draw(st.booleans())
        if as_str:
            return json_string_literal(str(as_int))
        else:
            return str(as_int)

    # amount: string normally, but also number (Probe 3)
    # We try to produce string or number for amount
    def gen_amount():
        # amount is string normally, but Gson/Moshi/Jackson accept number coercion, kotlinx rejects
        # So we try to produce either string or number
        as_number = draw(st.booleans())
        if as_number:
            # number as int or float string
            n = draw(st.one_of(st.integers(min_value=0, max_value=100000), st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)))
            # Format floats with minimal decimal places
            if isinstance(n, float):
                # Format float with minimal decimal places, no trailing zeros
                s = ('%.10f' % n).rstrip('0').rstrip('.')
                if s == '':
                    s = '0'
                return s
            else:
                return str(n)
        else:
            # string amount, possibly numeric string or arbitrary string
            # To maximize divergence, sometimes numeric string, sometimes arbitrary string
            numeric_str = draw(st.booleans())
            if numeric_str:
                n = draw(st.integers(min_value=0, max_value=100000))
                return json_string_literal(str(n))
            else:
                # arbitrary string, but avoid quotes or backslash to keep simple
                s = draw(st.text(alphabet=st.characters(blacklist_characters=['"', '\\']), min_size=1, max_size=10))
                return json_string_literal(s)

    # name: string or null, also number coerced to string accepted by Gson/Moshi/Jackson, rejected by kotlinx (Probe 4)
    # We try: null, string, number (int or float)
    def gen_name():
        choice = draw(st.sampled_from(['null', 'string', 'number']))
        if choice == 'null':
            return 'null'
        elif choice == 'string':
            s = draw(st.text(alphabet=st.characters(blacklist_characters=['"', '\\']), min_size=1, max_size=10))
            return json_string_literal(s)
        else:
            # number as int or float
            n = draw(st.one_of(st.integers(min_value=0, max_value=100000), st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)))
            if isinstance(n, float):
                s = ('%.10f' % n).rstrip('0').rstrip('.')
                if s == '':
                    s = '0'
                return s
            else:
                return str(n)

    # status: enum string "active", "inactive", "unknown"
    # Probes show invalid enum causes Moshi/kotlinx/Jackson reject, Gson accepts with null (Probe 5)
    # Also null status rejected by Moshi/kotlinx/Jackson, accepted by Gson (Probe 13)
    # We try valid enum, invalid enum string, and null
    def gen_status():
        choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
        if choice == 'valid':
            return draw(st.sampled_from(STATUS_VALUES))
        elif choice == 'invalid':
            # invalid enum string, e.g. "invalid", "actve", "unknown " (with space)
            invalid_str = draw(st.text(min_size=1, max_size=10).filter(lambda x: x not in ['active', 'inactive', 'unknown']))
            return json_string_literal(invalid_str)
        else:
            return 'null'

    # tags: array of strings, but probes show:
    # - all reject tags as string (Probe 6)
    # - Gson/Moshi/Jackson accept numeric elements coercing to strings; kotlinx rejects (Probe 7)
    # - Gson/Moshi/Jackson accept null elements inside tags; kotlinx rejects (Probe 14)
    # - Gson/Moshi/Jackson accept mixed-type elements coercing non-strings to strings; kotlinx rejects (Probe 15)
    # We try to produce tags as array with elements:
    # - all strings
    # - mixed strings and numbers
    # - mixed strings and null
    # - empty array
    # Also try tags as string sometimes to cause all reject (but no score)
    def gen_tags():
        # We avoid tags as string because all reject (no divergence)
        # Instead, produce array with mixed element types to cause divergence
        # Length 0 to 5
        length = draw(st.integers(min_value=0, max_value=5))
        elements = []
        for _ in range(length):
            elem_type = draw(st.sampled_from(['string', 'number', 'null']))
            if elem_type == 'string':
                s = draw(st.text(alphabet=st.characters(blacklist_characters=['"', '\\']), min_size=1, max_size=10))
                elements.append(json_string_literal(s))
            elif elem_type == 'number':
                n = draw(st.one_of(st.integers(min_value=0, max_value=100000), st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)))
                if isinstance(n, float):
                    s = ('%.10f' % n).rstrip('0').rstrip('.')
                    if s == '':
                        s = '0'
                    elements.append(s)
                else:
                    elements.append(str(n))
            else:
                elements.append('null')
        return '[' + ','.join(elements) + ']'

    # child: null or nested Record (one level recursion)
    # Probes:
    # - all accept child null (Probe 12)
    # - all accept nested child with correct types (Probe 8)
    # - all accept nested child with id as string convertible int (Probe 9)
    # - Gson accepts empty object for child filling missing fields (Probe 11), others reject
    # - Gson/Moshi accept extra unknown fields at root; kotlinx/Jackson reject (Probe 10)
    # We try to produce child as null or nested record with one field off to cause divergence
    # Also try empty object child to cause divergence
    def gen_child(depth=0):
        # To avoid deep recursion, only one level allowed
        choice = draw(st.sampled_from(['null', 'nested', 'empty']))
        if choice == 'null':
            return 'null'
        elif choice == 'empty':
            # empty object {}
            return '{}'
        else:
            # nested record with one or two fields possibly off
            # Build fields similarly to root but simpler: id, amount, name, status, tags, child=null
            # For nested child, child must be null (no deeper recursion)
            nid = gen_id()
            namount = gen_amount()
            nname = gen_name()
            nstatus = gen_status()
            ntags = gen_tags()
            # child null always for nested child
            nchild = 'null'

            # To cause divergence, randomly omit one required field (except child) or set one field off type
            # But Gson accepts extra unknown fields at root, not sure about child - safer to avoid unknown fields here
            # We try to omit one field or set one field to wrong type (e.g. tags as string)
            omit_field = draw(st.sampled_from([None, 'id', 'amount', 'name', 'status', 'tags']))
            wrong_type_field = draw(st.sampled_from([None, 'id', 'amount', 'name', 'status', 'tags']))
            # If omit_field == wrong_type_field, only omit

            fields = {}

            if omit_field != 'id':
                fields['id'] = nid
            if omit_field != 'amount':
                fields['amount'] = namount
            if omit_field != 'name':
                fields['name'] = nname
            if omit_field != 'status':
                fields['status'] = nstatus
            if omit_field != 'tags':
                fields['tags'] = ntags
            # child always present as null
            fields['child'] = nchild

            # Apply wrong type if any and not omitted
            if wrong_type_field is not None and wrong_type_field != omit_field:
                if wrong_type_field == 'id':
                    # id as string not convertible to int (e.g. "abc")
                    fields['id'] = json_string_literal('abc')
                elif wrong_type_field == 'amount':
                    # amount as boolean (invalid type)
                    fields['amount'] = 'true'
                elif wrong_type_field == 'name':
                    # name as boolean (invalid type)
                    fields['name'] = 'false'
                elif wrong_type_field == 'status':
                    # status as number (invalid type)
                    fields['status'] = '123'
                elif wrong_type_field == 'tags':
                    # tags as string (invalid type)
                    fields['tags'] = json_string_literal('not-an-array')

            # Compose JSON object string
            items = []
            for k in ['id', 'amount', 'name', 'status', 'tags', 'child']:
                if k in fields:
                    items.append(json_string_literal(k) + ':' + fields[k])
            return '{' + ','.join(items) + '}'

    # Compose root record similarly, but allow extra unknown fields to cause divergence (Probe 10)
    # Also allow empty object for child (Probe 11)
    # We try to omit one field or set one field off type to cause divergence
    omit_field = draw(st.sampled_from([None, 'id', 'amount', 'name', 'status', 'tags', 'child']))
    wrong_type_field = draw(st.sampled_from([None, 'id', 'amount', 'name', 'status', 'tags', 'child']))
    # If omit_field == wrong_type_field, only omit

    root_fields = {}

    if omit_field != 'id':
        root_fields['id'] = gen_id()
    if omit_field != 'amount':
        root_fields['amount'] = gen_amount()
    if omit_field != 'name':
        root_fields['name'] = gen_name()
    if omit_field != 'status':
        root_fields['status'] = gen_status()
    if omit_field != 'tags':
        root_fields['tags'] = gen_tags()
    if omit_field != 'child':
        root_fields['child'] = gen_child(depth=0)

    # Apply wrong type if any and not omitted
    if wrong_type_field is not None and wrong_type_field != omit_field:
        if wrong_type_field == 'id':
            # id as string not convertible to int (e.g. "abc")
            root_fields['id'] = json_string_literal('abc')
        elif wrong_type_field == 'amount':
            # amount as boolean (invalid type)
            root_fields['amount'] = 'true'
        elif wrong_type_field == 'name':
            # name as boolean (invalid type)
            root_fields['name'] = 'false'
        elif wrong_type_field == 'status':
            # status as number (invalid type)
            root_fields['status'] = '123'
        elif wrong_type_field == 'tags':
            # tags as string (invalid type)
            root_fields['tags'] = json_string_literal('not-an-array')
        elif wrong_type_field == 'child':
            # child as boolean (invalid type)
            root_fields['child'] = 'false'

    # Possibly add extra unknown fields at root to cause divergence (Probe 10)
    add_extra = draw(st.booleans())
    extra_fields = {}
    if add_extra:
        # Add 1 or 2 extra fields with arbitrary string or number values
        n_extra = draw(st.integers(min_value=1, max_value=2))
        for i in range(n_extra):
            key = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\', ':', ',', '{', '}', '[', ']'])))
            # Avoid keys that collide with known fields
            if key in root_fields or key in extra_fields:
                continue
            val_type = draw(st.sampled_from(['string', 'number', 'null']))
            if val_type == 'string':
                val = json_string_literal(draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\']))))
            elif val_type == 'number':
                n = draw(st.integers(min_value=0, max_value=100000))
                val = str(n)
            else:
                val = 'null'
            extra_fields[key] = val

    # Compose JSON object string for root
    items = []
    for k in ['id', 'amount', 'name', 'status', 'tags', 'child']:
        if k in root_fields:
            items.append(json_string_literal(k) + ':' + root_fields[k])
    for k, v in extra_fields.items():
        items.append(json_string_literal(k) + ':' + v)

    json_text = '{' + ','.join(items) + '}'
    return json_text.encode('utf-8')