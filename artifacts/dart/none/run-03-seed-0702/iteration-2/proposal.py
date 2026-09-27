from hypothesis import strategies as st

# Helper: JSON string with proper escaping of quotes and backslashes only (minimal)
def json_string(draw):
    # Use a restricted charset to avoid complex escaping issues
    s = draw(st.text(alphabet=st.characters(blacklist_characters='"\\"'), min_size=0, max_size=10))
    # Escape backslash and quote
    s_escaped = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s_escaped}"'

# Helper: JSON string or null (null as literal)
def json_string_or_null(draw):
    return draw(st.one_of(st.just("null"), json_string))

# Helper: JSON array of strings (empty or up to 3 strings)
def json_array_of_strings(draw):
    count = draw(st.integers(min_value=0, max_value=3))
    items = [draw(json_string) for _ in range(count)]
    return "[" + ",".join(items) + "]"

# Helper: JSON enum "active", "inactive", "unknown" or a near-miss string
def json_status(draw):
    # To induce divergence, sometimes produce a valid enum string,
    # sometimes a string close to enum but invalid (e.g. "Active", "inactiv", "unknown ").
    choice = draw(st.integers(min_value=0, max_value=9))
    if choice <= 5:
        # valid enum
        val = draw(st.sampled_from(['"active"', '"inactive"', '"unknown"']))
    else:
        # near-miss invalid enum string (still JSON string)
        near_miss = draw(st.sampled_from([
            '"Active"', '"inactive "', '"unknown "', '"actve"', '"inactiv"', '"unknwn"'
        ]))
        val = near_miss
    return val

# Helper: JSON integer as number or as string (to test type confusion)
def json_id(draw):
    # Sometimes produce integer as number, sometimes as string (valid JSON string)
    as_string = draw(st.booleans())
    val = draw(st.integers(min_value=0, max_value=10000))
    if as_string:
        return f'"{val}"'
    else:
        return str(val)

# Helper: JSON amount field: string representing a number, or a number (to induce type confusion)
def json_amount(draw):
    # amount is supposed to be string, but some implementations may accept number
    as_number = draw(st.booleans())
    if as_number:
        # number as JSON number (int or float)
        val = draw(st.one_of(st.integers(min_value=0, max_value=10000), st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)))
        # format floats carefully to avoid scientific notation
        if isinstance(val, float):
            val_str = f"{val:.2f}"
        else:
            val_str = str(val)
        return val_str
    else:
        # string representing a number, possibly with leading zeros or + sign (to induce divergence)
        num = draw(st.integers(min_value=0, max_value=10000))
        # sometimes add leading zeros or plus sign
        prefix = draw(st.sampled_from(['', '0', '00', '+']))
        return f'"{prefix}{num}"'

# Compose a record recursively, with bounded depth (max 1 level of child)
@st.composite
def record(draw, depth=0):
    # id field: sometimes number, sometimes string number
    id_val = draw(json_id)
    # amount field: string or number (should be string)
    amount_val = draw(json_amount)
    # name: string or null, but sometimes empty string or whitespace string to induce divergence
    name_choice = draw(st.integers(min_value=0, max_value=5))
    if name_choice == 0:
        name_val = "null"
    elif name_choice == 1:
        # empty string
        name_val = '""'
    elif name_choice == 2:
        # whitespace string
        name_val = '"   "'
    else:
        name_val = draw(json_string)
    # status: valid enum or near-miss string
    status_val = draw(json_status)
    # tags: array of strings, sometimes empty, sometimes with empty string elements
    tags_count = draw(st.integers(min_value=0, max_value=3))
    tags_items = []
    for _ in range(tags_count):
        # sometimes empty string or normal string
        if draw(st.booleans()):
            tags_items.append('""')
        else:
            tags_items.append(draw(json_string))
    tags_val = "[" + ",".join(tags_items) + "]"
    # child: null or nested record (only one level deep)
    if depth == 0:
        # 50% chance null, 50% chance nested record
        if draw(st.booleans()):
            child_val = "null"
        else:
            child_val = draw(record(depth=1))
    else:
        # at depth 1, child must be null (no deeper recursion)
        child_val = "null"

    # Build JSON object string with fields in fixed order
    # Intentionally vary spacing around colons and commas to test parsers
    # Also sometimes omit spaces, sometimes add spaces
    space1 = draw(st.sampled_from(["", " "]))
    space2 = draw(st.sampled_from(["", " "]))
    space3 = draw(st.sampled_from(["", " "]))
    space4 = draw(st.sampled_from(["", " "]))
    space5 = draw(st.sampled_from(["", " "]))
    space6 = draw(st.sampled_from(["", " "]))
    space7 = draw(st.sampled_from(["", " "]))

    json_obj = (
        "{" +
        f'"id"{space1}:{space2}{id_val},' +
        f'"amount"{space3}:{space4}{amount_val},' +
        f'"name"{space5}:{space6}{name_val},' +
        f'"status"{space7}:{status_val},' +
        f'"tags":{tags_val},' +
        f'"child":{child_val}' +
        "}"
    )
    return json_obj

@st.composite
def generated_json(draw) -> bytes:
    s = draw(record())
    return s.encode("utf-8")