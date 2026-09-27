from hypothesis import strategies as st

# Helper: JSON string literal with proper escaping of " and \ only (minimal)
def json_string(s: str) -> str:
    # Escape backslash and quote only (safe minimal escaping)
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings
def json_array_of_strings(draw, min_size=0, max_size=5):
    strs = draw(st.lists(st.text(min_size=0, max_size=10), min_size=min_size, max_size=max_size))
    # All elements are strings, no nulls or other types
    return '[' + ','.join(json_string(x) for x in strs) + ']'

# Helper: JSON enum "status" with known valid values and some invalid variants for fuzzing
status_valid = st.sampled_from(["active", "inactive", "unknown"])
status_invalid = st.sampled_from(["invalid", "ACTIVE", "InActive", "unknown "])  # known rejects

# Helper: JSON number as string (for "amount" field)
# "amount" is string, but test boundary strings that look numeric or empty
amount_valid = st.one_of(
    st.text(min_size=1, max_size=10).filter(lambda s: s != "null" and s != ""),  # normal strings
    st.just("0"),
    st.just("0.0"),
    st.just("-0"),
    st.just("12345678901234567890"),  # large numeric string
)
# We do not want amount as number (probe 12 rejects that), but we want to test borderline strings

# Helper: JSON id integer as string (to insert as number)
id_valid = st.integers(min_value=0, max_value=2**31-1)

# Compose a record JSON text with controlled fields, optionally nested child
# We produce a dict with all six fields always present (except we fuzz missing child sometimes)
# We produce syntactically valid JSON text only.

@st.composite
def generated_json(draw) -> bytes:
    # Decide if child is present or missing (missing child triggers divergence: built_value accepts, others reject)
    child_present = draw(st.booleans())
    # Decide if child is null or a nested record (null child accepted by built_value and others)
    child_null = False
    if child_present:
        child_null = draw(st.booleans())

    # id: integer, never null, always present
    id_val = draw(id_valid)

    # amount: string, never null, always present
    # We try to produce borderline strings that look numeric or empty or normal text
    amount_val = draw(amount_valid)

    # name: string or null, always present
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))

    # status: one of enum strings, or invalid variants to trigger divergence
    # To maximize divergence, sometimes produce invalid enum strings
    status_val = draw(st.one_of(status_valid, status_invalid))

    # tags: array of strings, never null, always present
    # built_value accepts null tags and converts to empty array, others reject null tags
    # To trigger divergence, sometimes produce null tags
    tags_null = draw(st.booleans())
    if tags_null:
        tags_val = None
    else:
        tags_val = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))

    # Compose child JSON text if present and not null
    if child_present:
        if child_null:
            child_json = "null"
        else:
            # Nested child record, one level only, no further recursion
            # Nested child must be valid or invalid to trigger divergence
            # We produce a valid nested child with all fields present and valid
            # But sometimes produce invalid nested child with null id or amount or invalid status
            nested_id = draw(id_valid)
            nested_amount = draw(amount_valid)
            nested_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            nested_status = draw(status_valid)  # nested child status valid to avoid rejection
            nested_tags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))
            # Compose nested child JSON text
            nested_child = (
                '{'
                + '"id":' + str(nested_id) + ','
                + '"amount":' + json_string(nested_amount) + ','
                + '"name":' + ("null" if nested_name is None else json_string(nested_name)) + ','
                + '"status":' + json_string(nested_status) + ','
                + '"tags":' + '[' + ','.join(json_string(t) for t in nested_tags) + ']' + ','
                + '"child":null'
                + '}'
            )
            child_json = nested_child
    else:
        # child missing (omit field) triggers divergence: built_value accepts, others reject
        child_json = None

    # Compose tags JSON text
    if tags_val is None:
        tags_json = "null"
    else:
        tags_json = '[' + ','.join(json_string(t) for t in tags_val) + ']'

    # Compose top-level JSON fields as list of key:value strings
    fields = []
    # id always present, integer
    fields.append('"id":' + str(id_val))
    # amount always present, string
    fields.append('"amount":' + json_string(amount_val))
    # name always present, string or null
    fields.append('"name":' + ("null" if name_val is None else json_string(name_val)))
    # status always present, string (valid or invalid)
    fields.append('"status":' + json_string(status_val))
    # tags always present, array or null
    fields.append('"tags":' + tags_json)
    # child present or missing
    if child_json is not None:
        fields.append('"child":' + child_json)
    # else omit child field

    # Compose final JSON object text
    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode("utf-8")