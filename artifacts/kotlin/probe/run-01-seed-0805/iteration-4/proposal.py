from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ['active', 'inactive', 'unknown']
    # To limit recursion depth, max depth = 1 (child can be null or a record with child=null)
    MAX_DEPTH = 1

    # Helper to produce JSON string for a string value with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for quotes and backslash
        esc = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{esc}"'

    # Helper to produce JSON string for an integer
    def json_int(i: int) -> str:
        return str(i)

    # Helper to produce JSON string for a JSON array of strings
    def json_array_of_strings(lst) -> str:
        # lst is list of strings
        return '[' + ','.join(json_string(e) for e in lst) + ']'

    # Helper to produce JSON string for "id" field
    # id can be integer or string convertible to integer
    # We vary type to trigger divergence
    def gen_id():
        # Choose int or string (string convertible to int)
        as_int = draw(st.booleans())
        val = draw(st.integers(min_value=0, max_value=10**9))
        if as_int:
            return json_int(val)
        else:
            # string convertible to int
            return json_string(str(val))

    # Helper to produce JSON string for "amount" field
    # amount is string normally, but Gson/Moshi/Jackson accept number (converted to string), kotlinx rejects number
    # So we vary between string and number to cause divergence
    def gen_amount():
        # Choose string or number
        as_number = draw(st.booleans())
        if as_number:
            # number can be int or float (float might cause all to reject, so keep int)
            val = draw(st.integers(min_value=0, max_value=10**9))
            return str(val)
        else:
            # string, possibly numeric string or arbitrary string
            # To maximize divergence, sometimes numeric string, sometimes non-numeric string
            numeric_string = draw(st.booleans())
            if numeric_string:
                val = draw(st.integers(min_value=0, max_value=10**9))
                return json_string(str(val))
            else:
                # arbitrary string, but avoid quotes and backslash to keep simple
                s = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
                return json_string(s)

    # Helper to produce JSON string for "name" field
    # name can be string or null
    # Gson, Moshi accept string or number (converted to string)
    # kotlinx rejects number
    # Jackson accepts number converted to string
    # null accepted by all
    # So vary among null, string, number to cause divergence
    def gen_name():
        choice = draw(st.sampled_from(['null', 'string', 'number']))
        if choice == 'null':
            return 'null'
        elif choice == 'string':
            s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
            return json_string(s)
        else:
            # number as int or float (float might cause all reject, so int)
            val = draw(st.integers(min_value=-10**9, max_value=10**9))
            return str(val)

    # Helper to produce JSON string for "status" field
    # Only exact enum strings accepted by Moshi, kotlinx, Jackson
    # Gson accepts invalid strings but decodes invalid as null
    # So vary among valid enum strings, invalid strings, and null (null not accepted)
    def gen_status():
        choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
        if choice == 'valid':
            val = draw(st.sampled_from(STATUS_VALUES))
            return json_string(val)
        elif choice == 'invalid':
            # invalid string not in enum
            # avoid quotes and backslash
            s = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
            # ensure s not in STATUS_VALUES
            while s in STATUS_VALUES:
                s = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
            return json_string(s)
        else:
            # null (should cause rejection by all except Gson? Actually no, null not accepted)
            return 'null'

    # Helper to produce JSON string for "tags" field
    # Must be array of strings
    # Gson, Moshi, Jackson accept numbers in array (Moshi rejects booleans)
    # kotlinx rejects non-string elements
    # So vary array elements among strings, numbers, booleans to cause divergence
    def gen_tags():
        # Decide if tags is array or not (to cause rejection by all if not array)
        # But since all reject non-array, keep array to maximize divergence
        # Array length 0 to 5
        length = draw(st.integers(min_value=0, max_value=5))
        # For each element, choose type: string, number, boolean
        elements = []
        for _ in range(length):
            elem_type = draw(st.sampled_from(['string', 'number', 'boolean']))
            if elem_type == 'string':
                s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
                elements.append(json_string(s))
            elif elem_type == 'number':
                val = draw(st.integers(min_value=-10**9, max_value=10**9))
                elements.append(str(val))
            else:
                # boolean true or false
                b = draw(st.booleans())
                elements.append('true' if b else 'false')
        return '[' + ','.join(elements) + ']'

    # Helper to produce JSON string for "child" field
    # child can be null or full Record (one level recursion)
    # empty object {} accepted only by Gson, rejected by others
    # missing fields in child cause rejection by Moshi, kotlinx, Jackson; Gson fills defaults
    # So vary child among null, full record, empty object, partial record (missing fields)
    def gen_child(depth=0):
        choice = draw(st.sampled_from(['null', 'full', 'empty', 'partial']))
        if depth >= MAX_DEPTH:
            # At max depth, only allow null or full with child=null to avoid infinite recursion
            choice = draw(st.sampled_from(['null', 'full']))
        if choice == 'null':
            return 'null'
        elif choice == 'empty':
            # empty object {}
            return '{}'
        elif choice == 'partial':
            # partial record with missing fields (remove 1 or 2 fields)
            # Only allowed at depth 0 to cause divergence
            # Build partial record with missing fields
            # Fields: id, amount, name, status, tags, child
            fields = ['id', 'amount', 'name', 'status', 'tags', 'child']
            missing_count = draw(st.integers(min_value=1, max_value=2))
            missing_fields = draw(st.lists(st.sampled_from(fields), min_size=missing_count, max_size=missing_count, unique=True))
            present_fields = [f for f in fields if f not in missing_fields]
            parts = []
            for f in present_fields:
                parts.append(f'"{f}":{gen_field(f, depth+1)}')
            return '{' + ','.join(parts) + '}'
        else:
            # full record
            parts = []
            for f in ['id', 'amount', 'name', 'status', 'tags', 'child']:
                parts.append(f'"{f}":{gen_field(f, depth+1)}')
            return '{' + ','.join(parts) + '}'

    # Helper to generate field value JSON string by field name and depth
    def gen_field(field_name, depth):
        if field_name == 'id':
            return gen_id()
        elif field_name == 'amount':
            return gen_amount()
        elif field_name == 'name':
            return gen_name()
        elif field_name == 'status':
            return gen_status()
        elif field_name == 'tags':
            return gen_tags()
        elif field_name == 'child':
            return gen_child(depth)
        else:
            # Should not happen
            return 'null'

    # Compose top-level record JSON string
    json_text = '{' + ','.join(
        f'"{f}":{gen_field(f, 0)}' for f in ['id', 'amount', 'name', 'status', 'tags', 'child']
    ) + '}'

    return json_text.encode('utf-8')