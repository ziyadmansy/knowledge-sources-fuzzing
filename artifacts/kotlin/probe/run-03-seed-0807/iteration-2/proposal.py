from hypothesis import strategies as st

# Constants for enum values
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
INVALID_STATUS_VALUES = ['"enabled"', '"ACTIVE"', 'null', '123', 'true', 'false', '""']

# Helper to produce JSON string literals safely (no escaping needed for test)
def json_str(s: str) -> str:
    # We assume s has no special chars for simplicity; Hypothesis strings are ASCII by default
    # If needed, could add escaping here
    return '"' + s + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text (bytes) for the record schema, designed to trigger divergences
    among Gson, Moshi, kotlinx.serialization, and Jackson Kotlin module.
    """

    # Recursive limit: max depth 1 for child (one level of recursion)
    # We'll produce a record with optional child record or null.

    # --- id field ---
    # id can be integer or string integer (all accept both)
    id_int = draw(st.integers(min_value=0, max_value=2**31-1))
    id_as_string = draw(st.booleans())
    if id_as_string:
        id_field = str(id_int)
        id_json = '"' + id_field + '"'
    else:
        id_json = str(id_int)

    # --- amount field ---
    # Known: Gson, Moshi, Jackson accept number or string; kotlinx rejects number
    # To maximize divergence, sometimes produce number, sometimes string, sometimes null (Gson accepts null)
    amount_type = draw(st.sampled_from(['string', 'number', 'null']))
    if amount_type == 'string':
        # string amount, non-empty numeric string or arbitrary string
        # To avoid rejection by kotlinx, string is safest
        amount_val = draw(st.one_of(
            st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])),
            st.from_regex(r'-?\d+(\.\d+)?', fullmatch=True)
        ))
        amount_json = json_str(amount_val)
    elif amount_type == 'number':
        # number amount (float or int)
        # This triggers rejection by kotlinx
        amount_val = draw(st.one_of(
            st.integers(min_value=-1000000, max_value=1000000),
            st.floats(allow_infinity=False, allow_nan=False, width=32)
        ))
        # JSON number formatting
        if isinstance(amount_val, float):
            # Format float with repr to avoid scientific notation if possible
            amount_json = repr(amount_val)
        else:
            amount_json = str(amount_val)
    else:
        # null amount (Gson accepts, others reject)
        amount_json = 'null'

    # --- name field ---
    # name can be string or null normally
    # Gson, Moshi, Jackson accept string or number (converted to string)
    # kotlinx rejects non-string non-null
    # Try to produce string, null, or number (to cause divergence)
    name_type = draw(st.sampled_from(['string', 'null', 'number']))
    if name_type == 'string':
        # string or null
        # string can be empty or normal
        name_val = draw(st.one_of(
            st.none(),
            st.text(min_size=0, max_size=20, alphabet=st.characters(blacklist_characters=['"','\\']))
        ))
        if name_val is None:
            name_json = 'null'
        else:
            name_json = json_str(name_val)
    elif name_type == 'null':
        name_json = 'null'
    else:
        # number (int or float)
        name_num = draw(st.one_of(
            st.integers(min_value=-1000000, max_value=1000000),
            st.floats(allow_infinity=False, allow_nan=False, width=32)
        ))
        if isinstance(name_num, float):
            name_json = repr(name_num)
        else:
            name_json = str(name_num)

    # --- status field ---
    # Enum: "active", "inactive", "unknown"
    # Gson accepts invalid enum values and null, sets null
    # Others reject invalid or null
    # To cause divergence, sometimes produce valid enum, sometimes invalid string, sometimes null
    status_type = draw(st.sampled_from(['valid', 'invalid', 'null']))
    if status_type == 'valid':
        status_json = draw(st.sampled_from(STATUS_VALUES))
    elif status_type == 'invalid':
        status_json = draw(st.sampled_from(INVALID_STATUS_VALUES))
    else:
        status_json = 'null'

    # --- tags field ---
    # Must be array
    # Gson, Moshi, Jackson accept arrays with non-string elements (converted to strings or null)
    # kotlinx rejects non-string elements or null elements
    # Gson accepts null elements in array; kotlinx rejects
    # Also Gson accepts null tags in nested child; others reject
    # We'll produce array of strings, or array with some nulls or numbers to cause divergence
    tags_type = draw(st.sampled_from(['all_strings', 'mixed', 'null_element', 'empty_array']))
    if tags_type == 'all_strings':
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])), min_size=0, max_size=5))
        tags_json = '[' + ','.join(json_str(t) for t in tags_list) + ']'
    elif tags_type == 'mixed':
        # mix strings and numbers and booleans (Gson, Moshi, Jackson accept; kotlinx rejects)
        elems = []
        n = draw(st.integers(min_value=1, max_value=5))
        for _ in range(n):
            elem_type = draw(st.sampled_from(['string', 'number', 'bool']))
            if elem_type == 'string':
                s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])))
                elems.append(json_str(s))
            elif elem_type == 'number':
                num = draw(st.integers(min_value=-1000, max_value=1000))
                elems.append(str(num))
            else:
                b = draw(st.booleans())
                elems.append('true' if b else 'false')
        tags_json = '[' + ','.join(elems) + ']'
    elif tags_type == 'null_element':
        # array with some null elements (Gson accepts; kotlinx rejects)
        n = draw(st.integers(min_value=1, max_value=5))
        elems = []
        for _ in range(n):
            if draw(st.booleans()):
                elems.append('null')
            else:
                s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])))
                elems.append(json_str(s))
        tags_json = '[' + ','.join(elems) + ']'
    else:
        # empty array
        tags_json = '[]'

    # --- child field ---
    # child is either null or a nested record (one level)
    # Gson accepts empty object {} as child, filling defaults/nulls; others reject missing required fields
    # Gson accepts null or invalid enum or null amount or null tags in child; others reject
    # To cause divergence, sometimes produce null, sometimes full child, sometimes empty object, sometimes partial child
    child_type = draw(st.sampled_from(['null', 'full', 'empty_object', 'partial']))

    def gen_child_record():
        # child record with fields, but with some fields possibly null or invalid to cause divergence
        # id: integer or string integer (always accepted)
        cid_int = draw(st.integers(min_value=0, max_value=2**31-1))
        cid_as_string = draw(st.booleans())
        if cid_as_string:
            cid_json = '"' + str(cid_int) + '"'
        else:
            cid_json = str(cid_int)

        # amount: string, number, or null (Gson accepts null)
        c_amount_type = draw(st.sampled_from(['string', 'number', 'null']))
        if c_amount_type == 'string':
            c_amount_val = draw(st.one_of(
                st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])),
                st.from_regex(r'-?\d+(\.\d+)?', fullmatch=True)
            ))
            c_amount_json = json_str(c_amount_val)
        elif c_amount_type == 'number':
            c_amount_val = draw(st.one_of(
                st.integers(min_value=-1000000, max_value=1000000),
                st.floats(allow_infinity=False, allow_nan=False, width=32)
            ))
            if isinstance(c_amount_val, float):
                c_amount_json = repr(c_amount_val)
            else:
                c_amount_json = str(c_amount_val)
        else:
            c_amount_json = 'null'

        # name: string, null, or number (Gson accepts number)
        c_name_type = draw(st.sampled_from(['string', 'null', 'number']))
        if c_name_type == 'string':
            c_name_val = draw(st.one_of(
                st.none(),
                st.text(min_size=0, max_size=20, alphabet=st.characters(blacklist_characters=['"','\\']))
            ))
            if c_name_val is None:
                c_name_json = 'null'
            else:
                c_name_json = json_str(c_name_val)
        elif c_name_type == 'null':
            c_name_json = 'null'
        else:
            c_name_num = draw(st.one_of(
                st.integers(min_value=-1000000, max_value=1000000),
                st.floats(allow_infinity=False, allow_nan=False, width=32)
            ))
            if isinstance(c_name_num, float):
                c_name_json = repr(c_name_num)
            else:
                c_name_json = str(c_name_num)

        # status: valid, invalid, or null (Gson accepts invalid/null)
        c_status_type = draw(st.sampled_from(['valid', 'invalid', 'null']))
        if c_status_type == 'valid':
            c_status_json = draw(st.sampled_from(STATUS_VALUES))
        elif c_status_type == 'invalid':
            c_status_json = draw(st.sampled_from(INVALID_STATUS_VALUES))
        else:
            c_status_json = 'null'

        # tags: array of strings, null elements, or null (Gson accepts null tags in child)
        c_tags_type = draw(st.sampled_from(['all_strings', 'null_element', 'null']))
        if c_tags_type == 'all_strings':
            c_tags_list = draw(st.lists(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])), min_size=0, max_size=5))
            c_tags_json = '[' + ','.join(json_str(t) for t in c_tags_list) + ']'
        elif c_tags_type == 'null_element':
            n = draw(st.integers(min_value=1, max_value=5))
            elems = []
            for _ in range(n):
                if draw(st.booleans()):
                    elems.append('null')
                else:
                    s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])))
                    elems.append(json_str(s))
            c_tags_json = '[' + ','.join(elems) + ']'
        else:
            c_tags_json = 'null'

        # child.child is always null (no deeper recursion)
        c_child_json = 'null'

        # Compose child JSON object with all fields present
        # To test partial child, caller can omit fields
        fields = [
            '"id":' + cid_json,
            '"amount":' + c_amount_json,
            '"name":' + c_name_json,
            '"status":' + c_status_json,
            '"tags":' + c_tags_json,
            '"child":' + c_child_json,
        ]
        return '{' + ','.join(fields) + '}'

    if child_type == 'null':
        child_json = 'null'
    elif child_type == 'full':
        child_json = gen_child_record()
    elif child_type == 'empty_object':
        # Gson accepts empty object as child; others reject
        child_json = '{}'
    else:
        # partial child: omit one or two fields randomly (others reject)
        full_child = gen_child_record()
        # parse fields from full_child string (simple split)
        # full_child is like {"id":..., "amount":..., ...}
        # We'll remove one or two fields by string manipulation
        # Since no json module allowed, do simple heuristic:
        # split by commas outside quotes
        # Our generated fields have no commas inside values except tags array which may have commas
        # To be safe, remove last one or two fields by splitting on commas from right
        # This is a heuristic but should suffice for fuzzing
        # Remove 1 or 2 fields from the end
        n_remove = draw(st.integers(min_value=1, max_value=2))
        # strip braces
        inner = full_child[1:-1]
        parts = []
        depth = 0
        last = 0
        for i, c in enumerate(inner):
            if c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
            elif c == ',' and depth == 0:
                parts.append(inner[last:i])
                last = i+1
        parts.append(inner[last:])
        # remove last n_remove fields
        if n_remove >= len(parts):
            # remove all fields -> empty object
            child_json = '{}'
        else:
            parts = parts[:-n_remove]
            child_json = '{' + ','.join(parts) + '}'

    # --- Compose top-level JSON object ---
    # Compose fields in fixed order for consistency
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
        '"child":' + child_json,
    ]
    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')