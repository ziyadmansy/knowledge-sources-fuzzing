from hypothesis import strategies as st

# Constants for enum values
STATUS_VALUES = ['active', 'inactive', 'unknown']

# Helper to produce JSON string literal with proper escaping for " and \ only (minimal)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote only (minimal JSON escaping)
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations designed to trigger behavioral divergence among four Dart JSON
    deserializers (manual, json_serializable, freezed, built_value).

    Strategy:
    - Produce mostly well-formed documents with exactly all six fields present.
    - Vary one or two fields per document around known edge cases:
      * "id": int normally, but sometimes float or exponent form (to trigger truncation or rejection).
      * "amount": string normally, but sometimes numeric string with fractional or exponent form.
      * "name": string or null, always present.
      * "status": one of enum strings, but sometimes invalid casing or unknown string (to cause rejection).
      * "tags": array of strings normally, but sometimes null or missing (built_value accepts null or missing).
      * "child": null or nested record (one level), sometimes missing (to test rejection).
    - Use duplicate keys with last key winning occasionally.
    - Use extra unknown keys occasionally (ignored by all).
    - Use numeric strings for "amount" to test subtle differences.
    - Use float or exponent for "id" to test truncation differences.
    - Use missing or null "tags" to test built_value acceptance divergence.
    - Use missing or null "child" to test rejection divergence.
    """

    # --- Helpers for fields ---

    # id: mostly int, sometimes float or exponent string (as JSON number)
    id_type = draw(st.sampled_from(['int', 'float', 'exponent']))
    if id_type == 'int':
        # 32-bit and 64-bit range integers
        id_val = draw(st.integers(min_value=-(2**40), max_value=2**40))
        id_json = str(id_val)
    elif id_type == 'float':
        # float with fractional part, e.g. 1234.0 or 1234.56
        base = draw(st.integers(min_value=-(2**20), max_value=2**20))
        frac = draw(st.floats(min_value=0.1, max_value=0.9999))
        val = base + frac
        # Format as JSON number with decimal point, no exponent
        id_json = ("%.4f" % val).rstrip('0').rstrip('.')
        if id_json == '':
            id_json = '0'
    else:  # exponent
        # exponent form like 1e3 or -2e4
        base = draw(st.integers(min_value=1, max_value=9999))
        exp = draw(st.integers(min_value=-10, max_value=10))
        sign = '' if draw(st.booleans()) else '-'
        id_json = f"{sign}{base}e{exp}"

    # amount: string, numeric string normally, sometimes invalid string to test rejection
    amount_type = draw(st.sampled_from(['numeric_string', 'fractional_string', 'non_numeric_string']))
    if amount_type == 'numeric_string':
        # integer string
        amount_val = draw(st.integers(min_value=-(10**12), max_value=10**12))
        amount_str = str(amount_val)
    elif amount_type == 'fractional_string':
        # fractional numeric string
        whole = draw(st.integers(min_value=-(10**6), max_value=10**6))
        frac = draw(st.integers(min_value=1, max_value=9999))
        amount_str = f"{whole}.{frac}"
    else:
        # non-numeric string but valid JSON string
        amount_str = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES and s != 'null'))

    amount_json = json_string_literal(amount_str)

    # name: string or null, always present
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        # non-empty string, avoid reserved words or enum values
        name_val = draw(st.text(min_size=1, max_size=20).filter(lambda s: s not in STATUS_VALUES))
        name_json = json_string_literal(name_val)

    # status: mostly valid enum, sometimes invalid casing or unknown string
    status_variant = draw(st.sampled_from(['valid', 'invalid_case', 'unknown_value']))
    if status_variant == 'valid':
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_json = json_string_literal(status_val)
    elif status_variant == 'invalid_case':
        # upper case or mixed case variant of valid enum
        base = draw(st.sampled_from(STATUS_VALUES))
        # upper or capitalize
        if draw(st.booleans()):
            status_val = base.upper()
        else:
            status_val = base.capitalize()
        status_json = json_string_literal(status_val)
    else:
        # unknown string not in enum
        status_val = draw(st.text(min_size=3, max_size=10).filter(lambda s: s not in STATUS_VALUES and s.lower() not in STATUS_VALUES))
        status_json = json_string_literal(status_val)

    # tags: array of strings normally, sometimes null or missing (built_value accepts null or missing)
    tags_variant = draw(st.sampled_from(['normal', 'null', 'missing']))
    if tags_variant == 'normal':
        # array of 0-3 strings
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10), max_size=3))
        tags_json = "[" + ",".join(json_string_literal(t) for t in tags_list) + "]"
        tags_present = True
    elif tags_variant == 'null':
        tags_json = "null"
        tags_present = True
    else:
        # missing tags field
        tags_json = None
        tags_present = False

    # child: null or nested record or missing
    child_variant = draw(st.sampled_from(['normal', 'null', 'missing']))
    if child_variant == 'normal':
        # nested record, one level, well-formed but with simpler fixed values to keep size small
        # Use mostly valid values to avoid broad rejection
        child_id = draw(st.integers(min_value=0, max_value=1000))
        child_amount = json_string_literal("123.45")
        child_name = json_string_literal("childname")
        child_status = json_string_literal("active")
        child_tags = '[]'
        child_child = "null"
        child_json = (
            '{'
            f'"id":{child_id},'
            f'"amount":{child_amount},'
            f'"name":{child_name},'
            f'"status":{child_status},'
            f'"tags":{child_tags},'
            f'"child":{child_child}'
            '}'
        )
        child_present = True
    elif child_variant == 'null':
        child_json = "null"
        child_present = True
    else:
        # missing child field
        child_json = None
        child_present = False

    # id, amount, name, status are always present
    # tags and child may be missing

    # Compose fields as list of (key,json_value) tuples
    fields = [
        ("id", id_json),
        ("amount", amount_json),
        ("name", name_json),
        ("status", status_json),
    ]
    if tags_present:
        fields.append(("tags", tags_json))
    if child_present:
        fields.append(("child", child_json))

    # Possibly add extra unknown keys (ignored by all)
    add_extra_keys = draw(st.booleans())
    if add_extra_keys:
        # 1 or 2 extra keys with simple string or number values
        extra_keys_count = draw(st.integers(min_value=1, max_value=2))
        for i in range(extra_keys_count):
            key = f"extra{i}"
            # value: string or number
            if draw(st.booleans()):
                val = json_string_literal(draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['id','amount','name','status','tags','child'])))
            else:
                val = str(draw(st.integers(min_value=-1000, max_value=1000)))
            fields.append((key, val))

    # Possibly add duplicate keys for one field (last key wins)
    add_duplicate = draw(st.booleans())
    if add_duplicate:
        # Choose one field to duplicate among present fields
        dup_field = draw(st.sampled_from([k for k, v in fields]))
        # Generate a second value for that field, subtly different
        if dup_field == "id":
            # duplicate id with different numeric form
            dup_id_type = draw(st.sampled_from(['int', 'float', 'exponent']))
            if dup_id_type == 'int':
                dup_val = draw(st.integers(min_value=-(2**40), max_value=2**40))
                dup_json = str(dup_val)
            elif dup_id_type == 'float':
                base = draw(st.integers(min_value=-(2**20), max_value=2**20))
                frac = draw(st.floats(min_value=0.1, max_value=0.9999))
                val = base + frac
                dup_json = ("%.4f" % val).rstrip('0').rstrip('.')
                if dup_json == '':
                    dup_json = '0'
            else:
                base = draw(st.integers(min_value=1, max_value=9999))
                exp = draw(st.integers(min_value=-10, max_value=10))
                sign = '' if draw(st.booleans()) else '-'
                dup_json = f"{sign}{base}e{exp}"
            fields.append((dup_field, dup_json))
        elif dup_field == "amount":
            # duplicate amount with different numeric string or non-numeric string
            dup_amount_type = draw(st.sampled_from(['numeric_string', 'fractional_string', 'non_numeric_string']))
            if dup_amount_type == 'numeric_string':
                dup_val = draw(st.integers(min_value=-(10**12), max_value=10**12))
                dup_json = json_string_literal(str(dup_val))
            elif dup_amount_type == 'fractional_string':
                whole = draw(st.integers(min_value=-(10**6), max_value=10**6))
                frac = draw(st.integers(min_value=1, max_value=9999))
                dup_json = json_string_literal(f"{whole}.{frac}")
            else:
                dup_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES and s != 'null'))
                dup_json = json_string_literal(dup_val)
            fields.append((dup_field, dup_json))
        elif dup_field == "name":
            # duplicate name with null or different string
            if draw(st.booleans()):
                dup_json = "null"
            else:
                dup_val = draw(st.text(min_size=1, max_size=20).filter(lambda s: s not in STATUS_VALUES))
                dup_json = json_string_literal(dup_val)
            fields.append((dup_field, dup_json))
        elif dup_field == "status":
            # duplicate status with valid or invalid enum variant
            dup_status_variant = draw(st.sampled_from(['valid', 'invalid_case', 'unknown_value']))
            if dup_status_variant == 'valid':
                dup_val = draw(st.sampled_from(STATUS_VALUES))
                dup_json = json_string_literal(dup_val)
            elif dup_status_variant == 'invalid_case':
                base = draw(st.sampled_from(STATUS_VALUES))
                if draw(st.booleans()):
                    dup_val = base.upper()
                else:
                    dup_val = base.capitalize()
                dup_json = json_string_literal(dup_val)
            else:
                dup_val = draw(st.text(min_size=3, max_size=10).filter(lambda s: s not in STATUS_VALUES and s.lower() not in STATUS_VALUES))
                dup_json = json_string_literal(dup_val)
            fields.append((dup_field, dup_json))
        elif dup_field == "tags":
            # duplicate tags with normal array or null
            if draw(st.booleans()):
                dup_tags_list = draw(st.lists(st.text(min_size=1, max_size=10), max_size=3))
                dup_json = "[" + ",".join(json_string_literal(t) for t in dup_tags_list) + "]"
            else:
                dup_json = "null"
            fields.append((dup_field, dup_json))
        elif dup_field == "child":
            # duplicate child with null or nested record
            if draw(st.booleans()):
                dup_json = "null"
            else:
                # nested record with fixed values
                dup_json = (
                    '{'
                    '"id":1,'
                    '"amount":"0.0",'
                    '"name":"dupchild",'
                    '"status":"inactive",'
                    '"tags":[],'
                    '"child":null'
                    '}'
                )
            fields.append((dup_field, dup_json))

    # Compose JSON object text with fields in order, duplicates last
    json_parts = []
    json_parts.append('{')
    first = True
    for k, v in fields:
        if not first:
            json_parts.append(',')
        first = False
        json_parts.append(json_string_literal(k))
        json_parts.append(':')
        json_parts.append(v)
    json_parts.append('}')

    json_text = ''.join(json_parts)
    return json_text.encode('utf-8')