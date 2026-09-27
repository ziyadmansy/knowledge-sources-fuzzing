from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # We allow null for name and child always, but status null only for Gson (to provoke divergence)
    # We allow id as number or string number
    # amount as string or number (kotlinx rejects number)
    # name as string, null, or number (kotlinx rejects number)
    # status as enum string, unknown string (Gson accepts unknown as null), or null (Gson accepts null)
    # tags as array of strings normally, but can include non-string or null elements (kotlinx rejects non-string)
    # child as null or nested record, or empty object {} (Gson accepts empty object child, others reject)
    # unknown extra fields at top level or nested (Gson, Moshi accept; kotlinx, Jackson reject)
    # duplicate keys: last wins for all

    # Helpers to produce JSON text for fields

    def json_string_or_number_for_id():
        # id: integer as number or string number
        id_int = draw(st.integers(min_value=0, max_value=10**6))
        as_number = draw(st.booleans())
        if as_number:
            return str(id_int)
        else:
            return '"' + str(id_int) + '"'

    def json_string_or_number_for_amount():
        # amount: string or number (kotlinx rejects number)
        # amount is string representing a decimal number, or number
        # We produce a decimal string or a number (int or float)
        as_number = draw(st.booleans())
        if as_number:
            # number: int or float
            is_float = draw(st.booleans())
            if is_float:
                # float with 2 decimals
                val = draw(st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False))
                # format with 2 decimals, no exponent
                s = f"{val:.2f}"
                # remove trailing zeros and dot if integer
                if '.' in s:
                    s = s.rstrip('0').rstrip('.')
                return s
            else:
                val = draw(st.integers(min_value=0, max_value=10**6))
                return str(val)
        else:
            # string decimal, possibly with leading zeros or decimal point
            # produce string that looks like a number but as string
            integral = draw(st.integers(min_value=0, max_value=10**6))
            fractional = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=99)))
            s = str(integral)
            if fractional is not None:
                s += '.' + f"{fractional:02d}"
            # maybe add leading zeros
            leading_zeros = draw(st.integers(min_value=0, max_value=3))
            s = '0'*leading_zeros + s
            return '"' + s + '"'

    def json_string_or_null_or_number_for_name():
        # name: string or null or number (kotlinx rejects number)
        choice = draw(st.sampled_from(['string', 'null', 'number']))
        if choice == 'string':
            # string or empty string
            s = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            if s is None:
                return 'null'
            else:
                # escape quotes and backslashes minimally
                s_esc = s.replace('\\', '\\\\').replace('"', '\\"')
                return '"' + s_esc + '"'
        elif choice == 'null':
            return 'null'
        else:
            # number as int or float
            is_float = draw(st.booleans())
            if is_float:
                val = draw(st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False))
                s = f"{val:.2f}"
                if '.' in s:
                    s = s.rstrip('0').rstrip('.')
                return s
            else:
                val = draw(st.integers(min_value=-1000, max_value=1000))
                return str(val)

    def json_status():
        # status: one of "active", "inactive", "unknown", unknown string, or null
        # Gson accepts unknown string as null, Moshi/kotlinx/Jackson reject unknown string
        # Gson accepts null, others reject null
        choice = draw(st.sampled_from(['valid', 'unknown_string', 'null']))
        if choice == 'valid':
            return draw(st.sampled_from(STATUS_VALUES))
        elif choice == 'unknown_string':
            # produce a string not in valid set
            # simple fixed unknown string
            return '"invalid_status"'
        else:
            return 'null'

    def json_tags():
        # tags: array of strings normally
        # but can include non-string or null elements (kotlinx rejects non-string)
        # or non-array (all reject non-array)
        # We produce mostly array, sometimes non-array to provoke rejection divergence
        is_array = draw(st.booleans())
        if not is_array:
            # produce a non-array value for tags: string, number, null, object, boolean
            choice = draw(st.sampled_from(['string', 'number', 'null', 'object', 'bool']))
            if choice == 'string':
                s = draw(st.text(min_size=0, max_size=10))
                s_esc = s.replace('\\', '\\\\').replace('"', '\\"')
                return '"' + s_esc + '"'
            elif choice == 'number':
                val = draw(st.integers(min_value=0, max_value=100))
                return str(val)
            elif choice == 'null':
                return 'null'
            elif choice == 'object':
                # empty object
                return '{}'
            else:
                # boolean
                return draw(st.sampled_from(['true', 'false']))
        else:
            # array of elements: mostly strings, sometimes non-string or null
            length = draw(st.integers(min_value=0, max_value=5))
            elements = []
            for _ in range(length):
                # element type: string, null, number, bool, object
                elem_type = draw(st.sampled_from(['string', 'null', 'number', 'bool', 'object']))
                if elem_type == 'string':
                    s = draw(st.text(min_size=0, max_size=10))
                    s_esc = s.replace('\\', '\\\\').replace('"', '\\"')
                    elements.append('"' + s_esc + '"')
                elif elem_type == 'null':
                    elements.append('null')
                elif elem_type == 'number':
                    val = draw(st.integers(min_value=0, max_value=100))
                    elements.append(str(val))
                elif elem_type == 'bool':
                    elements.append(draw(st.sampled_from(['true', 'false'])))
                else:
                    # object: empty object only to keep complexity low
                    elements.append('{}')
            return '[' + ','.join(elements) + ']'

    # Recursive child record generator with bounded depth
    def json_child(depth):
        # child: null or nested record or empty object (Gson accepts empty object)
        choice = draw(st.sampled_from(['null', 'record', 'empty_object']))
        if depth <= 0:
            # no recursion deeper than 1 level
            if choice == 'record':
                choice = 'null'  # force no deeper recursion
        if choice == 'null':
            return 'null'
        elif choice == 'empty_object':
            return '{}'
        else:
            # nested record, depth-1
            return json_record(depth - 1)

    # Unknown extra fields: Gson and Moshi accept, kotlinx and Jackson reject
    # We add zero or one unknown extra field at top level or nested
    def unknown_extra_field():
        # key: simple string not in known keys
        key = '"extra_field"'
        # value: string or number or null
        val_type = draw(st.sampled_from(['string', 'number', 'null']))
        if val_type == 'string':
            s = draw(st.text(min_size=0, max_size=10))
            s_esc = s.replace('\\', '\\\\').replace('"', '\\"')
            val = '"' + s_esc + '"'
        elif val_type == 'number':
            val = str(draw(st.integers(min_value=0, max_value=1000)))
        else:
            val = 'null'
        return f'{key}:{val}'

    def json_record(depth):
        # Compose fields in order, but allow duplicate keys by repeating keys with different values
        # We produce a list of (key, value) pairs as strings, then join with commas

        # Known keys: id, amount, name, status, tags, child
        # We produce 6 fields, each once, but sometimes duplicate one key once with different value (to provoke duplicate keys)
        # We produce unknown extra field sometimes

        # Produce each field value
        id_val = json_string_or_number_for_id()
        amount_val = json_string_or_number_for_amount()
        name_val = json_string_or_null_or_number_for_name()
        status_val = json_status()
        tags_val = json_tags()
        child_val = json_child(depth)

        fields = [
            ('"id"', id_val),
            ('"amount"', amount_val),
            ('"name"', name_val),
            ('"status"', status_val),
            ('"tags"', tags_val),
            ('"child"', child_val),
        ]

        # Possibly add unknown extra field at this level (only once)
        add_unknown = draw(st.booleans())
        if add_unknown:
            fields.append(unknown_extra_field().split(':', 1))  # split into key, value

        # Possibly add duplicate key for one of the known keys (last wins)
        add_dup = draw(st.booleans())
        if add_dup:
            dup_key, _ = draw(st.sampled_from(fields[:6]))  # only known keys
            # produce a different value for the duplicate key
            if dup_key == '"id"':
                dup_val = json_string_or_number_for_id()
            elif dup_key == '"amount"':
                dup_val = json_string_or_number_for_amount()
            elif dup_key == '"name"':
                dup_val = json_string_or_null_or_number_for_name()
            elif dup_key == '"status"':
                dup_val = json_status()
            elif dup_key == '"tags"':
                dup_val = json_tags()
            else:  # child
                dup_val = json_child(depth)
            fields.append((dup_key, dup_val))

        # Shuffle fields order to vary order (duplicate keys last appended)
        # But keep duplicate keys last to ensure last wins behavior is tested
        known_fields = fields[:6]
        extra_fields = fields[6:-1] if add_dup else fields[6:]
        dup_field = fields[-1:] if add_dup else []

        # Shuffle known fields and extra fields independently
        known_fields = draw(st.permutations(known_fields))
        extra_fields = draw(st.permutations(extra_fields))

        all_fields = list(known_fields) + list(extra_fields) + list(dup_field)

        # Compose JSON object text
        json_fields_text = ','.join(f'{k}:{v}' for k, v in all_fields)
        return '{' + json_fields_text + '}'

    # Generate top-level record with depth 1 recursion max
    json_text = json_record(depth=1)
    return json_text.encode('utf-8')