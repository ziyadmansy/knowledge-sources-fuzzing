from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum status
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal with proper escaping for " and \
    def json_string(s: str) -> str:
        # Minimal escaping for " and \ only, enough for test purposes
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id field:
    # Manual requires exact int (no float 1.0)
    # json_serializable/freezed accept integral floats (e.g. 1.0)
    # built_value likely requires exact int
    # So to cause divergence, sometimes produce integral float (e.g. 1.0), sometimes int
    id_type = draw(st.sampled_from(["int", "integral_float"]))
    if id_type == "int":
        # int as integer literal
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_json = str(id_val)
    else:
        # integral float, e.g. 1.0, 42.0
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_json = str(id_val) + ".0"

    # amount field: must be string, no coercion allowed anywhere
    # To cause divergence, always produce string (valid)
    amount_str = draw(st.text(min_size=1, max_size=10))
    amount_json = json_string(amount_str)

    # name field:
    # Manual and json_serializable/freezed accept null or string
    # built_value omits name if null but accepts null if present
    # Missing name treated as null by all
    # To cause divergence: sometimes omit name, sometimes present null, sometimes string
    name_choice = draw(st.sampled_from(["omit", "null", "string"]))
    if name_choice == "omit":
        name_json = None
    elif name_choice == "null":
        name_json = "null"
    else:
        # string or empty string allowed
        name_val = draw(st.one_of(st.none(), st.text(max_size=10)))
        # but none here means null, so treat none as null string
        if name_val is None:
            name_json = "null"
        else:
            name_json = json_string(name_val)

    # status field:
    # Enum exact case sensitive match required by all
    # Manual throws raw ArgumentError on unknown strings
    # json_serializable/freezed throw CheckedFromJsonException
    # built_value throws ArgumentError wrapped in BuiltValueNestedFieldError if nested
    # To cause divergence: sometimes produce valid enum, sometimes invalid string
    status_choice = draw(st.sampled_from(["valid", "invalid"]))
    if status_choice == "valid":
        status_val = draw(st.sampled_from(statuses))
        status_json = json_string(status_val)
    else:
        # invalid string: non-empty, no enum value, e.g. "Active" (wrong case), "invalid", "unknown " (trailing space)
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses))
        status_json = json_string(invalid_status)

    # tags field:
    # All reject missing or null tags
    # All reject non-string elements
    # Manual casts as List then each element as String
    # json_serializable/freezed cast as List<dynamic> then map to String
    # built_value expects non-null BuiltList<String>
    # To cause divergence: produce tags as array of strings (valid), or array with one non-string element (invalid)
    # or empty array (valid)
    tags_choice = draw(st.sampled_from(["valid_strings", "one_nonstring"]))
    if tags_choice == "valid_strings":
        # produce list of 0 to 5 strings
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
        # JSON array of strings
        tags_json = "[" + ",".join(json_string(t) for t in tags_list) + "]"
    else:
        # one non-string element inserted randomly in list of strings
        n = draw(st.integers(min_value=0, max_value=4))
        strings = draw(st.lists(st.text(min_size=0, max_size=10), min_size=n, max_size=n))
        # non-string element: number or boolean or null (null rejected by all)
        nonstring_val = draw(st.one_of(
            st.integers(min_value=-100, max_value=100).map(str),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: repr(f)),
            st.booleans().map(lambda b: "true" if b else "false"),
        ))
        # Insert non-string element at random position
        pos = draw(st.integers(min_value=0, max_value=n))
        elems = strings[:pos] + [nonstring_val] + strings[pos:]
        # Compose JSON array: strings quoted, non-string raw
        def elem_to_json(e):
            # if e is one of "true","false" or a number string, output raw else quoted
            if e in ("true", "false"):
                return e
            try:
                float(e)
                # if float parse succeeds, output raw
                return e
            except Exception:
                return json_string(e)
        tags_json = "[" + ",".join(elem_to_json(e) for e in elems) + "]"

    # child field:
    # Manual and json_serializable/freezed accept null or nested object
    # built_value requires null or valid BvRecord
    # If child present but not object/map, all reject
    # To cause divergence: sometimes omit child (treated as null?), sometimes null, sometimes nested object,
    # sometimes invalid type (string or number)
    child_choice = draw(st.sampled_from(["omit", "null", "valid", "invalid_type"]))

    # To avoid infinite recursion, limit recursion depth to 1 (only one level)
    # So nested child record will have child=null always
    def gen_child_json():
        # child record with child=null always
        # id: int or integral float (to cause divergence)
        child_id_type = draw(st.sampled_from(["int", "integral_float"]))
        if child_id_type == "int":
            cid_val = draw(st.integers(min_value=0, max_value=1000))
            cid_json = str(cid_val)
        else:
            cid_val = draw(st.integers(min_value=0, max_value=1000))
            cid_json = str(cid_val) + ".0"

        camount_str = draw(st.text(min_size=1, max_size=10))
        camount_json = json_string(camount_str)

        # name: omit, null, or string
        cname_choice = draw(st.sampled_from(["omit", "null", "string"]))
        if cname_choice == "omit":
            cname_json = None
        elif cname_choice == "null":
            cname_json = "null"
        else:
            cname_val = draw(st.text(max_size=10))
            cname_json = json_string(cname_val)

        cstatus_val = draw(st.sampled_from(statuses))
        cstatus_json = json_string(cstatus_val)

        ctags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=3))
        ctags_json = "[" + ",".join(json_string(t) for t in ctags_list) + "]"

        # child: always null at this level
        cchild_json = "null"

        # Compose child JSON object fields, omitting name if cname_json is None
        fields = [
            '"id":' + cid_json,
            '"amount":' + camount_json,
        ]
        if cname_json is not None:
            fields.append('"name":' + cname_json)
        fields.append('"status":' + cstatus_json)
        fields.append('"tags":' + ctags_json)
        fields.append('"child":' + cchild_json)
        return "{" + ",".join(fields) + "}"

    if child_choice == "omit":
        child_json = None
    elif child_choice == "null":
        child_json = "null"
    elif child_choice == "valid":
        child_json = gen_child_json()
    else:
        # invalid type: string or number or boolean
        child_json = draw(st.one_of(
            st.text(min_size=1, max_size=10).map(json_string),
            st.integers(min_value=-100, max_value=100).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
        ))

    # Compose top-level JSON object fields
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
    ]
    if name_json is not None:
        fields.append('"name":' + name_json)
    fields.append('"status":' + status_json)
    fields.append('"tags":' + tags_json)
    if child_json is not None:
        fields.append('"child":' + child_json)

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")