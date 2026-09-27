from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslashes only,
# minimal escaping to keep JSON valid.
def json_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')

# Recursive record generator as JSON text (string), bounded depth.
# Produces a JSON object string with all six fields always present,
# but with controlled variations to induce divergences.
@st.composite
def record_json(draw, depth=0):
    # Limit recursion depth to 1 for child (one level only)
    max_depth = 1

    # id field: integer or double (to trigger int vs num.toInt() difference)
    # We produce either a JSON integer literal or a JSON number literal with decimal point.
    # To get a double, produce a number with decimal point but integral value.
    # Also test very large integers that jsonDecode turns into double.
    id_choice = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
    # With some probability, emit as double literal (e.g. "123.0") to test json_serializable/freezed acceptance.
    emit_double = draw(st.booleans())
    if emit_double:
        # Represent as floating point with .0 suffix
        id_json = str(float(id_choice))  # e.g. "123.0"
    else:
        id_json = str(id_choice)  # e.g. "123"

    # amount: string, always present, non-null
    # Use simple decimal strings, or sometimes empty string to test boundaries.
    amount_str = draw(st.text(min_size=0, max_size=10))
    # Escape string for JSON
    amount_json = '"' + json_escape(amount_str) + '"'

    # name: nullable string or null
    # Sometimes null, sometimes string (possibly empty)
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        name_str = draw(st.text(min_size=0, max_size=10))
        name_json = '"' + json_escape(name_str) + '"'

    # status: one of "active", "inactive", "unknown", or sometimes an unrecognized string
    # Unrecognized strings are rejected by all four, so no divergence from that.
    # So only pick from the three known values.
    status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
    status_json = '"' + status_val + '"'

    # tags: array of strings, or sometimes missing (to test built_value acceptance)
    # To induce divergence, sometimes omit tags field entirely.
    tags_missing = draw(st.booleans())
    if not tags_missing:
        # tags array: 0 to 3 strings, each string up to length 5
        tags_list = draw(st.lists(st.text(min_size=0, max_size=5), max_size=3))
        # Escape each string
        tags_json_items = ['"' + json_escape(t) + '"' for t in tags_list]
        tags_json = "[" + ",".join(tags_json_items) + "]"
    else:
        tags_json = None  # omit field

    # child: nullable record or null
    # At max depth, child must be null to avoid infinite recursion
    if depth >= max_depth:
        child_json = "null"
    else:
        # Sometimes null, sometimes a nested record (depth+1)
        child_is_null = draw(st.booleans())
        if child_is_null:
            child_json = "null"
        else:
            child_json = draw(record_json(depth=depth + 1))

    # Compose fields as JSON object text
    # Fields order: id, amount, name, status, tags (optional), child
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
    ]
    if tags_json is not None:
        fields.append('"tags":' + tags_json)
    # else omit tags field to test built_value acceptance

    fields.append('"child":' + child_json)

    obj_json = "{" + ",".join(fields) + "}"
    return obj_json

@st.composite
def generated_json(draw) -> bytes:
    # Draw a record JSON string
    json_str = draw(record_json())
    # Return as UTF-8 bytes
    return json_str.encode("utf-8")