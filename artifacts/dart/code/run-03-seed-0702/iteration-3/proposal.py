from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum status
    statuses = ["active", "inactive", "unknown"]
    # We will produce JSON text manually, carefully quoting strings and formatting arrays/objects.
    # We produce a record with fields: id, amount, name, status, tags, child
    # We allow one or two fields to be "off" to maximize divergence.
    # We do bounded recursion for child (max depth 1).
    # We produce syntactically valid JSON only.

    def json_string(s: str) -> str:
        # Minimal JSON string escaper for double quotes and backslash
        # and control chars \b\f\n\r\t
        # We do not need full unicode escaping, just basics.
        esc_map = {
            '\\': '\\\\',
            '"': '\\"',
            '\b': '\\b',
            '\f': '\\f',
            '\n': '\\n',
            '\r': '\\r',
            '\t': '\\t',
        }
        return '"' + ''.join(esc_map.get(c, c) for c in s) + '"'

    # id field:
    # Manual requires int exactly (no float 1.0)
    # json_serializable/freezed accept float 1.0 and convert to int
    # built_value expects int (likely rejects float)
    # So we produce either int or float with .0 to cause divergence.
    # Also try string id to cause manual to reject.
    id_type = draw(st.sampled_from(["int", "float", "string"]))
    if id_type == "int":
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_json = str(id_val)
    elif id_type == "float":
        # float with .0 to look like float but integral value
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_json = str(float(id_val))  # e.g. "1.0"
    else:
        # string id to cause manual to reject
        id_val = draw(st.text(min_size=1, max_size=5))
        id_json = json_string(id_val)

    # amount field:
    # manual requires string exactly
    # others likely accept string only
    # We try string or number (number should cause manual reject)
    amount_type = draw(st.sampled_from(["string", "number"]))
    if amount_type == "string":
        amount_val = draw(st.text(min_size=1, max_size=10))
        amount_json = json_string(amount_val)
    else:
        # number (int or float)
        amount_val = draw(st.one_of(st.integers(min_value=0, max_value=10000),
                                   st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)))
        # format floats carefully
        if isinstance(amount_val, float):
            amount_json = repr(amount_val)
        else:
            amount_json = str(amount_val)

    # name field:
    # nullable string or null
    # built_value accepts missing or null
    # manual/json_serializable/freezed accept null or string
    # We produce either string, null, or omit (omit only for built_value acceptance)
    # But spec says all six fields always present in well-formed document,
    # so omit only to cause divergence.
    name_option = draw(st.sampled_from(["string", "null", "omit"]))
    if name_option == "string":
        name_val = draw(st.text(min_size=0, max_size=10))
        name_json = json_string(name_val)
        name_present = True
    elif name_option == "null":
        name_json = "null"
        name_present = True
    else:
        # omit field
        name_present = False

    # status field:
    # manual uses Enum.values.byName throwing raw ArgumentError on unknown strings
    # json_serializable/freezed throw CheckedFromJsonException with clear messages
    # built_value throws ArgumentError wrapped in BuiltValueNestedFieldError if nested
    # So produce either valid enum string or unknown string to cause divergence
    status_option = draw(st.sampled_from(["valid", "invalid"]))
    if status_option == "valid":
        status_val = draw(st.sampled_from(statuses))
    else:
        # invalid enum string, not in statuses
        # use a string not in statuses
        invalid_statuses = ["activ", "inactiv", "unknwn", "none", "123"]
        status_val = draw(st.sampled_from(invalid_statuses))
    status_json = json_string(status_val)

    # tags field:
    # manual casts tags as List then maps elements as String with e as String, rejecting non-string tags
    # json_serializable/freezed cast tags as List<dynamic> then map
    # built_value expects BuiltList<String> and uses serializers.deserialize, rejecting non-string lists differently
    # So produce tags as list of strings or list with one non-string element to cause divergence
    tags_type = draw(st.sampled_from(["all_strings", "one_non_string"]))
    if tags_type == "all_strings":
        tags_len = draw(st.integers(min_value=0, max_value=5))
        tags_vals = draw(st.lists(st.text(min_size=0, max_size=10), min_size=tags_len, max_size=tags_len))
        tags_json = "[" + ",".join(json_string(t) for t in tags_vals) + "]"
    else:
        # one non-string element in tags
        # produce mostly strings but one element is int or bool or null
        tags_len = draw(st.integers(min_value=1, max_value=5))
        # position of non-string element
        non_str_pos = draw(st.integers(min_value=0, max_value=tags_len - 1))
        tags_vals = []
        for i in range(tags_len):
            if i == non_str_pos:
                non_str_val = draw(st.one_of(st.integers(min_value=0, max_value=100),
                                            st.booleans(),
                                            st.just(None)))
                if non_str_val is None:
                    tags_vals.append("null")
                elif isinstance(non_str_val, bool):
                    tags_vals.append("true" if non_str_val else "false")
                else:
                    tags_vals.append(str(non_str_val))
            else:
                s = draw(st.text(min_size=0, max_size=10))
                tags_vals.append(json_string(s))
        tags_json = "[" + ",".join(tags_vals) + "]"

    # child field:
    # nullable record or null
    # built_value requires deserialization via serializers.deserialize as BvRecord, rejecting invalid nested objects
    # manual and json_serializable/freezed accept null or nested record
    # We produce either null or a nested record with one level recursion
    # To cause divergence, nested record can have one field off (like id float vs int, or invalid enum)
    child_option = draw(st.sampled_from(["null", "nested"]))
    if child_option == "null":
        child_json = "null"
    else:
        # nested record with one field off or all correct
        # We reuse the same logic but limit recursion depth to 1
        # To avoid infinite recursion, nested child.child is always null
        # We produce nested record JSON text here

        # Nested id type: choose from int or float (string id unlikely to cause new divergence here)
        nested_id_type = draw(st.sampled_from(["int", "float"]))
        if nested_id_type == "int":
            nested_id_val = draw(st.integers(min_value=0, max_value=1000))
            nested_id_json = str(nested_id_val)
        else:
            nested_id_val = draw(st.integers(min_value=0, max_value=1000))
            nested_id_json = str(float(nested_id_val))

        # Nested amount always string (to keep nested mostly valid)
        nested_amount_val = draw(st.text(min_size=1, max_size=10))
        nested_amount_json = json_string(nested_amount_val)

        # Nested name nullable string or null
        nested_name_option = draw(st.sampled_from(["string", "null"]))
        if nested_name_option == "string":
            nested_name_val = draw(st.text(min_size=0, max_size=10))
            nested_name_json = json_string(nested_name_val)
            nested_name_present = True
        else:
            nested_name_json = "null"
            nested_name_present = True

        # Nested status valid or invalid
        nested_status_option = draw(st.sampled_from(["valid", "invalid"]))
        if nested_status_option == "valid":
            nested_status_val = draw(st.sampled_from(statuses))
        else:
            invalid_statuses = ["activ", "inactiv", "unknwn", "none", "123"]
            nested_status_val = draw(st.sampled_from(invalid_statuses))
        nested_status_json = json_string(nested_status_val)

        # Nested tags all strings (to keep nested mostly valid)
        nested_tags_len = draw(st.integers(min_value=0, max_value=3))
        nested_tags_vals = draw(st.lists(st.text(min_size=0, max_size=10), min_size=nested_tags_len, max_size=nested_tags_len))
        nested_tags_json = "[" + ",".join(json_string(t) for t in nested_tags_vals) + "]"

        # Nested child always null (no deeper recursion)
        nested_child_json = "null"

        nested_fields = [
            '"id":' + nested_id_json,
            '"amount":' + nested_amount_json,
        ]
        if nested_name_present:
            nested_fields.append('"name":' + nested_name_json)
        nested_fields.extend([
            '"status":' + nested_status_json,
            '"tags":' + nested_tags_json,
            '"child":' + nested_child_json,
        ])
        child_json = "{" + ",".join(nested_fields) + "}"

    # Compose top-level fields
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
    ]
    if name_present:
        fields.append('"name":' + name_json)
    fields.append('"status":' + status_json)
    fields.append('"tags":' + tags_json)
    fields.append('"child":' + child_json)

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")