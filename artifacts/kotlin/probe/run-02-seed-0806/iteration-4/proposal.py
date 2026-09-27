from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only for simplicity
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array from list of JSON texts
def json_array(items):
    return '[' + ','.join(items) + ']'

# Helper: JSON object from list of (key, json_text) pairs
def json_object(pairs):
    return '{' + ','.join(json_string(k) + ':' + v for k, v in pairs) + '}'

# Recursive record generator with bounded depth
@st.composite
def generated_json(draw, _depth=0):
    # Limit recursion depth to 1 for "child" field
    max_depth = 1

    # id: integer or string integer (to trigger known divergence)
    id_int = draw(st.integers(min_value=0, max_value=10000))
    id_as_string = draw(st.booleans())
    if id_as_string:
        id_json = json_string(str(id_int))
    else:
        id_json = str(id_int)

    # amount: string normally, but sometimes number to trigger divergence
    # Known: Gson, Moshi, Jackson accept number or string; kotlinx rejects number
    # So produce amount as string or number
    amount_is_number = draw(st.booleans())
    if amount_is_number:
        # amount as number (int or float string)
        # Use int for simplicity
        amount_num = draw(st.integers(min_value=0, max_value=100000))
        amount_json = str(amount_num)
    else:
        # amount as string (including numeric string)
        # Also try empty string or normal numeric string
        amount_str = draw(st.text(min_size=0, max_size=10))
        # Restrict to ASCII printable except quotes and backslash for safe JSON string
        amount_str = ''.join(c for c in amount_str if c not in '"\\')
        amount_json = json_string(amount_str)

    # name: string or null
    # Gson accepts string or null; all accept null
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = 'null'
    else:
        # string or empty string
        name_str = draw(st.text(min_size=0, max_size=20))
        name_str = ''.join(c for c in name_str if c not in '"\\')
        name_json = json_string(name_str)

    # status: enum "active", "inactive", "unknown"
    # Known: Gson accepts unknown enum as null; others reject unknown enum
    # Also Gson accepts null; others reject null
    # So produce either valid enum, unknown enum string, or null
    status_choice = draw(st.integers(min_value=0, max_value=4))
    if status_choice == 0:
        status_json = json_string("active")
    elif status_choice == 1:
        status_json = json_string("inactive")
    elif status_choice == 2:
        status_json = json_string("unknown")
    elif status_choice == 3:
        # unknown enum string (to trigger Gson accept as null, others reject)
        # Use a string not in enum
        status_json = json_string("invalid_status")
    else:
        # null for enum (Gson accepts, others reject)
        status_json = 'null'

    # tags: array of strings normally
    # Known:
    # Gson and Moshi coerce non-string elements to strings
    # kotlinx rejects non-string elements and null elements
    # Jackson accepts non-string elements as-is and accepts null elements
    # Gson and Jackson accept null for tags; Moshi and kotlinx reject null tags
    # So produce tags as:
    # - null (to trigger Gson/Jackson accept, Moshi/kotlinx reject)
    # - array with strings only (valid)
    # - array with some null elements (Gson, Moshi, Jackson accept; kotlinx reject)
    # - array with some non-string elements (int, bool) (Gson, Moshi coerce; kotlinx reject; Jackson accept as-is)
    tags_null = draw(st.booleans())
    if tags_null:
        tags_json = 'null'
    else:
        # array length 0..5
        tags_len = draw(st.integers(min_value=0, max_value=5))
        tags_items = []
        for _ in range(tags_len):
            # element type choice:
            # 0: string
            # 1: null
            # 2: number (int)
            # 3: boolean
            elem_type = draw(st.integers(min_value=0, max_value=3))
            if elem_type == 0:
                s = draw(st.text(min_size=0, max_size=10))
                s = ''.join(c for c in s if c not in '"\\')
                tags_items.append(json_string(s))
            elif elem_type == 1:
                tags_items.append('null')
            elif elem_type == 2:
                n = draw(st.integers(min_value=-1000, max_value=1000))
                tags_items.append(str(n))
            else:
                b = draw(st.booleans())
                tags_items.append('true' if b else 'false')
        tags_json = json_array(tags_items)

    # child: null or Record (one level recursion max)
    # Known:
    # Gson accepts empty object for child (fills missing fields with defaults/nulls)
    # Moshi, kotlinx, Jackson reject empty object for child
    # So produce child as:
    # - null
    # - empty object {}
    # - valid record (recursion depth < max_depth)
    child_choice = draw(st.integers(min_value=0, max_value=2))
    if _depth >= max_depth:
        # At max depth, only null child allowed
        child_json = 'null'
    else:
        if child_choice == 0:
            child_json = 'null'
        elif child_choice == 1:
            # empty object
            child_json = '{}'
        else:
            # recursive record
            child_json = draw(generated_json(_depth=_depth + 1))

    # Compose the object fields in order
    # All fields always present (except child can be null or object)
    # Fields: id, amount, name, status, tags, child
    obj_pairs = [
        ("id", id_json),
        ("amount", amount_json),
        ("name", name_json),
        ("status", status_json),
        ("tags", tags_json),
        ("child", child_json),
    ]
    json_text = json_object(obj_pairs)
    return json_text.encode('utf-8')