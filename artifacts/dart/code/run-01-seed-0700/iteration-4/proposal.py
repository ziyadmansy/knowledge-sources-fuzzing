from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Enum valid values and some invalid variants for status
    valid_status = ["active", "inactive", "unknown"]
    invalid_status = ["Active", "INACTIVE", "unkn0wn", "", "null", "123", "active "]

    # Strategy for id field:
    # Manual and built_value require int strictly.
    # json_serializable and freezed accept any num and convert via toInt().
    # To cause divergence, sometimes provide int, sometimes float, sometimes string.
    id_int = st.integers(min_value=-(2**31), max_value=2**31-1)
    id_float = st.floats(allow_infinity=False, allow_nan=False).filter(lambda f: f.is_integer() and -(2**31) <= f <= 2**31-1)
    id_str = st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit())  # invalid string id to cause rejection

    id_choice = st.one_of(
        id_int,
        id_float,
        id_str,
    )

    # amount: always string, but try valid string or number string or empty string
    amount_str = st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s)
    # We keep amount always string, but sometimes numeric string to test subtlety
    amount_choice = st.one_of(
        amount_str,
        st.integers(min_value=0, max_value=999999).map(str),
        st.floats(allow_infinity=False, allow_nan=False).map(lambda f: f.hex()),  # hex float string, unusual but string
    )

    # name: nullable string, manual requires present (nullable), built_value and others tolerate missing
    # To cause divergence, sometimes omit name, sometimes null, sometimes string, sometimes wrong type
    name_present_str = st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s)
    name_null = st.just(None)
    name_missing = st.just(st.nothing())  # will handle omission by special logic
    name_wrong_type = st.integers(min_value=0, max_value=100)  # int instead of string or null

    # We'll model name as either present with string or null or wrong type, or omitted
    # But manual requires present, so omission causes manual to reject
    name_choice = st.one_of(
        name_present_str,
        name_null,
        name_wrong_type,
        # Omission handled separately below
    )

    # status: mostly valid enum strings, sometimes invalid strings to cause raw ArgumentError or CheckedFromJsonException
    status_choice = st.one_of(
        st.sampled_from(valid_status),
        st.sampled_from(invalid_status),
    )

    # tags: List<String> required by all, but manual expects List<String> exactly
    # json_serializable and freezed accept List<dynamic> mapped to String
    # built_value expects BuiltList<String>
    # To cause divergence, sometimes put empty list, sometimes list of strings, sometimes list with non-string
    tag_str = st.text(min_size=1, max_size=8).filter(lambda s: '"' not in s and '\\' not in s)
    tags_valid = st.lists(tag_str, min_size=0, max_size=5)
    tags_invalid = st.lists(st.one_of(tag_str, st.integers(), st.booleans()), min_size=1, max_size=5)

    tags_choice = st.one_of(
        tags_valid,
        tags_invalid,
    )

    # child: null or nested record (one level recursion)
    # built_value and manual require child present (nullable), others tolerate missing
    # To cause divergence, sometimes omit child, sometimes null, sometimes nested record
    # Limit recursion depth to 1

    # We'll define a helper to build child JSON text recursively

    def gen_record(depth=0):
        # depth 0 means top-level, depth 1 means child level, no deeper
        # Compose fields as strings, then join with commas inside {}

        # id
        id_v = draw(id_choice)
        if isinstance(id_v, str):
            id_json = '"' + id_v + '"'
        elif isinstance(id_v, float):
            # floats that are integer-valued, output as number (no quotes)
            id_json = str(int(id_v))
        else:
            id_json = str(id_v)

        # amount
        amount_v = draw(amount_choice)
        amount_json = '"' + amount_v + '"'

        # name: sometimes omit only at top-level or child level
        # To cause divergence, omit name only at top-level or child level sometimes
        # We'll draw a bool to decide omission only at top-level (depth==0)
        omit_name = False
        if depth == 0:
            omit_name = draw(st.booleans())
        else:
            # At child level, omit name less often to keep some variation
            omit_name = draw(st.booleans().filter(lambda b: b == False))  # mostly present at child level

        if omit_name:
            # omit name field
            name_json = None
        else:
            name_v = draw(name_choice)
            if name_v is None:
                name_json = 'null'
            elif isinstance(name_v, str):
                name_json = '"' + name_v + '"'
            else:
                # wrong type int
                name_json = str(name_v)

        # status
        status_v = draw(status_choice)
        status_json = '"' + status_v + '"'

        # tags
        tags_v = draw(tags_choice)
        # tags must be JSON array of strings, but tags_v may contain non-strings
        # We'll serialize each element accordingly
        tags_elems = []
        for e in tags_v:
            if isinstance(e, str):
                tags_elems.append('"' + e + '"')
            elif isinstance(e, bool):
                tags_elems.append('true' if e else 'false')
            elif isinstance(e, int):
                tags_elems.append(str(e))
            else:
                # fallback to string repr quoted
                tags_elems.append('"' + str(e) + '"')
        tags_json = '[' + ','.join(tags_elems) + ']'

        # child: null, omitted, or nested record (depth limited)
        # built_value tolerates omitted child, manual requires present (nullable)
        # To cause divergence, sometimes omit child only at top-level
        omit_child = False
        if depth == 0:
            omit_child = draw(st.booleans())
        else:
            # child level: omit child less often
            omit_child = draw(st.booleans().filter(lambda b: b == False))

        if omit_child:
            child_json = None
        else:
            # child can be null or nested record (depth=1 max)
            child_null = draw(st.booleans())
            if child_null or depth >= 1:
                child_json = 'null'
            else:
                child_json = gen_record(depth=depth+1)

        # Compose fields
        fields = []
        fields.append('"id":' + id_json)
        fields.append('"amount":' + amount_json)
        if name_json is not None:
            fields.append('"name":' + name_json)
        fields.append('"status":' + status_json)
        fields.append('"tags":' + tags_json)
        if child_json is not None:
            fields.append('"child":' + child_json)

        return '{' + ','.join(fields) + '}'

    json_text = gen_record(depth=0)
    return json_text.encode('utf-8')