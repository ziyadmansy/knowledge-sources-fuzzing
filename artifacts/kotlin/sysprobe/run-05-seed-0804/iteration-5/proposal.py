from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars)
def json_string(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings
def json_array_of_strings(lst):
    return '[' + ','.join(json_string(s) for s in lst) + ']'

# Helper: JSON enum "status" with known values plus some variants for testing
status_values = ["active", "inactive", "unknown"]
# We will generate either a valid enum or an invalid variant (case variant or unknown)
def json_status(draw):
    # 80% valid enum, 20% invalid variant
    valid = st.sampled_from(status_values)
    invalid = st.one_of(
        st.sampled_from(["Active", "INACTIVE", "Unknown", "invalid", ""]),
        st.text(min_size=1, max_size=5).filter(lambda x: x.lower() not in status_values)
    )
    use_valid = draw(st.booleans())
    val = draw(valid if use_valid else invalid)
    return json_string(val)

# Helper: JSON value for "id" (integer, or null, or missing)
# We will produce either integer or null (to trigger divergence)
def json_id(draw):
    # According to known facts:
    # Gson and Jackson accept null for id (decode as 0)
    # Moshi and kotlinx reject null for id
    # So null id is a good divergence trigger
    use_null = draw(st.booleans())
    if use_null:
        return "null"
    else:
        # integer id >=0
        return str(draw(st.integers(min_value=0, max_value=10000)))

# Helper: JSON value for "amount" (string, integer coerced to string, or null)
# Gson accepts null amount as null, others reject null
# Gson, Jackson, Moshi accept integer for amount (coerced to string), kotlinx rejects
def json_amount(draw, nested=False):
    # nested param to distinguish top-level vs child behavior (some differences)
    # At top-level:
    # - null amount accepted only by Gson
    # - integer amount accepted by Gson, Jackson, Moshi; rejected by kotlinx
    # At child:
    # - Gson accepts null amount, Jackson rejects null amount
    # - Gson, Jackson, Moshi accept integer amount; kotlinx rejects
    choice = draw(st.sampled_from(["string", "integer", "null"]))
    if choice == "string":
        # string or null string? null string is null, so here string only
        # generate a non-empty ascii string without quotes or control chars
        s = draw(st.text(min_size=1, max_size=10).filter(lambda x: all(32 <= ord(c) <= 126 and c not in '"\\' for c in x)))
        return json_string(s)
    elif choice == "integer":
        # integer coerced to string by some implementations
        i = draw(st.integers(min_value=0, max_value=100000))
        return str(i)
    else:  # null
        # null accepted only by Gson top-level and child; Jackson rejects null in child
        # We produce null anyway to trigger divergence
        return "null"

# Helper: JSON value for "name" (string or null)
# name is nullable string, so null accepted by all
def json_name(draw):
    # 80% string, 20% null
    if draw(st.booleans()):
        s = draw(st.text(min_size=0, max_size=10).filter(lambda x: all(32 <= ord(c) <= 126 and c not in '"\\' for c in x)))
        return json_string(s)
    else:
        return "null"

# Helper: JSON value for "status" (enum string, or invalid string)
def json_status_field(draw):
    return json_status(draw)

# Helper: JSON value for "tags" (array of strings)
# Gson and Jackson accept missing tags as null; Moshi and kotlinx reject missing tags
# So missing tags is a divergence trigger
def json_tags(draw):
    # 70% present, 30% missing (missing means omit field)
    present = draw(st.booleans())
    if not present:
        return None
    # present: array of strings, possibly empty
    # strings are ascii printable without quotes or control chars
    n = draw(st.integers(min_value=0, max_value=5))
    lst = draw(st.lists(st.text(min_size=1, max_size=10).filter(lambda x: all(32 <= ord(c) <= 126 and c not in '"\\' for c in x)), min_size=n, max_size=n))
    return json_array_of_strings(lst)

# Helper: JSON value for "child" (Record or null or missing)
# Gson and Jackson accept missing child as null; Moshi and kotlinx reject missing child
# Gson and Jackson accept null child; Moshi and kotlinx reject null child
# So missing or null child is a divergence trigger
# Limit recursion depth to 1 (only one level)
def json_child(draw, depth=0):
    # 50% missing, 25% null, 25% present
    choice = draw(st.sampled_from(["missing", "null", "present"]))
    if choice == "missing":
        return None
    elif choice == "null":
        return "null"
    else:
        # present child record, depth limit 1
        if depth >= 1:
            # To avoid infinite recursion, produce a minimal valid child with no further child
            # Use well-formed child with all fields present and valid
            id_val = str(draw(st.integers(min_value=0, max_value=10000)))
            amount_val = json_amount(draw, nested=True)
            name_val = json_name(draw)
            status_val = json_status_field(draw)
            tags_val = json_array_of_strings(draw(st.lists(st.text(min_size=1, max_size=10).filter(lambda x: all(32 <= ord(c) <= 126 and c not in '"\\' for c in x)), min_size=0, max_size=3)))
            child_val = "null"
            return (
                '{'
                + '"id":' + id_val + ','
                + '"amount":' + amount_val + ','
                + '"name":' + name_val + ','
                + '"status":' + status_val + ','
                + '"tags":' + tags_val + ','
                + '"child":' + child_val
                + '}'
            )
        else:
            # Recursively generate child record with depth+1
            return generated_record(draw, depth=depth+1)

# Compose a full record JSON string with all fields present except those omitted by None
def generated_record(draw, depth=0):
    # id field: integer or null (null triggers divergence)
    id_val = json_id(draw)
    # amount field: string, integer, or null (null triggers divergence)
    amount_val = json_amount(draw, nested=(depth>0))
    # name field: string or null
    name_val = json_name(draw)
    # status field: enum string or invalid variant
    status_val = json_status_field(draw)
    # tags field: array of strings or missing (None)
    tags_val = json_tags(draw)
    # child field: record, null, or missing (None)
    child_val = json_child(draw, depth=depth)

    # Build JSON fields list
    fields = []
    # id always present
    fields.append('"id":' + id_val)
    # amount always present
    fields.append('"amount":' + amount_val)
    # name always present
    fields.append('"name":' + name_val)
    # status always present
    fields.append('"status":' + status_val)
    # tags present or omitted
    if tags_val is not None:
        fields.append('"tags":' + tags_val)
    # child present or omitted
    if child_val is not None:
        fields.append('"child":' + child_val)

    return '{' + ','.join(fields) + '}'

@st.composite
def generated_json(draw) -> bytes:
    # Generate a record JSON string with bounded recursion depth 0
    s = generated_record(draw, depth=0)
    return s.encode("utf-8")