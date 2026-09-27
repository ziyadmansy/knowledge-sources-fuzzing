from hypothesis import strategies as st

# Helper: JSON string escape for a subset of ASCII (no control chars, no unicode escapes)
# We only generate simple strings without control chars or quotes to keep it simple.
def json_string(s: str) -> str:
    # Escape backslash and quote
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s + '"'

# Compose JSON array of strings
def json_array_of_strings(lst):
    return "[" + ",".join(json_string(x) for x in lst) + "]"

# Compose JSON enum string or null
def json_enum_or_null(val):
    if val is None:
        return "null"
    return json_string(val)

# Compose JSON integer or null
def json_int_or_null(val):
    if val is None:
        return "null"
    return str(val)

# Compose JSON string or null
def json_str_or_null(val):
    if val is None:
        return "null"
    return json_string(val)

# Compose JSON null or object or string or int or array or enum as string
# We will produce a record as JSON text recursively, with bounded depth.

@st.composite
def generated_json(draw, _depth=0):
    # Limit recursion depth to 1 for child (one level of recursion normally)
    # We produce a JSON text representing the record described.

    # id: integer or null or missing (to trigger divergences)
    # amount: string or number (to trigger coercion) or null or missing
    # name: string or null or missing
    # status: enum string ("active", "inactive", "unknown") or unknown string or null or missing
    # tags: array of strings or array of ints or null or missing
    # child: null or record or missing

    # We want to produce documents that are almost well-formed with one or two fields off.

    # Field presence: for each field, decide if present or missing (to trigger missing field divergences)
    # Use bias to produce mostly present fields, but sometimes missing or null or wrong type.

    # id field
    id_present = draw(st.booleans())
    if id_present:
        # id can be integer, null, or wrong type (string) to trigger divergences
        id_type = draw(st.sampled_from(["int", "null", "string"]))
        if id_type == "int":
            id_val = draw(st.integers(min_value=0, max_value=1000))
            id_json = str(id_val)
        elif id_type == "null":
            id_json = "null"
        else:
            # string instead of int
            id_val = draw(st.text(min_size=1, max_size=5))
            id_json = json_string(id_val)
    else:
        id_json = None

    # amount field
    amount_present = draw(st.booleans())
    if amount_present:
        # amount can be string, number, null, or missing
        amount_type = draw(st.sampled_from(["string", "number", "null"]))
        if amount_type == "string":
            amount_val = draw(st.text(min_size=1, max_size=10))
            amount_json = json_string(amount_val)
        elif amount_type == "number":
            amount_val = draw(st.integers(min_value=0, max_value=10000))
            amount_json = str(amount_val)
        else:
            amount_json = "null"
    else:
        amount_json = None

    # name field
    name_present = draw(st.booleans())
    if name_present:
        # name can be string or null or missing
        name_type = draw(st.sampled_from(["string", "null"]))
        if name_type == "string":
            name_val = draw(st.text(min_size=0, max_size=10))
            name_json = json_string(name_val)
        else:
            name_json = "null"
    else:
        name_json = None

    # status field
    status_present = draw(st.booleans())
    if status_present:
        # status can be valid enum, unknown enum (to trigger divergence), null
        status_type = draw(st.sampled_from(["valid", "unknown", "case_variant", "null"]))
        if status_type == "valid":
            status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
            status_json = json_string(status_val)
        elif status_type == "unknown":
            # unknown enum string (not in allowed set)
            status_val = draw(st.text(min_size=1, max_size=8).filter(lambda s: s not in {"active", "inactive", "unknown"}))
            status_json = json_string(status_val)
        elif status_type == "case_variant":
            # case variant of valid enum (e.g. "Active")
            status_val = draw(st.sampled_from(["Active", "Inactive", "Unknown"]))
            status_json = json_string(status_val)
        else:
            status_json = "null"
    else:
        status_json = None

    # tags field
    tags_present = draw(st.booleans())
    if tags_present:
        # tags can be array of strings, array of ints (to trigger coercion), null
        tags_type = draw(st.sampled_from(["string_array", "int_array", "null"]))
        if tags_type == "string_array":
            # array of 0-3 strings without quotes or control chars
            tags_vals = draw(st.lists(st.text(min_size=1, max_size=5).filter(lambda s: '"' not in s and '\\' not in s), max_size=3))
            tags_json = json_array_of_strings(tags_vals)
        elif tags_type == "int_array":
            tags_vals = draw(st.lists(st.integers(min_value=0, max_value=100), max_size=3))
            tags_json = "[" + ",".join(str(x) for x in tags_vals) + "]"
        else:
            tags_json = "null"
    else:
        tags_json = None

    # child field
    child_present = draw(st.booleans())
    if child_present and _depth < 1:
        # child can be null or a nested record (one level recursion)
        child_type = draw(st.sampled_from(["null", "record"]))
        if child_type == "null":
            child_json = "null"
        else:
            child_json = draw(generated_json(_depth=_depth + 1)).decode("utf-8")
    else:
        child_json = None

    # Compose fields as JSON key:value pairs, only present fields included
    fields = []
    if id_json is not None:
        fields.append('"id":' + id_json)
    if amount_json is not None:
        fields.append('"amount":' + amount_json)
    if name_json is not None:
        fields.append('"name":' + name_json)
    if status_json is not None:
        fields.append('"status":' + status_json)
    if tags_json is not None:
        fields.append('"tags":' + tags_json)
    if child_json is not None:
        fields.append('"child":' + child_json)

    # Occasionally add one extra unknown key to trigger divergence on unknown keys acceptance
    add_extra_key = draw(st.booleans())
    if add_extra_key:
        extra_key_name = draw(st.text(min_size=1, max_size=5).filter(lambda s: all(c.isalpha() for c in s)))
        extra_key_val_type = draw(st.sampled_from(["string", "number", "null"]))
        if extra_key_val_type == "string":
            extra_key_val = draw(st.text(min_size=1, max_size=5))
            extra_key_json = json_string(extra_key_val)
        elif extra_key_val_type == "number":
            extra_key_val = draw(st.integers(min_value=0, max_value=100))
            extra_key_json = str(extra_key_val)
        else:
            extra_key_json = "null"
        fields.append(json_string(extra_key_name) + ":" + extra_key_json)

    # Compose final JSON object text
    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")