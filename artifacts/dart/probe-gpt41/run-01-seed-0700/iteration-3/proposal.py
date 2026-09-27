from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslashes only (minimal)
def json_string_escape(s: str) -> str:
    # Only escape backslash and double quote for JSON strings
    return s.replace('\\', '\\\\').replace('"', '\\"')

# Compose a JSON string literal from a Python string
def json_string_literal(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

@st.composite
def generated_json(draw) -> bytes:
    # Constants for "status" enum
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Strategy for "id": integer (required)
    id_val = draw(st.integers(min_value=0, max_value=10**9))

    # Strategy for "amount": string representing a decimal number (required)
    # To maximize divergence, sometimes produce valid decimal strings,
    # sometimes produce strings that look numeric but with odd formatting.
    # But all must be strings.
    # We'll produce strings of digits with optional decimal point and optional leading zeros.
    def amount_str():
        # Either integer string or decimal string with 1-2 decimal digits
        int_part = draw(st.integers(min_value=0, max_value=9999999))
        if draw(st.booleans()):
            # integer string
            return str(int_part)
        else:
            # decimal string with 1 or 2 decimals
            decimals = draw(st.integers(min_value=0, max_value=99))
            return f"{int_part}.{decimals:0>2}"

    amount_val = amount_str()

    # Strategy for "name": string or null or missing (missing treated as null)
    # To maximize divergence, sometimes omit "name" field, sometimes null, sometimes string
    # But since all accept missing or null, no divergence here.
    # We'll always include "name" to keep one variation less.
    # But to keep "name" sometimes null or string:
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))

    # Strategy for "status": one of the three strings (required)
    # To maximize divergence, sometimes omit "status" (only built_value accepts missing)
    # or put invalid values (all reject).
    # We'll produce mostly valid values, but sometimes omit.
    status_present = draw(st.booleans())
    if status_present:
        status_val = draw(st.sampled_from(STATUS_VALUES))
    else:
        status_val = None  # omitted

    # Strategy for "tags": array of strings (required)
    # To maximize divergence, sometimes omit "tags" (only built_value accepts missing)
    # or empty array, or array with empty strings, or array with one string.
    tags_present = draw(st.booleans())
    if tags_present:
        # array of 0 to 3 strings (strings can be empty)
        tags_list = draw(st.lists(st.text(min_size=0, max_size=5), max_size=3))
    else:
        tags_list = None  # omitted

    # Strategy for "child": null or nested record or omitted (treated as null)
    # To keep recursion bounded, max depth 1 (no grandchild)
    # We'll produce either null or a nested record with all required fields well-formed
    # or omit child (treated as null)
    child_present = draw(st.booleans())
    if child_present:
        # nested record with all required fields present and valid
        # but to maximize divergence, sometimes make one field off-type or missing in child
        # but since malformed child causes all to reject, we keep child well-formed here
        child_id = draw(st.integers(min_value=0, max_value=10**9))
        child_amount = amount_str()
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        child_status = draw(st.sampled_from(STATUS_VALUES))
        child_tags = draw(st.lists(st.text(min_size=0, max_size=5), max_size=3))
        # child.child omitted (null)
        child_obj = {
            "id": child_id,
            "amount": child_amount,
            "name": child_name,
            "status": child_status,
            "tags": child_tags,
            # "child" omitted
        }
    else:
        child_obj = None  # null or omitted

    # Build JSON object string parts
    # We will selectively omit "status" and "tags" to trigger divergence on built_value acceptance
    # We will always include "id" and "amount" (required)
    # We will always include "name" (nullable)
    # We will include "child" as null or nested object or omit (treated as null)

    # Compose fields as list of strings "key":value
    fields = []

    # "id": integer
    fields.append('"id":' + str(id_val))

    # "amount": string
    fields.append('"amount":' + json_string_literal(amount_val))

    # "name": string or null
    if name_val is None:
        fields.append('"name":null')
    else:
        fields.append('"name":' + json_string_literal(name_val))

    # "status": string or omitted
    if status_val is not None:
        fields.append('"status":' + json_string_literal(status_val))
    # else omit "status"

    # "tags": array of strings or omitted
    if tags_list is not None:
        # Compose JSON array of strings
        tags_json = '[' + ','.join(json_string_literal(t) for t in tags_list) + ']'
        fields.append('"tags":' + tags_json)
    # else omit "tags"

    # "child": null or nested object or omitted
    if child_obj is None:
        # include "child": null explicitly (to avoid ambiguity)
        fields.append('"child":null')
    else:
        # Compose child object JSON string
        child_fields = []
        child_fields.append('"id":' + str(child_obj["id"]))
        child_fields.append('"amount":' + json_string_literal(child_obj["amount"]))
        if child_obj["name"] is None:
            child_fields.append('"name":null')
        else:
            child_fields.append('"name":' + json_string_literal(child_obj["name"]))
        child_fields.append('"status":' + json_string_literal(child_obj["status"]))
        child_tags_json = '[' + ','.join(json_string_literal(t) for t in child_obj["tags"]) + ']'
        child_fields.append('"tags":' + child_tags_json)
        # omit child.child
        child_json = '{' + ','.join(child_fields) + '}'
        fields.append('"child":' + child_json)

    # Compose full JSON object string
    json_obj = '{' + ','.join(fields) + '}'

    # Return as bytes
    return json_obj.encode('utf-8')