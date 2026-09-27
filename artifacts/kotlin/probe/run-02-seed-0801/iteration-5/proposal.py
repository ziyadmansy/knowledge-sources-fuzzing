from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslashes only (minimal)
def json_string_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')

# Compose JSON string literal from Python str
def json_str_literal(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

# Compose JSON array literal from list of JSON strings
def json_array_literal(elems: list[str]) -> str:
    return '[' + ','.join(elems) + ']'

# Compose JSON object literal from list of (key, json_value) pairs
def json_object_literal(pairs: list[tuple[str, str]]) -> str:
    # pairs: list of (key, json_value) where key is str (unescaped), json_value is JSON text
    # keys must be JSON strings
    kvs = [json_str_literal(k) + ':' + v for k, v in pairs]
    return '{' + ','.join(kvs) + '}'

# Compose JSON literal for null
json_null = 'null'

# Compose JSON literal for boolean
def json_bool_literal(b: bool) -> str:
    return 'true' if b else 'false'

# Compose JSON literal for integer number
def json_int_literal(i: int) -> str:
    return str(i)

# Compose JSON literal for number as string (quoted)
def json_number_as_string_literal(n: int | float) -> str:
    return json_str_literal(str(n))

# Compose JSON literal for string or null
def json_name_literal(value: str | None, allow_nonstring: bool, nonstring_type: str | None) -> str:
    # value: if not None, string
    # allow_nonstring: if True, can emit number or boolean as string (for Gson/Jackson)
    # nonstring_type: if not None, one of "number", "boolean" to emit that type instead of string
    if value is None:
        return json_null
    if allow_nonstring and nonstring_type == "number":
        # emit as number literal (unquoted)
        try:
            # try int first
            iv = int(value)
            return json_int_literal(iv)
        except Exception:
            # fallback: emit as string
            return json_str_literal(value)
    if allow_nonstring and nonstring_type == "boolean":
        # emit as boolean literal if value is "true" or "false"
        if value.lower() == "true":
            return json_bool_literal(True)
        if value.lower() == "false":
            return json_bool_literal(False)
        # fallback string
        return json_str_literal(value)
    # default: string literal
    return json_str_literal(value)

# Compose JSON literal for "status" field
def json_status_literal(value: str | None) -> str:
    # value must be one of "active", "inactive", "unknown" or invalid string or null
    if value is None:
        return json_null
    return json_str_literal(value)

# Compose JSON literal for "tags" array
def json_tags_literal(elems: list[str], elems_type: str) -> str:
    # elems_type: "string", "number", "boolean", "null"
    # elems: list of strings representing the element values (unescaped)
    # We must produce JSON elements accordingly
    json_elems = []
    for e in elems:
        if elems_type == "string":
            json_elems.append(json_str_literal(e))
        elif elems_type == "number":
            try:
                iv = int(e)
                json_elems.append(json_int_literal(iv))
            except Exception:
                # fallback string
                json_elems.append(json_str_literal(e))
        elif elems_type == "boolean":
            if e.lower() == "true":
                json_elems.append(json_bool_literal(True))
            elif e.lower() == "false":
                json_elems.append(json_bool_literal(False))
            else:
                json_elems.append(json_str_literal(e))
        elif elems_type == "null":
            json_elems.append(json_null)
        else:
            # fallback string
            json_elems.append(json_str_literal(e))
    return json_array_literal(json_elems)

# Compose JSON literal for "amount" field
def json_amount_literal(value: str | int | float, as_number: bool) -> str:
    # as_number: if True, emit as number literal (int or float)
    # else emit as string literal
    if as_number:
        if isinstance(value, (int, float)):
            return str(value)
        # try to parse string as number
        try:
            iv = int(value)
            return str(iv)
        except Exception:
            try:
                fv = float(value)
                return str(fv)
            except Exception:
                # fallback string literal
                return json_str_literal(str(value))
    else:
        return json_str_literal(str(value))

# Compose JSON literal for "id" field
def json_id_literal(value: int | str, as_string: bool) -> str:
    if as_string:
        return json_str_literal(str(value))
    else:
        # emit as integer literal
        if isinstance(value, int):
            return str(value)
        try:
            iv = int(value)
            return str(iv)
        except Exception:
            # fallback string literal
            return json_str_literal(str(value))

@st.composite
def generated_json(draw) -> bytes:
    # Strategy to produce a JSON document string (bytes) for the record schema,
    # designed to maximize divergence among Gson, Moshi, kotlinx.serialization, Jackson.

    # We produce a record with fields:
    # id: int or string convertible to int (all accept)
    # amount: string or number (Gson, Moshi, Jackson accept number; kotlinx rejects number)
    # name: string or null; Gson, Jackson accept number or boolean (converted to string), Moshi, kotlinx reject non-string non-null
    # status: exact enum string or invalid string or null (Gson accepts invalid enum as null; others reject invalid enum)
    # tags: array of strings (Gson, Moshi, Jackson accept non-string elements converted to string; kotlinx rejects non-string elements)
    # child: record or null (one level recursion)

    # To maximize divergence, vary one or two fields at a time with borderline values.

    # 1) id field: choose int or string int (both accepted by all)
    id_as_string = draw(st.booleans())
    id_value = draw(st.integers(min_value=0, max_value=10000))
    id_json = json_id_literal(id_value, id_as_string)

    # 2) amount field: choose string or number
    # If number, kotlinx rejects; others accept
    amount_as_number = draw(st.booleans())
    # amount value as string digits or number
    amount_value_str = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(min_codepoint=48, max_codepoint=57)))  # digits string
    # ensure amount_value_str is digits only
    if not amount_value_str.isdigit():
        amount_value_str = '123'
    amount_value_int = int(amount_value_str)
    amount_json = json_amount_literal(amount_value_int if amount_as_number else amount_value_str, amount_as_number)

    # 3) name field: choose null, string, or non-string (number or boolean)
    # Gson, Jackson accept number or boolean as string; Moshi, kotlinx reject non-string non-null
    name_choice = draw(st.sampled_from(['null', 'string', 'number', 'boolean']))
    if name_choice == 'null':
        name_json = json_null
    elif name_choice == 'string':
        name_str = draw(st.text(min_size=1, max_size=10))
        name_json = json_str_literal(name_str)
    elif name_choice == 'number':
        # number as int literal
        name_num = draw(st.integers(min_value=0, max_value=1000))
        name_json = str(name_num)
    else:  # boolean
        name_bool = draw(st.booleans())
        name_json = json_bool_literal(name_bool)

    # 4) status field: choose valid enum, invalid enum, or null
    status_choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
    if status_choice == 'valid':
        status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        status_json = json_str_literal(status_val)
    elif status_choice == 'invalid':
        # invalid enum string
        status_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']))
        status_json = json_str_literal(status_val)
    else:
        status_json = json_null

    # 5) tags field: must be array; elements string or non-string or null
    # Gson, Moshi, Jackson accept non-string elements converted to string; kotlinx rejects non-string elements
    # To maximize divergence, sometimes include non-string elements
    tags_len = draw(st.integers(min_value=0, max_value=4))
    # element types: string, number, boolean, null
    # choose element types to include
    tags_elem_types = draw(st.lists(st.sampled_from(['string', 'number', 'boolean', 'null']), min_size=tags_len, max_size=tags_len))
    tags_elems = []
    for etype in tags_elem_types:
        if etype == 'string':
            s = draw(st.text(min_size=1, max_size=5))
            tags_elems.append(s)
        elif etype == 'number':
            n = draw(st.integers(min_value=0, max_value=1000))
            tags_elems.append(str(n))
        elif etype == 'boolean':
            b = draw(st.booleans())
            tags_elems.append('true' if b else 'false')
        else:  # null
            tags_elems.append('null')
    # Compose tags JSON array with mixed element types
    # We must emit elements as JSON literals, so recompose below:
    tags_json_elems = []
    for etype, val in zip(tags_elem_types, tags_elems):
        if etype == 'string':
            tags_json_elems.append(json_str_literal(val))
        elif etype == 'number':
            tags_json_elems.append(val)  # number literal string
        elif etype == 'boolean':
            tags_json_elems.append(val)  # "true" or "false"
        else:
            tags_json_elems.append(json_null)
    tags_json = json_array_literal(tags_json_elems)

    # 6) child field: null or nested record (one level only)
    child_present = draw(st.booleans())
    if not child_present:
        child_json = json_null
    else:
        # Nested record with same schema but no further nesting (child.child always null)
        # To maximize divergence, vary one or two fields in child differently from top-level
        # id: int or string
        child_id_as_string = draw(st.booleans())
        child_id_value = draw(st.integers(min_value=0, max_value=10000))
        child_id_json = json_id_literal(child_id_value, child_id_as_string)

        # amount: string or number (kotlin rejects number)
        child_amount_as_number = draw(st.booleans())
        child_amount_value_str = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(min_codepoint=48, max_codepoint=57)))
        if not child_amount_value_str.isdigit():
            child_amount_value_str = '456'
        child_amount_value_int = int(child_amount_value_str)
        child_amount_json = json_amount_literal(child_amount_value_int if child_amount_as_number else child_amount_value_str, child_amount_as_number)

        # name: null, string, number, boolean
        child_name_choice = draw(st.sampled_from(['null', 'string', 'number', 'boolean']))
        if child_name_choice == 'null':
            child_name_json = json_null
        elif child_name_choice == 'string':
            child_name_str = draw(st.text(min_size=1, max_size=10))
            child_name_json = json_str_literal(child_name_str)
        elif child_name_choice == 'number':
            child_name_num = draw(st.integers(min_value=0, max_value=1000))
            child_name_json = str(child_name_num)
        else:
            child_name_bool = draw(st.booleans())
            child_name_json = json_bool_literal(child_name_bool)

        # status: valid, invalid, null
        child_status_choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
        if child_status_choice == 'valid':
            child_status_val = draw(st.sampled_from(['active', 'inactive', 'unknown']))
            child_status_json = json_str_literal(child_status_val)
        elif child_status_choice == 'invalid':
            child_status_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']))
            child_status_json = json_str_literal(child_status_val)
        else:
            child_status_json = json_null

        # tags: array with mixed element types (like top-level)
        child_tags_len = draw(st.integers(min_value=0, max_value=3))
        child_tags_elem_types = draw(st.lists(st.sampled_from(['string', 'number', 'boolean', 'null']), min_size=child_tags_len, max_size=child_tags_len))
        child_tags_elems = []
        for etype in child_tags_elem_types:
            if etype == 'string':
                s = draw(st.text(min_size=1, max_size=5))
                child_tags_elems.append(s)
            elif etype == 'number':
                n = draw(st.integers(min_value=0, max_value=1000))
                child_tags_elems.append(str(n))
            elif etype == 'boolean':
                b = draw(st.booleans())
                child_tags_elems.append('true' if b else 'false')
            else:
                child_tags_elems.append('null')
        child_tags_json_elems = []
        for etype, val in zip(child_tags_elem_types, child_tags_elems):
            if etype == 'string':
                child_tags_json_elems.append(json_str_literal(val))
            elif etype == 'number':
                child_tags_json_elems.append(val)
            elif etype == 'boolean':
                child_tags_json_elems.append(val)
            else:
                child_tags_json_elems.append(json_null)
        child_tags_json = json_array_literal(child_tags_json_elems)

        # child.child always null (no deeper nesting)
        child_child_json = json_null

        child_pairs = [
            ("id", child_id_json),
            ("amount", child_amount_json),
            ("name", child_name_json),
            ("status", child_status_json),
            ("tags", child_tags_json),
            ("child", child_child_json),
        ]
        child_json = json_object_literal(child_pairs)

    # Compose top-level record JSON object
    top_pairs = [
        ("id", id_json),
        ("amount", amount_json),
        ("name", name_json),
        ("status", status_json),
        ("tags", tags_json),
        ("child", child_json),
    ]
    json_text = json_object_literal(top_pairs)

    return json_text.encode('utf-8')