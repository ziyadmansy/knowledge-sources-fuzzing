from hypothesis import strategies as st

# We produce JSON text (bytes) of a single object with the given schema.
# We carefully vary presence, nullability, and types of fields to trigger
# divergences, focusing on "tags" and "child" null/missing/empty array,
# and subtle type boundary or duplicate keys.

# Helper: JSON string escaper for simple ASCII strings (no control chars).
def json_string(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping.
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings.
def json_array_of_strings(arr):
    return '[' + ','.join(json_string(e) for e in arr) + ']'

# Helper: JSON object from dict of key->value strings (already JSON text).
def json_object(d):
    # keys are strings, values are JSON text strings
    return '{' + ','.join(json_string(k) + ':' + v for k, v in d.items()) + '}'

# We produce a record JSON text with controlled variations.
# We use bounded recursion for "child" (depth 0 or 1).
# We vary:
# - presence or absence of "tags" and "child" (built_value accepts missing)
# - null vs empty array for "tags" (built_value accepts null tags)
# - null vs object for "child"
# - "id" as integer (always present, never null)
# - "amount" as string (always present, never null)
# - "name" as string or null (always present)
# - "status" as enum string (always present, correct value)
# - duplicate keys for "tags" or "child" (to test duplicate keys)
# - subtle type variations for "tags" (array vs null vs missing)
# - subtle type variations for "child" (object vs null vs missing)
# We do not produce invalid JSON syntax.
# We do not produce invalid enum values or missing required fields except "tags" and "child".

@st.composite
def generated_json(draw, _depth=0):
    # id: integer
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    id_json = str(id_val)

    # amount: string (non-null)
    amount_val = draw(st.text(min_size=1, max_size=10))
    amount_json = json_string(amount_val)

    # name: string or null
    name_val = draw(st.one_of(st.none(), st.text(max_size=10)))
    name_json = "null" if name_val is None else json_string(name_val)

    # status: one of "active", "inactive", "unknown"
    status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
    status_json = json_string(status_val)

    # tags: three variants:
    # 1) present as array of strings (possibly empty)
    # 2) present as null (only built_value accepts)
    # 3) missing (only built_value accepts)
    tags_variant = draw(st.sampled_from(["array", "null", "missing"]))
    if tags_variant == "array":
        tags_list = draw(st.lists(st.text(min_size=1, max_size=5), max_size=3))
        tags_json = json_array_of_strings(tags_list)
    elif tags_variant == "null":
        tags_json = "null"
    else:  # missing
        tags_json = None

    # child: three variants:
    # 1) present as object (recursive, depth limited)
    # 2) present as null
    # 3) missing
    child_variant = draw(st.sampled_from(["object", "null", "missing"]))
    if _depth == 0:
        if child_variant == "object":
            child_json = generated_json(draw, _depth=1)
        elif child_variant == "null":
            child_json = "null"
        else:
            child_json = None
    else:
        # depth 1: no further recursion, child must be null or missing or empty object
        # to keep recursion bounded, produce empty object or null or missing
        child_variant_1 = draw(st.sampled_from(["object", "null", "missing"]))
        if child_variant_1 == "object":
            # empty object (all fields missing) - built_value accepts missing tags/child
            child_json = "{}"
        elif child_variant_1 == "null":
            child_json = "null"
        else:
            child_json = None

    # Compose fields dict
    fields = {
        "id": id_json,
        "amount": amount_json,
        "name": name_json,
        "status": status_json,
    }
    # Add tags if not missing
    if tags_json is not None:
        fields["tags"] = tags_json
    # Add child if not missing
    if child_json is not None:
        fields["child"] = child_json

    # Duplicate keys test: optionally duplicate "tags" or "child" keys with same or different values
    # This can cause divergence if some accept duplicates differently.
    # We do this rarely to keep corpus focused.
    duplicate_key = draw(st.one_of(st.none(), st.just("tags"), st.just("child")))
    if duplicate_key is not None and duplicate_key in fields:
        # duplicate key with either same or different value
        dup_same = draw(st.booleans())
        if duplicate_key == "tags":
            if dup_same:
                dup_value = fields["tags"]
            else:
                # different value: if array, change to null or empty array; if null, change to array
                if fields["tags"] == "null":
                    dup_value = "[]"
                else:
                    dup_value = "null"
            # Insert duplicate key after original
            # We will build JSON manually below to allow duplicates
            # So mark duplicate to insert later
            duplicate_entry = (duplicate_key, dup_value)
        else:  # child
            if dup_same:
                dup_value = fields["child"]
            else:
                # different value: if null, change to empty object; if object, change to null
                if fields["child"] == "null":
                    dup_value = "{}"
                else:
                    dup_value = "null"
            duplicate_entry = (duplicate_key, dup_value)
    else:
        duplicate_entry = None

    # Build JSON text with possible duplicate key
    # Insert keys in order: id, amount, name, status, tags?, child?, duplicate?
    parts = []
    def add_field(k):
        parts.append(json_string(k))
        parts.append(":")
        parts.append(fields[k])

    add_field("id")
    parts.append(",")
    add_field("amount")
    parts.append(",")
    add_field("name")
    parts.append(",")
    add_field("status")

    if "tags" in fields:
        parts.append(",")
        add_field("tags")
    if "child" in fields:
        parts.append(",")
        add_field("child")
    if duplicate_entry is not None:
        parts.append(",")
        parts.append(json_string(duplicate_entry[0]))
        parts.append(":")
        parts.append(duplicate_entry[1])

    json_text = "{" + "".join(parts) + "}"

    return json_text.encode("utf-8")