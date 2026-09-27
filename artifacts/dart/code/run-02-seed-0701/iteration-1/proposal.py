from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslashes only (minimal)
def json_escape(s: str) -> str:
    # Minimal escaping: backslash and double quote
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects matching the record schema,
    with small, targeted variations to provoke behavioral divergence among
    four Dart JSON deserializers.

    Variations focus on:
    - id: int vs integral float (e.g. 1 vs 1.0)
    - amount: string exact
    - name: string or null or missing (missing treated as null)
    - status: exact enum strings or unknown strings (to provoke enum decode errors)
    - tags: array of strings, but sometimes empty or with non-string element (to provoke rejection)
    - child: null or nested record or present but not object (to provoke rejection)
    """

    # --- id field ---
    # Manual requires int exact; others accept integral float (e.g. 1.0)
    # So generate either int or integral float (num with zero fractional)
    id_is_float = draw(st.booleans())
    if id_is_float:
        # integral float as string (e.g. 1.0)
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_json = f"{id_val}.0"
    else:
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_json = str(id_val)

    # --- amount field ---
    # Must be string exact, no coercion
    # Use simple decimal strings, but sometimes empty or "0"
    amount_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c == '.' for c in s)))
    amount_json = '"' + json_escape(amount_val) + '"'

    # --- name field ---
    # Manual and json_serializable/freezed accept null or string
    # built_value omits null on serialization but accepts null if present
    # Also test missing name (treated as null by all)
    name_choice = draw(st.sampled_from(['string', 'null', 'missing']))
    if name_choice == 'string':
        # simple ascii string or unicode
        name_val = draw(st.text(min_size=1, max_size=20))
        name_json = '"' + json_escape(name_val) + '"'
        name_field = f'"name":{name_json}'
    elif name_choice == 'null':
        name_field = '"name":null'
    else:
        # missing name field
        name_field = None

    # --- status field ---
    # Enum exact match: "active", "inactive", "unknown"
    # Try valid or invalid strings to provoke enum decode errors
    status_valid = draw(st.booleans())
    if status_valid:
        status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
    else:
        # invalid enum string (case variant or unknown)
        invalid_statuses = ["Active", "INACTIVE", "unknowns", "disabled", "null", ""]  # some invalid variants
        status_val = draw(st.sampled_from(invalid_statuses))
    status_json = '"' + json_escape(status_val) + '"'

    # --- tags field ---
    # Must be non-null array of strings
    # Try mostly valid arrays, but sometimes inject a non-string element or empty array
    tags_choice = draw(st.sampled_from(['valid', 'empty', 'nonstring']))
    if tags_choice == 'valid':
        # non-empty list of strings
        tags_len = draw(st.integers(min_value=1, max_value=5))
        tags_vals = draw(st.lists(st.text(min_size=1, max_size=10), min_size=tags_len, max_size=tags_len))
        tags_json = '[' + ','.join('"' + json_escape(t) + '"' for t in tags_vals) + ']'
    elif tags_choice == 'empty':
        # empty array (should be accepted by all? Actually, spec says non-null, but empty allowed)
        tags_json = '[]'
    else:
        # non-string element injected
        tags_len = draw(st.integers(min_value=1, max_value=4))
        tags_vals = draw(st.lists(st.text(min_size=1, max_size=10), min_size=tags_len, max_size=tags_len))
        # replace one element with a number or null or bool
        idx = draw(st.integers(min_value=0, max_value=tags_len - 1))
        nonstring_val = draw(st.sampled_from(['null', 'true', 'false', '123', '12.3']))
        tags_vals_json = []
        for i, v in enumerate(tags_vals):
            if i == idx:
                tags_vals_json.append(nonstring_val)
            else:
                tags_vals_json.append('"' + json_escape(v) + '"')
        tags_json = '[' + ','.join(tags_vals_json) + ']'

    # --- child field ---
    # null or nested record or present but not object (to provoke rejection)
    # Limit recursion depth to 1 (one level)
    def gen_child(level=0):
        # At level 1, only null or valid record (no further recursion)
        if level >= 1:
            # null or valid record with child=null
            child_null = draw(st.booleans())
            if child_null:
                return 'null'
            else:
                # valid record with child=null
                # reuse fields but child=null
                # id int only here for simplicity
                child_id = draw(st.integers(min_value=0, max_value=1000))
                child_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c == '.' for c in s)))
                child_name_choice = draw(st.sampled_from(['string', 'null', 'missing']))
                if child_name_choice == 'string':
                    child_name_val = draw(st.text(min_size=1, max_size=20))
                    child_name_field = f'"name":"{json_escape(child_name_val)}"'
                elif child_name_choice == 'null':
                    child_name_field = '"name":null'
                else:
                    child_name_field = None
                child_status = draw(st.sampled_from(["active", "inactive", "unknown"]))
                child_tags_len = draw(st.integers(min_value=1, max_value=3))
                child_tags_vals = draw(st.lists(st.text(min_size=1, max_size=10), min_size=child_tags_len, max_size=child_tags_len))
                child_tags_json = '[' + ','.join('"' + json_escape(t) + '"' for t in child_tags_vals) + ']'

                parts = [f'"id":{child_id}', f'"amount":"{json_escape(child_amount)}"']
                if child_name_field is not None:
                    parts.append(child_name_field)
                parts.append(f'"status":"{child_status}"')
                parts.append(f'"tags":{child_tags_json}')
                parts.append(f'"child":null')
                return '{' + ','.join(parts) + '}'
        else:
            # level 0: child can be null, valid record, or invalid type (string/number/array)
            child_type = draw(st.sampled_from(['null', 'record', 'invalid']))
            if child_type == 'null':
                return 'null'
            elif child_type == 'record':
                # recurse with level+1
                return gen_child(level=1)
            else:
                # invalid type: string, number, bool, array
                invalid_val = draw(st.sampled_from([
                    '"not an object"',
                    '123',
                    '12.3',
                    'true',
                    'false',
                    '[]',
                    '[1,2,3]',
                    '"{}"',
                ]))
                return invalid_val

    child_json = gen_child(level=0)

    # Compose fields in order id, amount, name?, status, tags, child
    fields = [f'"id":{id_json}', f'"amount":{amount_json}']
    if name_field is not None:
        fields.append(name_field)
    fields.append(f'"status":{status_json}')
    fields.append(f'"tags":{tags_json}')
    fields.append(f'"child":{child_json}')

    json_text = '{' + ','.join(fields) + '}'
    return json_text.encode('utf-8')