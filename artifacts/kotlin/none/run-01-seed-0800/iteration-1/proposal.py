from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper: generate a JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Escape backslash and double quote for JSON string
        s_escaped = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s_escaped}"'

    # Helper: generate a JSON array of strings
    def json_string_array(strings):
        return '[' + ','.join(json_string(s) for s in strings) + ']'

    # Recursive generator for a Record JSON text, with bounded recursion depth
    def gen_record(depth):
        # To induce divergence, we vary one or two fields slightly off from spec,
        # or use borderline values, or null vs missing, or type variants.

        # Decide if this record is null (only allowed at child)
        if depth > 1:
            # At max depth, child must be null or omitted, but we always include child field
            child_json = "null"
        else:
            # 20% chance child is null, 80% chance child is a nested record (depth+1)
            if draw(st.booleans().filter(lambda b: b)):  # always True, just to use draw
                if draw(st.integers(min_value=1, max_value=100)) <= 20:
                    child_json = "null"
                else:
                    child_json = gen_record(depth + 1)
            else:
                child_json = "null"

        # id: integer normally, but sometimes string or float to cause divergence
        id_choice = draw(st.integers(min_value=0, max_value=100))
        id_type_variant = draw(st.sampled_from(['int', 'str', 'float']))
        if id_type_variant == 'int':
            id_json = str(id_choice)
        elif id_type_variant == 'str':
            # id as string number, e.g. "42"
            id_json = json_string(str(id_choice))
        else:
            # id as float, e.g. 42.0
            id_json = f"{float(id_choice)}"

        # amount: string normally, but sometimes number or null or boolean
        amount_str = draw(st.text(min_size=0, max_size=10))
        # To avoid invalid JSON string, replace quotes and backslash
        amount_str = amount_str.replace('"', '').replace('\\', '')
        amount_type_variant = draw(st.sampled_from(['str', 'int', 'null', 'bool']))
        if amount_type_variant == 'str':
            amount_json = json_string(amount_str)
        elif amount_type_variant == 'int':
            # amount as integer number (not string)
            amount_json = str(draw(st.integers(min_value=0, max_value=10000)))
        elif amount_type_variant == 'null':
            amount_json = "null"
        else:
            # boolean true or false
            amount_json = draw(st.sampled_from(["true", "false"]))

        # name: string or null or number or missing (simulate missing by null)
        # We always include the field, but sometimes with wrong type
        name_type_variant = draw(st.sampled_from(['str', 'null', 'int']))
        if name_type_variant == 'str':
            name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            if name_val is None:
                name_json = "null"
            else:
                # sanitize string
                name_val = name_val.replace('"', '').replace('\\', '')
                name_json = json_string(name_val)
        elif name_type_variant == 'null':
            name_json = "null"
        else:
            # number instead of string or null
            name_json = str(draw(st.integers(min_value=-100, max_value=100)))

        # status: one of "active", "inactive", "unknown" normally,
        # but sometimes a wrong string or null or number
        status_type_variant = draw(st.sampled_from(['valid', 'invalid_str', 'null', 'int']))
        if status_type_variant == 'valid':
            status_json = draw(st.sampled_from(statuses))
        elif status_type_variant == 'invalid_str':
            # invalid string not in enum
            invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']))
            invalid_status = invalid_status.replace('"', '').replace('\\', '')
            status_json = json_string(invalid_status)
        elif status_type_variant == 'null':
            status_json = "null"
        else:
            status_json = str(draw(st.integers(min_value=0, max_value=10)))

        # tags: array of strings normally, but sometimes null, empty array, or array with non-string
        tags_type_variant = draw(st.sampled_from(['valid', 'null', 'empty', 'nonstring']))
        if tags_type_variant == 'valid':
            tags_list = draw(st.lists(st.text(min_size=0, max_size=5).map(lambda s: s.replace('"', '').replace('\\', '')), min_size=1, max_size=5))
            tags_json = json_string_array(tags_list)
        elif tags_type_variant == 'null':
            tags_json = "null"
        elif tags_type_variant == 'empty':
            tags_json = "[]"
        else:
            # array with mixed types: strings and numbers
            strs = draw(st.lists(st.text(min_size=0, max_size=3).map(lambda s: s.replace('"', '').replace('\\', '')), min_size=0, max_size=3))
            nums = draw(st.lists(st.integers(min_value=0, max_value=10), min_size=0, max_size=3))
            mixed = []
            for v in strs:
                mixed.append(json_string(v))
            for v in nums:
                mixed.append(str(v))
            # shuffle mixed
            mixed = draw(st.permutations(mixed))
            tags_json = '[' + ','.join(mixed) + ']'

        # Compose JSON object fields in random order to increase coverage
        fields = [
            ('"id"', id_json),
            ('"amount"', amount_json),
            ('"name"', name_json),
            ('"status"', status_json),
            ('"tags"', tags_json),
            ('"child"', child_json),
        ]
        # Shuffle fields order
        fields = draw(st.permutations(fields))

        obj_json = '{' + ','.join(f'{k}:{v}' for k, v in fields) + '}'
        return obj_json

    # Generate top-level record at depth 0
    json_text = gen_record(0)
    return json_text.encode('utf-8')