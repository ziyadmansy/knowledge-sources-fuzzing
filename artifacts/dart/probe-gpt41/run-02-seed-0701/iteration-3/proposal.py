from hypothesis import strategies as st

# Helper: JSON string with proper escaping of quotes and backslashes (minimal)
def json_string(s: str) -> str:
    # Escape backslash and double quote
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + s + '"'

# Helper: JSON array of strings
def json_string_array(strings):
    return '[' + ','.join(strings) + ']'

# Helper: JSON object from list of (key, value) pairs (values are JSON text)
def json_object(pairs):
    # pairs: list of (str, str)
    # keys must be JSON strings
    items = []
    for k, v in pairs:
        items.append(json_string(k) + ':' + v)
    return '{' + ','.join(items) + '}'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects matching the record schema,
    with subtle variations to provoke behavioral divergence between
    four Dart JSON deserializers.

    Variations:
    - "id": integer or (rarely) string (to provoke type errors)
    - "amount": string normally, or (rarely) integer (type error)
    - "name": string or null or missing (missing treated as null)
    - "status": enum string or invalid enum string or null (to provoke errors)
    - "tags": array of strings normally, or null (only built_value accepts null)
    - "child": null or nested record (one level recursion only)
    - Extra fields allowed (ignored by all)
    """

    # id: mostly int, rarely string (to provoke type mismatch)
    id_val = draw(st.one_of(
        st.integers(min_value=0, max_value=10**9).map(str),
        st.integers(min_value=0, max_value=10**9).map(lambda i: str(i)),
        st.just(None),  # will not be used, just placeholder
        st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit())  # invalid string id
    ))
    # But we want mostly int, sometimes string that looks like int, sometimes invalid string
    # Let's do a weighted choice:
    id_choice = draw(st.integers(min_value=1, max_value=100))
    if id_choice <= 80:
        # 80% int
        id_json = str(draw(st.integers(min_value=0, max_value=10**9)))
    elif id_choice <= 90:
        # 10% string that looks like int (should cause type error)
        id_json = json_string(str(draw(st.integers(min_value=0, max_value=10**9))))
    else:
        # 10% string non-numeric (should cause type error)
        id_json = json_string(draw(st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit())))

    # amount: mostly string, rarely int (to provoke type mismatch)
    amount_choice = draw(st.integers(min_value=1, max_value=100))
    if amount_choice <= 85:
        # 85% string decimal number with 2 decimals
        amount_val = "{:.2f}".format(draw(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)))
        amount_json = json_string(amount_val)
    else:
        # 15% integer (type mismatch)
        amount_json = str(draw(st.integers(min_value=0, max_value=10000)))

    # name: string or null or missing (missing treated as null)
    name_choice = draw(st.integers(min_value=1, max_value=100))
    if name_choice <= 70:
        # 70% string
        name_val = draw(st.text(min_size=0, max_size=20))
        name_json = json_string(name_val)
        include_name = True
    elif name_choice <= 85:
        # 15% null
        name_json = "null"
        include_name = True
    else:
        # 15% missing
        name_json = None
        include_name = False

    # status: valid enum or invalid enum or null (to provoke errors)
    status_enum = ["active", "inactive", "unknown"]
    status_choice = draw(st.integers(min_value=1, max_value=100))
    if status_choice <= 80:
        status_val = draw(st.sampled_from(status_enum))
        status_json = json_string(status_val)
    elif status_choice <= 90:
        # invalid enum string (case variant or unknown)
        invalid_status = draw(st.sampled_from(["ACTIVE", "pending", "disabled", ""]))
        status_json = json_string(invalid_status)
    else:
        # null (all reject but with different exceptions)
        status_json = "null"

    # tags: array of strings normally, or null (only built_value accepts null)
    tags_choice = draw(st.integers(min_value=1, max_value=100))
    if tags_choice <= 85:
        # array of 0-5 strings
        tag_count = draw(st.integers(min_value=0, max_value=5))
        tags_list = [json_string(draw(st.text(min_size=1, max_size=10))) for _ in range(tag_count)]
        tags_json = '[' + ','.join(tags_list) + ']'
    else:
        # null (only built_value accepts)
        tags_json = "null"

    # child: null or nested record (one level recursion only)
    child_choice = draw(st.integers(min_value=1, max_value=100))
    if child_choice <= 70:
        # null child
        child_json = "null"
    else:
        # nested record, but with simpler fields (no further recursion)
        # For nested record, keep it well-formed but vary "name" presence and "tags" nullness to provoke divergence
        # id int always for child to avoid too many errors
        child_id_json = str(draw(st.integers(min_value=0, max_value=10**9)))
        child_amount_json = json_string("{:.2f}".format(draw(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False))))
        child_name_choice = draw(st.booleans())
        if child_name_choice:
            child_name_json = json_string(draw(st.text(min_size=0, max_size=20)))
            child_include_name = True
        else:
            child_name_json = None
            child_include_name = False
        child_status_json = json_string(draw(st.sampled_from(status_enum)))
        child_tags_choice = draw(st.integers(min_value=1, max_value=100))
        if child_tags_choice <= 90:
            child_tags_count = draw(st.integers(min_value=0, max_value=3))
            child_tags_list = [json_string(draw(st.text(min_size=1, max_size=10))) for _ in range(child_tags_count)]
            child_tags_json = '[' + ','.join(child_tags_list) + ']'
        else:
            child_tags_json = "null"  # only built_value accepts

        child_pairs = [
            ("id", child_id_json),
            ("amount", child_amount_json),
        ]
        if child_include_name:
            child_pairs.append(("name", child_name_json))
        # else omit "name"
        child_pairs.append(("status", child_status_json))
        child_pairs.append(("tags", child_tags_json))
        child_pairs.append(("child", "null"))  # no further recursion

        # Add an extra field sometimes to test tolerance
        if draw(st.booleans()):
            child_pairs.append(("extra_child_field", json_string("ignored")))

        child_json = json_object(child_pairs)

    # Compose top-level pairs
    pairs = [
        ("id", id_json),
        ("amount", amount_json),
    ]
    if include_name:
        pairs.append(("name", name_json))
    # else omit "name"
    pairs.append(("status", status_json))
    pairs.append(("tags", tags_json))
    pairs.append(("child", child_json))

    # Add an extra field sometimes to test tolerance
    if draw(st.booleans()):
        pairs.append(("extra_field", json_string("ignored")))

    json_text = json_object(pairs)
    return json_text.encode("utf-8")