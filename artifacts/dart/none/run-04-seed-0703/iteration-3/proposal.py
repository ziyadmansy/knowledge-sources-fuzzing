from hypothesis import strategies as st

# Constants for enum values and recursion depth
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
MAX_DEPTH = 1  # only one level of recursion for "child"

def json_string_escape(s: str) -> str:
    # Minimal JSON string escaping for double quotes and backslashes
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw, depth=0) -> st.SearchStrategy[str]:
    """
    Generate syntactically valid JSON text for the described record schema,
    with subtle variations to provoke divergence between Dart JSON deserializers.
    Returns JSON text as a string.
    """

    # id: integer, but sometimes inject a string or float to provoke divergence
    # Strategy: mostly int, sometimes stringified int, sometimes float as string
    id_choice = draw(st.integers(min_value=0, max_value=2**31 - 1))
    id_variant = draw(st.integers(min_value=0, max_value=9))
    if id_variant == 0:
        # valid int as number
        id_json = str(id_choice)
    elif id_variant == 1:
        # int as string (wrong type)
        id_json = '"' + str(id_choice) + '"'
    elif id_variant == 2:
        # float as number (wrong type)
        id_json = str(float(id_choice) + 0.5)
    else:
        # valid int as number
        id_json = str(id_choice)

    # amount: string, but sometimes inject a number or null to provoke divergence
    # amount normally a string representing a number, e.g. "123.45"
    # We'll generate a string that looks like a number, or sometimes a number literal or null
    amount_str = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
    # To keep it numeric-ish, sometimes digits and dot only
    if draw(st.booleans()):
        amount_str = draw(st.from_regex(r'\d+(\.\d+)?', fullmatch=True))
    amount_variant = draw(st.integers(min_value=0, max_value=9))
    if amount_variant == 0:
        # valid string
        amount_json = '"' + json_string_escape(amount_str) + '"'
    elif amount_variant == 1:
        # number literal (wrong type)
        try:
            # try to parse as float to emit as number
            float_val = float(amount_str)
            amount_json = str(float_val)
        except Exception:
            amount_json = '"' + json_string_escape(amount_str) + '"'
    elif amount_variant == 2:
        # null (wrong type)
        amount_json = 'null'
    else:
        amount_json = '"' + json_string_escape(amount_str) + '"'

    # name: string or null, sometimes inject number or boolean to provoke divergence
    # name can be null or string or wrong type
    name_variant = draw(st.integers(min_value=0, max_value=9))
    if name_variant <= 4:
        # valid string or null
        if draw(st.booleans()):
            # null
            name_json = 'null'
        else:
            name_str = draw(st.text(min_size=0, max_size=20, alphabet=st.characters(blacklist_characters='"\\')))
            name_json = '"' + json_string_escape(name_str) + '"'
    elif name_variant == 5:
        # number literal (wrong type)
        name_json = str(draw(st.integers(min_value=-1000, max_value=1000)))
    elif name_variant == 6:
        # boolean literal (wrong type)
        name_json = draw(st.sampled_from(['true', 'false']))
    else:
        # valid string
        name_str = draw(st.text(min_size=0, max_size=20, alphabet=st.characters(blacklist_characters='"\\')))
        name_json = '"' + json_string_escape(name_str) + '"'

    # status: one of "active", "inactive", "unknown"
    # Sometimes inject invalid enum string or null or number to provoke divergence
    status_variant = draw(st.integers(min_value=0, max_value=9))
    if status_variant <= 6:
        status_json = draw(st.sampled_from(STATUS_VALUES))
    elif status_variant == 7:
        # invalid enum string
        invalid_status = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
        status_json = '"' + json_string_escape(invalid_status) + '"'
    elif status_variant == 8:
        # null (wrong type)
        status_json = 'null'
    else:
        # number (wrong type)
        status_json = str(draw(st.integers(min_value=0, max_value=10)))

    # tags: array of strings, sometimes inject array of numbers, or null, or empty array
    # tags always present, but can be empty or contain wrong types
    tags_variant = draw(st.integers(min_value=0, max_value=9))
    if tags_variant <= 6:
        # valid array of strings (possibly empty)
        tags_len = draw(st.integers(min_value=0, max_value=5))
        tags_list = []
        for _ in range(tags_len):
            tag_str = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
            tags_list.append('"' + json_string_escape(tag_str) + '"')
        tags_json = '[' + ','.join(tags_list) + ']'
    elif tags_variant == 7:
        # array of numbers (wrong type)
        tags_len = draw(st.integers(min_value=1, max_value=5))
        tags_list = [str(draw(st.integers(min_value=0, max_value=100))) for _ in range(tags_len)]
        tags_json = '[' + ','.join(tags_list) + ']'
    elif tags_variant == 8:
        # null (wrong type)
        tags_json = 'null'
    else:
        # empty array
        tags_json = '[]'

    # child: Record or null, one level of recursion normally
    # Sometimes omit child field (wrong), sometimes null, sometimes valid child
    # To provoke divergence, sometimes child is wrong type (string, number)
    child_variant = draw(st.integers(min_value=0, max_value=9))
    if depth >= MAX_DEPTH:
        # At max depth, child must be null or missing (missing is invalid, but we won't omit here)
        if child_variant <= 7:
            child_json = 'null'
        elif child_variant == 8:
            # wrong type string
            child_json = '"' + json_string_escape(draw(st.text(min_size=1, max_size=10))) + '"'
        else:
            # wrong type number
            child_json = str(draw(st.integers(min_value=0, max_value=1000)))
    else:
        if child_variant <= 5:
            # valid child record (one level deeper)
            child_json = draw(generated_json(depth=depth + 1))
        elif child_variant == 6:
            # null
            child_json = 'null'
        elif child_variant == 7:
            # wrong type string
            child_json = '"' + json_string_escape(draw(st.text(min_size=1, max_size=10))) + '"'
        elif child_variant == 8:
            # wrong type number
            child_json = str(draw(st.integers(min_value=0, max_value=1000)))
        else:
            # omit child field entirely (invalid but syntactically valid JSON object)
            child_json = None

    # Compose fields into JSON object string
    # If child_json is None, omit the field entirely
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
    ]
    if child_json is not None:
        fields.append('"child":' + child_json)

    json_text = '{' + ','.join(fields) + '}'

    return json_text

@st.composite
def generated_json_bytes(draw) -> bytes:
    # Wrap generated_json to produce bytes output as required
    s = draw(generated_json())
    return s.encode('utf-8')