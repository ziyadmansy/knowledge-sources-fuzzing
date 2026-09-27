from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for "status" field
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal from a Python string (with proper escaping)
    def json_string(s: str) -> str:
        # Minimal escaping for JSON string (backslash, quote, control chars)
        # Hypothesis strings are unicode, so escape backslash and quote and control chars
        def escape_char(c):
            o = ord(c)
            if c == '"':
                return '\\"'
            elif c == '\\':
                return '\\\\'
            elif c == '\b':
                return '\\b'
            elif c == '\f':
                return '\\f'
            elif c == '\n':
                return '\\n'
            elif c == '\r':
                return '\\r'
            elif c == '\t':
                return '\\t'
            elif o < 0x20:
                return '\\u%04x' % o
            else:
                return c
        return '"' + ''.join(escape_char(c) for c in s) + '"'

    # Recursive record generator with bounded depth (max 1 level of child)
    def record_json(depth=0):
        # id: integer
        id_val = draw(st.integers(min_value=0, max_value=2**31-1))
        id_json = str(id_val)

        # amount: string (any string)
        amount_val = draw(st.text(min_size=0, max_size=20))
        amount_json = json_string(amount_val)

        # name: string or null or missing (missing means omit the field)
        # To create divergence, sometimes omit "name" (all decode as null),
        # sometimes present as null, sometimes present as string.
        name_choice = draw(st.sampled_from(["missing", "null", "string"]))
        if name_choice == "missing":
            name_json = None
        elif name_choice == "null":
            name_json = "null"
        else:
            name_val = draw(st.text(min_size=0, max_size=20))
            name_json = json_string(name_val)

        # status: one of "active", "inactive", "unknown"
        # To create divergence, sometimes put a valid status, sometimes an invalid string (should be rejected by all)
        # But since invalid values rejected by all, no divergence there.
        # So always valid status to keep near well-formed.
        status_val = draw(st.sampled_from(statuses))
        status_json = json_string(status_val)

        # tags: array of strings normally
        # To create divergence:
        # built_value accepts null or object (decoded as empty list), others reject.
        # So sometimes tags=null, sometimes tags=object, sometimes tags=array of strings.
        tags_type = draw(st.sampled_from(["array", "null", "object"]))
        if tags_type == "array":
            # array of strings (possibly empty)
            tags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
            # all elements must be strings, no non-string elements
            tags_json = "[" + ",".join(json_string(t) for t in tags_list) + "]"
        elif tags_type == "null":
            tags_json = "null"
        else:
            # object with some string keys and string values (non-array)
            # keys and values are strings
            obj_size = draw(st.integers(min_value=0, max_value=3))
            obj_items = []
            for _ in range(obj_size):
                k = draw(st.text(min_size=1, max_size=10))
                v = draw(st.text(min_size=0, max_size=10))
                obj_items.append(json_string(k) + ":" + json_string(v))
            tags_json = "{" + ",".join(obj_items) + "}"

        # child: null or a valid record (one level recursion only)
        # To create divergence, sometimes child=null, sometimes child=valid record,
        # sometimes child=empty object (rejected by all),
        # sometimes child=array (rejected by all),
        # sometimes child with missing required fields (rejected by all).
        child_type = draw(st.sampled_from(["null", "record", "empty_object", "array", "missing_fields"]))
        if depth >= 1:
            # no further recursion, only null allowed
            child_type = "null"
        if child_type == "null":
            child_json = "null"
        elif child_type == "record":
            child_json = record_json(depth=depth+1)
        elif child_type == "empty_object":
            child_json = "{}"
        elif child_type == "array":
            child_json = "[]"
        else:  # missing_fields
            # produce an object missing one or more required fields (id, amount, status, tags)
            # name is optional, child is optional (?), but child is required (?), spec says all six fields always present in well-formed
            # So omit one required field to cause rejection
            # We'll omit "id" here
            # Compose partial record with all fields except "id"
            # amount
            amount_c = draw(st.text(min_size=0, max_size=20))
            amount_c_json = json_string(amount_c)
            # name optional, present as null
            name_c_json = "null"
            # status valid
            status_c_json = json_string(draw(st.sampled_from(statuses)))
            # tags array of strings
            tags_c_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=3))
            tags_c_json = "[" + ",".join(json_string(t) for t in tags_c_list) + "]"
            # child null
            child_c_json = "null"
            # Compose object missing "id"
            child_json = (
                "{" +
                '"amount":' + amount_c_json + "," +
                '"name":' + name_c_json + "," +
                '"status":' + status_c_json + "," +
                '"tags":' + tags_c_json + "," +
                '"child":' + child_c_json +
                "}"
            )

        # Compose top-level record JSON object
        # Fields: id, amount, name (optional), status, tags, child
        fields = []
        fields.append('"id":' + id_json)
        fields.append('"amount":' + amount_json)
        if name_json is not None:
            fields.append('"name":' + name_json)
        fields.append('"status":' + status_json)
        fields.append('"tags":' + tags_json)
        fields.append('"child":' + child_json)

        obj_json = "{" + ",".join(fields) + "}"
        return obj_json

    # Draw the top-level record JSON string
    json_str = draw(record_json(depth=0))
    # Return as bytes
    return json_str.encode("utf-8")