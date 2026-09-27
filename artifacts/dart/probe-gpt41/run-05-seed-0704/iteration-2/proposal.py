from hypothesis import strategies as st

# Allowed values for "status"
_status_values = st.sampled_from(["active", "inactive", "unknown"])

# Helper to produce a JSON string literal from a Python string,
# escaping backslash and double quote minimally.
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote for JSON string
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.
    """

    # We implement bounded recursion for "child" field: max depth 1 (child can have no child)
    # So we define an inner function to generate a record JSON string at given depth.
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # id: integer
        # amount: string
        # name: string or null or missing (to test missing name)
        # status: one of allowed strings, or null (to test null status)
        # tags: array of strings, or missing, or object (to test divergence)
        # child: null or record (depth < 1) or invalid types (to test rejection)
        #
        # We produce a dict of fields as strings (key and value as JSON text),
        # then join with commas inside braces.

        # id: always integer (to avoid trivial rejection)
        id_val = draw(st.integers(min_value=0, max_value=10**9))
        id_json = '"id":' + str(id_val)

        # amount: always string (to avoid trivial rejection)
        # Use decimal-like strings, or edge cases like empty string or "0"
        amount_str = draw(st.one_of(
            st.just("0"),
            st.just(""),
            st.from_regex(r"[0-9]+(\.[0-9]+)?", fullmatch=True),
            st.text(min_size=1, max_size=5).filter(lambda s: all(c.isdigit() or c == '.' for c in s))
        ))
        amount_json = '"amount":' + json_string_literal(amount_str)

        # name: string or null or missing (missing tests)
        # We bias towards present name (string or null), but sometimes omit
        name_option = draw(st.sampled_from(["present_string", "present_null", "missing"]))
        if name_option == "present_string":
            # string name, possibly empty or with special chars
            name_str = draw(st.text(max_size=10))
            name_json = '"name":' + json_string_literal(name_str)
            name_field = name_json
        elif name_option == "present_null":
            name_field = '"name":null'
        else:
            # missing name field
            name_field = None

        # status: one of allowed strings, or null (to test null status)
        # Also test invalid strings rarely to provoke rejection
        status_option = draw(st.sampled_from(["valid", "null", "invalid_string"]))
        if status_option == "valid":
            status_val = draw(_status_values)
            status_json = '"status":' + json_string_literal(status_val)
        elif status_option == "null":
            status_json = '"status":null'
        else:
            # invalid string, e.g. "actve" (typo), or empty string
            invalid_status = draw(st.one_of(
                st.just(""),
                st.text(min_size=1, max_size=10).filter(lambda s: s not in {"active", "inactive", "unknown"})
            ))
            status_json = '"status":' + json_string_literal(invalid_status)

        # tags: array of strings, or missing, or object (to test divergence)
        # We bias towards present array of strings, but sometimes missing or object
        tags_option = draw(st.sampled_from(["present_array", "missing", "object"]))
        if tags_option == "present_array":
            # array of strings, possibly empty, possibly with empty strings
            tags_list = draw(st.lists(st.text(max_size=5), max_size=5))
            # encode as JSON array of strings
            tags_json = '"tags":[' + ",".join(json_string_literal(t) for t in tags_list) + ']'
        elif tags_option == "missing":
            tags_json = None
        else:
            # object instead of array, empty or with string keys
            obj_keys = draw(st.lists(st.text(min_size=1, max_size=5), max_size=3))
            obj_items = []
            for k in obj_keys:
                # values as strings
                v = draw(st.text(max_size=5))
                obj_items.append(json_string_literal(k) + ":" + json_string_literal(v))
            tags_json = '"tags":{' + ",".join(obj_items) + '}'

        # child: null or record (depth < 1) or invalid types (string, array, empty object)
        # We bias towards valid null or valid record child, but sometimes invalid types
        child_option = draw(st.sampled_from(["null", "valid_record", "string", "array", "empty_object"]))
        if child_option == "null":
            child_json = '"child":null'
        elif child_option == "valid_record" and depth == 0:
            # recurse once only
            child_rec = draw(record_json(depth + 1))
            child_json = '"child":' + child_rec
        elif child_option == "string":
            # invalid type: string
            child_json = '"child":' + json_string_literal(draw(st.text(max_size=10)))
        elif child_option == "array":
            # invalid type: array of strings
            arr = draw(st.lists(st.text(max_size=5), max_size=3))
            child_json = '"child":[' + ",".join(json_string_literal(s) for s in arr) + ']'
        else:
            # empty object
            child_json = '"child":{}'

        # Compose fields, skipping None
        fields = [id_json, amount_json]
        if name_field is not None:
            fields.append(name_field)
        fields.append(status_json)
        if tags_json is not None:
            fields.append(tags_json)
        fields.append(child_json)

        # Shuffle fields order to avoid positional bias
        fields = draw(st.permutations(fields))

        json_obj = "{" + ",".join(fields) + "}"
        return st.just(json_obj)

    # Draw top-level record JSON string
    rec = draw(record_json(0))
    # Return as bytes
    return rec.encode("utf-8")