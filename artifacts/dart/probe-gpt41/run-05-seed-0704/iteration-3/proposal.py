from hypothesis import strategies as st

# Allowed values for "status"
_status_values = st.sampled_from(["active", "inactive", "unknown"])

# Helper to produce a JSON string literal from a Python string (no escapes needed for this task)
def json_string(s: str) -> str:
    # Minimal escaping for quotes and backslashes
    # Hypothesis strings are unicode, but we keep it simple: only ASCII printable, no control chars
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + s + '"'

# Helper to produce JSON array of strings from list of strings
def json_array_of_strings(lst):
    return "[" + ",".join(json_string(s) for s in lst) + "]"

# Compose a JSON record string from fields dict (keys and values are strings already JSON encoded)
def json_object(fields):
    # fields is list of (key_json, value_json) pairs
    return "{" + ",".join(k + ":" + v for k, v in fields) + "}"

@st.composite
def generated_json(draw) -> bytes:
    # We produce a JSON object string with the six fields:
    # "id": integer
    # "amount": string
    # "name": string or null (or missing sometimes)
    # "status": one of allowed strings, or null, or invalid string, or missing
    # "tags": array of strings, or missing, or object (to trigger known divergence)
    # "child": null or nested record or invalid type (string, array, empty object)
    #
    # Strategy: mostly well-formed, but vary one or two fields subtly to trigger divergences.
    # We produce a dict of fields as strings (already JSON encoded).
    #
    # We allow missing "name" and "tags" sometimes (to test missing vs present),
    # and "tags" as object sometimes (to trigger D_built_value acceptance vs others reject).
    # We allow "status" null or invalid string sometimes.
    # We allow "child" null, valid nested record, or invalid types sometimes.
    #
    # We keep recursion depth bounded to 1 (child can have child=null only).
    #
    # We produce the JSON text and encode as UTF-8 bytes.

    # id: integer
    id_val = draw(st.integers(min_value=0, max_value=1000000))
    id_json = '"id":' + str(id_val)

    # amount: string (nonempty ascii digits or decimal)
    amount_str = draw(st.text(min_size=1, max_size=10, alphabet="0123456789."))
    amount_json = '"amount":' + json_string(amount_str)

    # name: string or null or missing (missing triggers rejection in A/B/C, accepted as null in D)
    # We'll pick one of: present string, present null, missing
    name_choice = draw(st.sampled_from(["present_string", "present_null", "missing"]))
    if name_choice == "present_string":
        name_val = draw(st.text(min_size=0, max_size=20))
        name_json = '"name":' + json_string(name_val)
        name_field = name_json
    elif name_choice == "present_null":
        name_field = '"name":null'
    else:
        # missing name field
        name_field = None

    # status: one of allowed strings, or null, or invalid string, or missing
    # missing triggers rejection in A/B/C/D (all reject missing status)
    # null triggers different exceptions (known)
    # invalid string triggers different exceptions
    status_choice = draw(st.sampled_from(["valid", "null", "invalid", "missing"]))
    if status_choice == "valid":
        status_val = draw(_status_values)
        status_field = '"status":' + json_string(status_val)
    elif status_choice == "null":
        status_field = '"status":null'
    elif status_choice == "invalid":
        # invalid string not in allowed set
        invalid_str = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ["active", "inactive", "unknown"]))
        status_field = '"status":' + json_string(invalid_str)
    else:
        # missing status field
        status_field = None

    # tags: array of strings, or missing, or object (to trigger D_built_value acceptance)
    # missing accepted only by D_built_value, rejected by others
    # object accepted only by D_built_value, rejected by others
    # array of strings accepted by all
    tags_choice = draw(st.sampled_from(["array", "missing", "object"]))
    if tags_choice == "array":
        # array of 0-3 strings
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10), max_size=3))
        tags_field = '"tags":' + json_array_of_strings(tags_list)
    elif tags_choice == "missing":
        tags_field = None
    else:
        # object (empty or with some keys)
        # To keep it simple, empty object {}
        tags_field = '"tags":{}'

    # child: null, valid nested record, or invalid type (string, array, empty object)
    # invalid types trigger rejection by all except D throws DeserializationError
    # valid nested record: same schema but child=null only (to keep recursion bounded)
    child_choice = draw(st.sampled_from(["null", "valid_nested", "string", "array", "empty_object"]))
    if child_choice == "null":
        child_field = '"child":null'
    elif child_choice == "valid_nested":
        # nested record with child=null only, and all fields well-formed
        # id: integer
        nid = draw(st.integers(min_value=0, max_value=1000000))
        namount = draw(st.text(min_size=1, max_size=10, alphabet="0123456789."))
        nname = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        nstatus = draw(_status_values)
        ntags = draw(st.lists(st.text(min_size=1, max_size=10), max_size=3))
        # child=null
        nested_fields = [
            ('"id"', str(nid)),
            ('"amount"', json_string(namount)),
            ('"name"', 'null' if nname is None else json_string(nname)),
            ('"status"', json_string(nstatus)),
            ('"tags"', json_array_of_strings(ntags)),
            ('"child"', 'null'),
        ]
        nested_json = "{" + ",".join(k + ":" + v for k, v in nested_fields) + "}"
        child_field = '"child":' + nested_json
    elif child_choice == "string":
        child_field = '"child":"not_a_record"'
    elif child_choice == "array":
        child_field = '"child":["not","a","record"]'
    else:
        child_field = '"child":{}'

    # Compose fields list, skipping missing ones
    fields = [id_json, amount_json]
    if name_field is not None:
        fields.append(name_field)
    if status_field is not None:
        fields.append(status_field)
    if tags_field is not None:
        fields.append(tags_field)
    fields.append(child_field)

    # Compose JSON object string
    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")