from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum status
    valid_statuses = ["active", "inactive", "unknown"]
    # Also include invalid variants to try to provoke divergence
    # but only one or two fields off at a time to keep near-valid documents.
    # We'll pick one field to "corrupt" per generated document.

    # Helper: generate a valid "id" field (integer)
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))

    # Helper: generate a valid "amount" field (string)
    # Use decimal strings, but sometimes empty or zero to test boundaries
    amount_val = draw(st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s)),
        st.just("0"),
        st.just("0.0"),
        st.just("123.45"),
    ))

    # Helper: generate a valid or null "name" field
    # name is nullable string
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))

    # Helper: generate a valid "status" field (enum)
    # Mostly valid, but sometimes invalid or case variants to test enum parsing
    status_val = draw(st.one_of(
        st.sampled_from(valid_statuses),
        st.sampled_from(["ACTIVE", "Invalid", "unknown "]),  # invalid variants
    ))

    # Helper: generate a valid "tags" array of strings
    # Sometimes empty, sometimes with one or two tags
    tags_val = draw(st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=3))

    # Helper: generate a valid or null "child" field (one level recursion)
    # We'll generate a valid child record or null
    # To keep recursion bounded, child cannot have child itself (child.child=null)
    def gen_child():
        child_id = draw(st.integers(min_value=0, max_value=2**31-1))
        child_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s)))
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        child_status = draw(st.sampled_from(valid_statuses))
        child_tags = draw(st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=3))
        # child.child is always null to keep one-level recursion
        child_child = None

        # Compose child JSON text
        # We will build JSON text manually, escaping strings minimally (only backslash and quote)
        def json_escape(s):
            return s.replace("\\", "\\\\").replace('"', '\\"')

        child_name_json = "null" if child_name is None else '"' + json_escape(child_name) + '"'
        child_tags_json = "[" + ",".join('"' + json_escape(t) + '"' for t in child_tags) + "]"
        child_child_json = "null"

        child_json = (
            '{'
            f'"id":{child_id},'
            f'"amount":"{child_amount}",'
            f'"name":{child_name_json},'
            f'"status":"{child_status}",'
            f'"tags":{child_tags_json},'
            f'"child":{child_child_json}'
            '}'
        )
        return child_json

    # Compose top-level JSON text similarly
    def json_escape(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    # We will produce a near-valid document, but with exactly one "corruption" to provoke divergence.
    # Choose one field to corrupt or omit or type-mutate:
    corruption_field = draw(st.sampled_from(["none", "id_null", "id_missing", "amount_number", "amount_null",
                                             "amount_missing", "status_invalid", "status_case", "status_null",
                                             "tags_null", "tags_missing", "tags_nonstring", "child_missing",
                                             "child_null", "child_invalid_id_null", "child_invalid_amount_null",
                                             "child_invalid_status_invalid", "child_invalid_tags_nonstring",
                                             "name_null", "name_nonstring"]))

    # Start with all fields present and valid
    id_json = str(id_val)
    amount_json = '"' + json_escape(amount_val) + '"'
    name_json = "null" if name_val is None else '"' + json_escape(name_val) + '"'
    status_json = '"' + status_val + '"'
    tags_json = "[" + ",".join('"' + json_escape(t) + '"' for t in tags_val) + "]"
    child_json = gen_child()

    # Apply corruption:
    # For missing fields, we omit the key entirely.
    # For null fields, we set null.
    # For wrong types, we set wrong JSON types.
    # For invalid enum, we set invalid string.
    # For child invalid fields, we replace child JSON with a child having that invalid field.

    # Helper to produce child JSON with one invalid field
    def child_with_invalid(field):
        # base valid child fields
        c_id = id_val
        c_amount = amount_val
        c_name = name_val
        c_status = valid_statuses[0]
        c_tags = tags_val if tags_val else ["tag1"]
        c_child = None

        def json_escape(s):
            return s.replace("\\", "\\\\").replace('"', '\\"')

        # Override invalid field
        if field == "id_null":
            c_id_json = "null"
        else:
            c_id_json = str(c_id)

        if field == "amount_null":
            c_amount_json = "null"
        else:
            c_amount_json = '"' + json_escape(c_amount) + '"'

        if field == "status_invalid":
            c_status_json = '"invalid"'
        else:
            c_status_json = '"' + c_status + '"'

        if field == "tags_nonstring":
            # Insert a non-string element in tags array
            c_tags_json = "[" + ",".join('"' + json_escape(t) + '"' for t in c_tags) + ",123]"
        else:
            c_tags_json = "[" + ",".join('"' + json_escape(t) + '"' for t in c_tags) + "]"

        c_name_json = "null" if c_name is None else '"' + json_escape(c_name) + '"'
        c_child_json = "null"

        child_obj = (
            '{'
            f'"id":{c_id_json},'
            f'"amount":{c_amount_json},'
            f'"name":{c_name_json},'
            f'"status":{c_status_json},'
            f'"tags":{c_tags_json},'
            f'"child":{c_child_json}'
            '}'
        )
        return child_obj

    # Now apply corruption_field
    fields = {}

    # id field
    if corruption_field == "id_missing":
        pass  # omit id
    elif corruption_field == "id_null":
        fields["id"] = "null"
    else:
        fields["id"] = id_json

    # amount field
    if corruption_field == "amount_missing":
        pass
    elif corruption_field == "amount_null":
        fields["amount"] = "null"
    elif corruption_field == "amount_number":
        # amount as number (known to be rejected by all)
        # Use a number instead of string
        fields["amount"] = "12345"
    else:
        fields["amount"] = amount_json

    # name field
    if corruption_field == "name_nonstring":
        # name as number (should be string or null)
        fields["name"] = "123"
    else:
        fields["name"] = name_json

    # status field
    if corruption_field == "status_invalid":
        fields["status"] = '"invalid"'
    elif corruption_field == "status_case":
        # uppercase variant
        fields["status"] = '"ACTIVE"'
    elif corruption_field == "status_null":
        fields["status"] = "null"
    else:
        fields["status"] = status_json

    # tags field
    if corruption_field == "tags_missing":
        pass
    elif corruption_field == "tags_null":
        fields["tags"] = "null"
    elif corruption_field == "tags_nonstring":
        # tags array with a non-string element
        fields["tags"] = '["tag1", 123]'
    else:
        fields["tags"] = tags_json

    # child field
    if corruption_field == "child_missing":
        pass
    elif corruption_field == "child_null":
        fields["child"] = "null"
    elif corruption_field == "child_invalid_id_null":
        fields["child"] = child_with_invalid("id_null")
    elif corruption_field == "child_invalid_amount_null":
        fields["child"] = child_with_invalid("amount_null")
    elif corruption_field == "child_invalid_status_invalid":
        fields["child"] = child_with_invalid("status_invalid")
    elif corruption_field == "child_invalid_tags_nonstring":
        fields["child"] = child_with_invalid("tags_nonstring")
    else:
        fields["child"] = child_json

    # Compose JSON text from fields dict, preserving order of keys as per schema
    # id, amount, name, status, tags, child
    keys_order = ["id", "amount", "name", "status", "tags", "child"]
    json_parts = []
    for k in keys_order:
        if k in fields:
            json_parts.append(f'"{k}":{fields[k]}')

    json_text = "{" + ",".join(json_parts) + "}"

    # Return bytes
    return json_text.encode("utf-8")