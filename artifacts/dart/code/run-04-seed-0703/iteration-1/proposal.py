from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Enum values for status
    valid_statuses = ["active", "inactive", "unknown"]
    # Also include some invalid enum strings to provoke divergence in enum decoding
    invalid_statuses = ["Active", "INACTIVE", "unknown ", "actve", "inactiv", "null", "", "123"]

    # Strategy for id field:
    # Manual requires int exactly,
    # json_serializable/freezed accept any num and convert via toInt(),
    # built_value expects int and likely rejects non-int.
    # So try int, float with integral value, float with fractional value, stringified number (as string),
    # and also a number outside int range (large float).
    # But must produce valid JSON number or string (not null or object).
    id_int = st.integers(min_value=-(2**31), max_value=2**31-1)
    id_float_integral = id_int.map(float)
    id_float_fractional = st.floats(allow_infinity=False, allow_nan=False).filter(lambda f: f != int(f))
    # We won't do string for id because manual requires int exactly and string would be rejected by all.
    # But float integral might be accepted by json_serializable/freezed but rejected by manual and built_value.
    id_candidates = st.one_of(
        id_int,
        id_float_integral,
        id_float_fractional,
    )

    # amount must be string exactly
    # We generate valid strings, but also try some edge cases like empty string, numeric strings
    amount_str = st.text(min_size=0, max_size=20)

    # name: string or null
    name_str_or_null = st.one_of(st.none(), st.text(min_size=0, max_size=20))

    # status: mostly valid enum strings, sometimes invalid to provoke divergence
    status_str = st.one_of(
        st.sampled_from(valid_statuses).map(lambda s: s),
        st.sampled_from(invalid_statuses).map(lambda s: s),
    )

    # tags: array of strings
    # Manual casts to List then maps elements as String
    # json_serializable/freezed cast to List<dynamic> then map to String
    # built_value expects BuiltList<String> and rejects non-list or lists with non-string elements
    # So try:
    # - valid list of strings
    # - list with one non-string element (int, null, bool)
    # - empty list
    # - single string (should be rejected by all)
    tag_str = st.text(min_size=0, max_size=10)
    valid_tags = st.lists(tag_str, min_size=0, max_size=5)
    invalid_tag_element = st.one_of(st.integers(), st.none(), st.booleans())
    tags_candidates = st.one_of(
        valid_tags,
        st.lists(st.one_of(tag_str, invalid_tag_element), min_size=1, max_size=5),
        # single string instead of list (invalid but syntactically valid JSON)
        tag_str,
    )

    # child: null or nested record (one level recursion)
    # To avoid infinite recursion, limit depth to 1
    # We'll generate child as null or a nested record with only valid fields (no invalid enum or id)
    # to isolate divergences to top-level fields.
    # But sometimes also try invalid child to provoke divergence in nested parsing.
    # We'll do a small helper function for child record generation with limited depth.

    def record(depth=0):
        # At depth 1, child must be null to avoid deep recursion
        if depth >= 1:
            child_val = st.none()
        else:
            child_val = st.one_of(st.none(), record(depth + 1))

        # For child record, mostly generate valid fields to isolate divergence to top-level
        # But sometimes inject invalid enum or id to provoke nested divergence
        # We'll do 80% valid, 20% invalid for child fields

        # id for child: mostly int, sometimes float integral or fractional
        child_id = st.one_of(
            id_int,
            id_float_integral,
            id_float_fractional,
        )

        # amount string for child
        child_amount = amount_str

        # name string or null for child
        child_name = name_str_or_null

        # status for child: mostly valid, sometimes invalid
        child_status = st.one_of(
            st.sampled_from(valid_statuses),
            st.sampled_from(invalid_statuses),
        )

        # tags for child: mostly valid lists of strings, sometimes invalid
        child_tags = st.one_of(
            valid_tags,
            st.lists(st.one_of(tag_str, invalid_tag_element), min_size=1, max_size=5),
        )

        return st.fixed_dictionaries({
            "id": child_id,
            "amount": child_amount,
            "name": child_name,
            "status": child_status,
            "tags": child_tags,
            "child": child_val,
        })

    # Compose the top-level record
    top_level_record = st.fixed_dictionaries({
        "id": id_candidates,
        "amount": amount_str,
        "name": name_str_or_null,
        "status": status_str,
        "tags": tags_candidates,
        "child": st.one_of(st.none(), record(0)),
    })

    # Now we must convert the generated dict to JSON text bytes manually,
    # using string concatenation and Hypothesis .map()/.flatmap() transforms.
    # We must produce syntactically valid JSON objects only.

    # Helper to JSON-encode a string (escape quotes and backslashes)
    def json_string(s: str) -> str:
        # minimal escaping for JSON string
        # replace \ with \\, " with \"
        # also escape control chars \b \f \n \r \t
        # Hypothesis strings can contain unicode, but JSON allows unicode directly except control chars
        # We'll do minimal escaping for control chars
        replacements = {
            '\\': '\\\\',
            '"': '\\"',
            '\b': '\\b',
            '\f': '\\f',
            '\n': '\\n',
            '\r': '\\r',
            '\t': '\\t',
        }
        res = []
        for c in s:
            if c in replacements:
                res.append(replacements[c])
            elif ord(c) < 0x20:
                # control char, escape as \u00XX
                res.append('\\u%04x' % ord(c))
            else:
                res.append(c)
        return '"' + ''.join(res) + '"'

    # Helper to JSON-encode a value (string, int, float, bool, None, list, dict)
    # We only need to encode the record structure we produce:
    # - int, float (for id)
    # - string (amount, name, status, tags elements)
    # - None (null)
    # - list of strings or mixed (tags)
    # - dict (record)
    def json_encode(value):
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, int):
            return str(value)
        elif isinstance(value, float):
            # JSON floats must not be NaN or Infinity (Hypothesis filters these)
            # Use repr to get shortest decimal representation
            # but ensure decimal point or exponent present for floats
            s = repr(value)
            if 'e' not in s and '.' not in s:
                s += '.0'
            return s
        elif isinstance(value, str):
            return json_string(value)
        elif isinstance(value, list):
            return "[" + ",".join(json_encode(v) for v in value) + "]"
        elif isinstance(value, dict):
            # keys are always strings
            items = []
            for k, v in value.items():
                items.append(json_string(k) + ":" + json_encode(v))
            return "{" + ",".join(items) + "}"
        else:
            # Should not happen
            raise ValueError("Unsupported type for JSON encoding: %r" % type(value))

    # Draw the top-level record dict
    record_dict = draw(top_level_record)

    # Encode to JSON string
    json_text = json_encode(record_dict)

    # Return bytes
    return json_text.encode("utf-8")