from hypothesis import strategies as st

# Helper: JSON string with proper escaping of quotes and backslashes only (minimal)
def json_string(draw, max_len=20):
    # Use ascii letters, digits, space, and a few punctuation except quotes and backslash
    chars = st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd', 'Zs'),
        blacklist_characters=['"', '\\']
    )
    s = draw(st.text(chars, max_size=max_len))
    # Escape backslash and quote (none here by construction)
    # But to be safe, replace backslash and quote if any slipped in
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + s + '"'

# Helper: JSON string or null (null as literal)
def json_string_or_null(draw):
    return draw(st.one_of(st.just("null"), json_string(draw)))

# Helper: JSON array of strings (possibly empty)
def json_array_of_strings(draw, max_len=5):
    # Generate list of strings, each properly escaped
    n = draw(st.integers(min_value=0, max_value=max_len))
    strs = []
    for _ in range(n):
        s = draw(json_string(draw))
        strs.append(s)
    return "[" + ",".join(strs) + "]"

# Helper: JSON enum for status field, but allow off-by-one errors or wrong casing to induce divergence
def json_status(draw):
    # Mostly valid, but sometimes off-case or wrong string to induce divergence
    base = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
    # Introduce subtle variants:
    variants = st.one_of(
        base,
        st.just('"Active"'),    # capital A
        st.just('"INACTIVE"'),  # all caps
        st.just('"unknown "'),  # trailing space
        st.just('"unkn0wn"'),   # zero instead of o
        st.just('null'),        # null instead of string
        st.just('123'),         # number instead of string
    )
    return draw(variants)

# Helper: JSON integer as number or string (to induce divergence)
def json_id(draw):
    # Mostly integer number, but sometimes stringified integer or float
    choice = draw(st.integers(min_value=0, max_value=1000))
    as_number = st.just(str(choice))
    as_string = st.just('"' + str(choice) + '"')
    as_float = st.just(str(float(choice) + 0.0))  # e.g. "123.0"
    # Also sometimes a string with leading zeros
    as_string_leading_zeros = st.just('"%03d"' % choice)
    return draw(st.one_of(as_number, as_string, as_float, as_string_leading_zeros))

# Helper: JSON amount field, string representing a decimal number, but sometimes malformed
def json_amount(draw):
    # Valid decimal strings or malformed variants
    valid_decimal = st.from_regex(r'^\d+(\.\d+)?$', fullmatch=True)
    # Malformed variants: empty string, leading plus, multiple dots, trailing letters
    malformed = st.sampled_from([
        '""',
        '"+"',
        '"12..3"',
        '"123abc"',
        '"-123.45"',
        '"0.0.0"',
        '" 123"',
        '"123 "',
        '"00123"',
        '"0"',
        '"0.00"',
    ])
    return draw(st.one_of(valid_decimal, malformed))

# Compose a record JSON object as string, with one-level recursion for "child"
@st.composite
def generated_json(draw) -> bytes:
    # id field: integer or stringified integer or float string
    id_val = json_id(draw)

    # amount field: string decimal or malformed string
    amount_val = json_amount(draw)

    # name field: string or null or sometimes number (to induce divergence)
    name_choice = draw(st.one_of(
        st.just("null"),
        json_string(draw),
        st.just('123'),  # number instead of string or null
        st.just('""'),   # empty string
    ))

    # status field: mostly valid enum string, sometimes off variants
    status_val = json_status(draw)

    # tags field: array of strings, sometimes empty, sometimes with null or numbers inside (to induce divergence)
    # We'll mostly keep strings but sometimes inject a null or number as string
    n_tags = draw(st.integers(min_value=0, max_value=4))
    tags_elems = []
    for _ in range(n_tags):
        tag_type = draw(st.integers(min_value=0, max_value=9))
        if tag_type < 7:
            # normal string tag
            tags_elems.append(draw(json_string(draw)))
        elif tag_type == 7:
            tags_elems.append("null")  # null inside array (invalid per schema)
        else:
            # number inside array as string (e.g. "123")
            tags_elems.append(str(draw(st.integers(min_value=0, max_value=999))))
    tags_val = "[" + ",".join(tags_elems) + "]"

    # child field: either null or a nested record (one level only)
    # To keep bounded recursion, child cannot have child itself (always null)
    child_present = draw(st.booleans())
    if child_present:
        # Compose child record with same rules but child=null always
        child_id = json_id(draw)
        child_amount = json_amount(draw)
        child_name = draw(st.one_of(st.just("null"), json_string(draw)))
        child_status = draw(json_status(draw))
        child_tags = json_array_of_strings(draw)
        child_child = "null"
        child_obj = (
            '{'
            f'"id":{child_id},'
            f'"amount":{child_amount},'
            f'"name":{child_name},'
            f'"status":{child_status},'
            f'"tags":{child_tags},'
            f'"child":{child_child}'
            '}'
        )
        child_val = child_obj
    else:
        child_val = "null"

    # Compose full record JSON object string
    obj = (
        '{'
        f'"id":{id_val},'
        f'"amount":{amount_val},'
        f'"name":{name_choice},'
        f'"status":{status_val},'
        f'"tags":{tags_val},'
        f'"child":{child_val}'
        '}'
    )
    return obj.encode("utf-8")