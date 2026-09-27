from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # We will produce JSON text as str, then encode to bytes at the end.

    # Helper: produce a JSON string literal from a Python string (no escapes needed here, safe ascii)
    def json_str(s: str) -> str:
        # Minimal escaping for quotes and backslash
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # id: integer normally, but sometimes string (to test type mismatch)
    # But type mismatches are rejected by all, so only produce int or omit to test missing
    # We'll mostly produce int, sometimes omit to test missing field
    id_field_present = draw(st.booleans())
    if id_field_present:
        id_val = draw(st.integers(min_value=0, max_value=10**9))
        id_json = f'"id":{id_val}'
    else:
        id_json = None

    # amount: string normally, sometimes number (rejected by all)
    # We'll produce string normally, sometimes omit to test missing
    amount_field_present = draw(st.booleans())
    if amount_field_present:
        # amount string: decimal string, sometimes empty string, sometimes "0", sometimes large number string
        amount_val = draw(st.one_of(
            st.text(min_size=1, max_size=10, alphabet='0123456789.'),
            st.just("0"),
            st.just(""),
            st.text(min_size=1, max_size=5, alphabet='0123456789')
        ))
        # To avoid invalid JSON number, always quote amount_val
        amount_json = f'"amount":{json_str(amount_val)}'
    else:
        amount_json = None

    # name: string or null normally, sometimes number (rejected by all)
    # We'll produce string or null or omit to test missing
    name_field_present = draw(st.booleans())
    if name_field_present:
        name_val = draw(st.one_of(
            st.none(),
            st.text(min_size=0, max_size=10, alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '),
        ))
        if name_val is None:
            name_json = '"name":null'
        else:
            name_json = f'"name":{json_str(name_val)}'
    else:
        name_json = None

    # status: enum string normally, sometimes invalid enum string (rejected by all)
    # We'll produce valid enum or omit to test missing
    status_field_present = draw(st.booleans())
    if status_field_present:
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_json = f'"status":{status_val}'
    else:
        status_json = None

    # tags: array of strings normally, sometimes empty array, sometimes omit to test missing
    tags_field_present = draw(st.booleans())
    if tags_field_present:
        # tags array: length 0 to 3, strings ascii letters only
        tags_len = draw(st.integers(min_value=0, max_value=3))
        tags_elems = []
        for _ in range(tags_len):
            tag = draw(st.text(min_size=1, max_size=5, alphabet='abcdefghijklmnopqrstuvwxyz'))
            tags_elems.append(json_str(tag))
        tags_json = f'"tags":[{",".join(tags_elems)}]'
    else:
        tags_json = None

    # child: null or nested record (one level only), sometimes omit to test missing
    child_field_present = draw(st.booleans())
    if child_field_present:
        # child null or nested record
        child_is_null = draw(st.booleans())
        if child_is_null:
            child_json = '"child":null'
        else:
            # nested record: all fields present and valid (to avoid rejection)
            # id int
            child_id = draw(st.integers(min_value=0, max_value=10**9))
            # amount string
            child_amount = draw(st.text(min_size=1, max_size=10, alphabet='0123456789.'))
            # name string or null
            child_name = draw(st.one_of(
                st.none(),
                st.text(min_size=0, max_size=10, alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ')
            ))
            # status enum
            child_status = draw(st.sampled_from(STATUS_VALUES))
            # tags array of strings
            child_tags_len = draw(st.integers(min_value=0, max_value=3))
            child_tags_elems = []
            for _ in range(child_tags_len):
                t = draw(st.text(min_size=1, max_size=5, alphabet='abcdefghijklmnopqrstuvwxyz'))
                child_tags_elems.append(json_str(t))
            # child.child must be null (no deeper recursion)
            child_child_json = '"child":null'

            child_name_json = '"name":null' if child_name is None else f'"name":{json_str(child_name)}'

            child_json = (
                '"child":{'
                f'"id":{child_id},'
                f'"amount":{json_str(child_amount)},'
                f'{child_name_json},'
                f'"status":{child_status},'
                f'"tags":[{",".join(child_tags_elems)}],'
                f'{child_child_json}'
                '}'
            )
    else:
        child_json = None

    # Compose fields list, always include all fields except those omitted
    fields = [f for f in [id_json, amount_json, name_json, status_json, tags_json, child_json] if f is not None]

    # To induce subtle disagreements, randomly duplicate one field with a different value
    # Duplicate keys: last occurrence wins, all implementations accept last occurrence wins
    # But we can try to duplicate with different types or values to see if any implementation fails or decodes differently
    do_duplicate = draw(st.booleans())
    if do_duplicate and fields:
        # Pick a field to duplicate
        dup_index = draw(st.integers(min_value=0, max_value=len(fields)-1))
        original_field = fields[dup_index]
        # Parse field name from original_field: it's always "key":...
        key_end = original_field.find(':')
        key = original_field[0:key_end]
        # Generate a conflicting value for the duplicate key
        # For id: original is int, duplicate string or omit
        # For amount: original string, duplicate number or different string
        # For name: original string or null, duplicate null or string or number (number rejected by all)
        # For status: original enum string, duplicate invalid enum string or valid enum string different
        # For tags: original array of strings, duplicate empty array or array with null (rejected by all)
        # For child: original nested or null, duplicate null or nested with missing fields (rejected by all)
        # We'll try to produce a duplicate that is valid JSON but may cause divergence

        def make_duplicate_value(field_key):
            if field_key == '"id"':
                # original int, duplicate string or int different
                choice = draw(st.sampled_from(['string', 'int']))
                if choice == 'string':
                    val = draw(st.text(min_size=1, max_size=5, alphabet='0123456789'))
                    return f'{key}:{json_str(val)}'
                else:
                    val = draw(st.integers(min_value=0, max_value=10**9))
                    # ensure different from original if possible
                    return f'{key}:{val}'
            elif field_key == '"amount"':
                # original string, duplicate number or different string
                choice = draw(st.sampled_from(['number', 'string']))
                if choice == 'number':
                    val = draw(st.integers(min_value=0, max_value=10**9))
                    return f'{key}:{val}'
                else:
                    val = draw(st.text(min_size=1, max_size=10, alphabet='0123456789.'))
                    return f'{key}:{json_str(val)}'
            elif field_key == '"name"':
                # original string or null, duplicate null or string or number
                choice = draw(st.sampled_from(['null', 'string', 'number']))
                if choice == 'null':
                    return f'{key}:null'
                elif choice == 'string':
                    val = draw(st.text(min_size=1, max_size=10, alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'))
                    return f'{key}:{json_str(val)}'
                else:
                    # number (rejected by all)
                    val = draw(st.integers(min_value=0, max_value=1000))
                    return f'{key}:{val}'
            elif field_key == '"status"':
                # original enum string, duplicate invalid enum string or different valid enum string
                choice = draw(st.sampled_from(['invalid', 'valid']))
                if choice == 'invalid':
                    # invalid enum string
                    val = draw(st.text(min_size=3, max_size=8, alphabet='abcdefghijklmnopqrstuvwxyz')).lower()
                    # ensure not in STATUS_VALUES
                    while f'"{val}"' in STATUS_VALUES:
                        val = draw(st.text(min_size=3, max_size=8, alphabet='abcdefghijklmnopqrstuvwxyz')).lower()
                    return f'{key}:"{val}"'
                else:
                    # different valid enum string
                    orig_val = original_field[key_end+1:].strip()
                    # pick different from original
                    candidates = [v for v in STATUS_VALUES if v != orig_val]
                    if not candidates:
                        val = STATUS_VALUES[0]
                    else:
                        val = draw(st.sampled_from(candidates))
                    return f'{key}:{val}'
            elif field_key == '"tags"':
                # original array of strings, duplicate empty array or array with null (rejected by all)
                choice = draw(st.sampled_from(['empty', 'null_elem']))
                if choice == 'empty':
                    return f'{key}:[]'
                else:
                    return f'{key}:[null]'
            elif field_key == '"child"':
                # original nested or null, duplicate null or nested with missing fields (rejected by all)
                choice = draw(st.sampled_from(['null', 'missing_fields']))
                if choice == 'null':
                    return f'{key}:null'
                else:
                    # nested with missing fields: only "id" present
                    child_id = draw(st.integers(min_value=0, max_value=10**9))
                    return f'{key}:{{"id":{child_id}}}'
            else:
                # fallback: duplicate same field as original
                return original_field

        dup_field = make_duplicate_value(key)
        # Insert duplicate field after original field (so last occurrence wins)
        fields.insert(dup_index + 1, dup_field)

    # Compose JSON object text
    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')