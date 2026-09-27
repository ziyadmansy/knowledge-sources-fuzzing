from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and field names
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # Also include known invalid enum values to trigger divergence
    STATUS_INVALIDS = ['"invalid"', 'null', '123', '{}', '[]']

    # Helper: produce a JSON string literal with proper escaping for simple ASCII only
    def json_string(s: str) -> str:
        # Escape backslash and double quote only for simplicity
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Helper: produce a JSON array of strings, with possible coercion to ints or mixed types
    # We will produce arrays that sometimes contain integers (to trigger coercion differences)
    def gen_tags():
        # Decide if tags are well-formed or have coercion candidates
        choice = draw(st.integers(min_value=0, max_value=3))
        if choice == 0:
            # well-formed array of strings
            arr = draw(st.lists(st.text(min_size=1, max_size=10).map(json_string), min_size=0, max_size=5))
        elif choice == 1:
            # array of integers coerced to strings by some libs
            arr = draw(st.lists(st.integers(min_value=0, max_value=100).map(str), min_size=0, max_size=5))
        elif choice == 2:
            # mixed strings and integers (as JSON numbers)
            parts = []
            length = draw(st.integers(min_value=0, max_value=5))
            for _ in range(length):
                if draw(st.booleans()):
                    parts.append(draw(st.text(min_size=1, max_size=10).map(json_string)))
                else:
                    parts.append(str(draw(st.integers(min_value=0, max_value=100))))
            arr = parts
        else:
            # empty array
            arr = []
        return '[' + ','.join(arr) + ']'

    # Helper: produce "amount" field as string or numeric JSON value (to trigger coercion differences)
    def gen_amount():
        choice = draw(st.integers(min_value=0, max_value=2))
        if choice == 0:
            # string numeric
            val = draw(st.integers(min_value=0, max_value=100000))
            return json_string(str(val))
        elif choice == 1:
            # numeric JSON value (int or float)
            if draw(st.booleans()):
                val = draw(st.integers(min_value=0, max_value=100000))
                return str(val)
            else:
                val = draw(st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False))
                # Format float with minimal decimals
                return repr(val)
        else:
            # string non-numeric (to test rejection)
            s = draw(st.text(min_size=1, max_size=10).filter(lambda x: not x.isdigit()))
            return json_string(s)

    # Helper: produce "id" field as integer or string integer (all libs accept string integers)
    def gen_id():
        if draw(st.booleans()):
            return str(draw(st.integers(min_value=0, max_value=100000)))
        else:
            return json_string(str(draw(st.integers(min_value=0, max_value=100000))))

    # Helper: produce "name" field as string or null or missing (but missing is not allowed per schema)
    def gen_name():
        choice = draw(st.integers(min_value=0, max_value=2))
        if choice == 0:
            # string
            return json_string(draw(st.text(min_size=0, max_size=20)))
        elif choice == 1:
            # null
            return 'null'
        else:
            # empty string (valid string)
            return '""'

    # Helper: produce "status" field with known enum, null, unknown, or invalid values
    def gen_status():
        choice = draw(st.integers(min_value=0, max_value=5))
        if choice == 0:
            # valid enum string
            return draw(st.sampled_from(STATUS_VALUES))
        elif choice == 1:
            # null (only Gson accepts)
            return 'null'
        elif choice == 2:
            # unknown enum string (invalid)
            return draw(st.sampled_from(STATUS_INVALIDS))
        elif choice == 3:
            # number (invalid type)
            return str(draw(st.integers(min_value=0, max_value=10)))
        else:
            # empty string (invalid enum)
            return '""'

    # Helper: produce "child" field as null, empty object, or nested record (one level recursion max)
    def gen_child(depth=0):
        choice = draw(st.integers(min_value=0, max_value=3))
        if choice == 0:
            # null child
            return 'null'
        elif choice == 1:
            # empty object (Gson accepts, others reject)
            return '{}'
        elif choice == 2 and depth == 0:
            # nested record (one level only)
            return gen_record(depth=1)
        else:
            # null fallback
            return 'null'

    # Helper: produce a record JSON object string with fields in random order
    def gen_record(depth=0):
        # Compose fields as key:value strings
        id_field = '"id":' + gen_id()
        amount_field = '"amount":' + gen_amount()
        name_field = '"name":' + gen_name()
        status_field = '"status":' + gen_status()
        tags_field = '"tags":' + gen_tags()
        child_field = '"child":' + gen_child(depth)

        fields = [id_field, amount_field, name_field, status_field, tags_field, child_field]

        # Possibly add one extra unknown field to trigger divergence (Gson and Moshi accept, others reject)
        if draw(st.booleans()):
            extra_key = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['id','amount','name','status','tags','child']))
            extra_val_type = draw(st.integers(min_value=0, max_value=2))
            if extra_val_type == 0:
                extra_val = json_string(draw(st.text(min_size=0, max_size=10)))
            elif extra_val_type == 1:
                extra_val = str(draw(st.integers(min_value=0, max_value=1000)))
            else:
                extra_val = 'null'
            fields.append(json_string(extra_key) + ':' + extra_val)

        # Shuffle fields order to avoid positional bias
        fields = draw(st.permutations(fields))

        return '{' + ','.join(fields) + '}'

    # Generate top-level record
    record = gen_record(depth=0)

    # Return as bytes
    return record.encode('utf-8')