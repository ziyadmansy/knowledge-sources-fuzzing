from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and recursion limit
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    MAX_DEPTH = 1

    # Helper: produce JSON string for a string value or null
    def json_string_or_null():
        # Sometimes null, sometimes string (including empty)
        return draw(st.one_of(st.just("null"), st.text(min_size=0, max_size=20).map(lambda s: '"' + s.replace('"', '\\"') + '"')))

    # Helper: produce JSON string for "amount" field (string)
    # We want to test type coercion: sometimes produce a number instead of string
    def json_amount():
        # 70% string, 30% number (int or float)
        choice = draw(st.floats(min_value=0, max_value=1))
        if choice < 0.7:
            s = draw(st.text(min_size=0, max_size=20))
            return '"' + s.replace('"', '\\"') + '"'
        else:
            # number as int or float, positive or zero
            n = draw(st.one_of(st.integers(min_value=0, max_value=1000000), st.floats(min_value=0, max_value=1e6)))
            # Format number without trailing .0 if int
            if isinstance(n, float) and n.is_integer():
                n = int(n)
            return str(n)

    # Helper: produce JSON string for "id" field (integer)
    # Sometimes null to test null handling
    def json_id():
        # 80% integer, 20% null
        if draw(st.floats(min_value=0, max_value=1)) < 0.8:
            return str(draw(st.integers(min_value=0, max_value=1_000_000)))
        else:
            return "null"

    # Helper: produce JSON string for "status" enum
    # Sometimes invalid enum to test rejection
    def json_status():
        p = draw(st.floats(min_value=0, max_value=1))
        if p < 0.75:
            # valid enum, but sometimes case variant or unknown string to test rejection
            base = draw(st.sampled_from(STATUS_VALUES))
            # 10% chance to uppercase or mixed case to test case sensitivity
            if draw(st.floats(min_value=0, max_value=1)) < 0.1:
                base_val = base.strip('"')
                # random case variant
                variant = ''.join(c.upper() if draw(st.booleans()) else c.lower() for c in base_val)
                return '"' + variant + '"'
            else:
                return base
        else:
            # invalid enum string or null
            invalids = ['"invalid"', '"Active"', '"INACTIVE"', '"unknowns"', 'null']
            return draw(st.sampled_from(invalids))

    # Helper: produce JSON string for "tags" array of strings or null
    # Null tests null array acceptance/rejection
    def json_tags():
        p = draw(st.floats(min_value=0, max_value=1))
        if p < 0.7:
            # array of strings, length 0..5
            arr_len = draw(st.integers(min_value=0, max_value=5))
            elems = []
            for _ in range(arr_len):
                s = draw(st.text(min_size=0, max_size=20))
                elems.append('"' + s.replace('"', '\\"') + '"')
            return "[" + ",".join(elems) + "]"
        elif p < 0.85:
            # null array
            return "null"
        else:
            # empty array (edge case)
            return "[]"

    # Helper: produce JSON string for "name" field (string or null)
    def json_name():
        return json_string_or_null()

    # Compose a record JSON string with bounded recursion depth
    def json_record(depth=0):
        # Decide if we omit fields (to test missing fields)
        # Moshi and kotlinx reject missing required fields, Gson and Jackson accept
        # We'll omit at most one field per record to maximize divergence
        omit_field = draw(st.sampled_from([None, "id", "amount", "name", "status", "tags", "child"]))
        # Compose fields, omitting one if chosen
        fields = []

        # id field
        if omit_field != "id":
            fields.append('"id":' + json_id())
        # amount field
        if omit_field != "amount":
            fields.append('"amount":' + json_amount())
        # name field
        if omit_field != "name":
            fields.append('"name":' + json_name())
        # status field
        if omit_field != "status":
            fields.append('"status":' + json_status())
        # tags field
        if omit_field != "tags":
            fields.append('"tags":' + json_tags())
        # child field
        if omit_field != "child":
            # child is either null or a nested record (one level recursion)
            if depth < MAX_DEPTH:
                # 50% chance null, 50% nested record
                if draw(st.booleans()):
                    fields.append('"child":null')
                else:
                    fields.append('"child":' + json_record(depth + 1))
            else:
                # max depth reached, child null
                fields.append('"child":null')

        # Shuffle fields to vary order (duplicate keys handled below)
        draw(st.randoms()).shuffle(fields)

        # Possibly add one duplicate key with different value to test last-key-wins
        # 30% chance to add a duplicate key for one of the existing keys
        if draw(st.floats(min_value=0, max_value=1)) < 0.3 and len(fields) > 0:
            dup_key_field = draw(st.sampled_from(fields))
            # Extract key name from '"key":value'
            key_name = dup_key_field.split(":", 1)[0]
            # Generate a different value for that key
            # We reuse the key name to generate a plausible value
            def dup_value_for_key(k):
                if k == '"id"':
                    return json_id()
                elif k == '"amount"':
                    return json_amount()
                elif k == '"name"':
                    return json_name()
                elif k == '"status"':
                    return json_status()
                elif k == '"tags"':
                    return json_tags()
                elif k == '"child"':
                    if depth < MAX_DEPTH:
                        if draw(st.booleans()):
                            return "null"
                        else:
                            return json_record(depth + 1)
                    else:
                        return "null"
                else:
                    # fallback string
                    return '"dup"'

            dup_value = dup_value_for_key(key_name)
            fields.append(key_name + ":" + dup_value)

        # Possibly add one extra unknown key to test unknown key acceptance/rejection
        # 20% chance to add an unknown key
        if draw(st.floats(min_value=0, max_value=1)) < 0.2:
            # unknown key name: random ascii letters, length 3..10
            unk_key = draw(st.text(min_size=3, max_size=10, alphabet=st.characters(whitelist_categories=('Ll','Lu'))))
            # unknown key value: string or number or null
            unk_val = draw(st.one_of(
                st.text(min_size=0, max_size=20).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
                st.integers(min_value=0, max_value=1000).map(str),
                st.just("null")
            ))
            fields.append('"' + unk_key + '":' + unk_val)

        # Join fields with commas
        return "{" + ",".join(fields) + "}"

    # Generate top-level record JSON string
    json_text = json_record(0)

    # Return as bytes
    return json_text.encode("utf-8")