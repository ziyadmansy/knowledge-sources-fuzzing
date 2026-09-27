from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string_escape(s: str) -> str:
    # Escape backslash and double quote only for simplicity
    return s.replace('\\', '\\\\').replace('"', '\\"')

# Compose JSON string literal from Python string
def json_string_literal(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

# Compose JSON array literal from list of JSON element strings
def json_array_literal(elements) -> str:
    return '[' + ','.join(elements) + ']'

# Compose JSON object literal from list of (key, value) pairs (both strings)
def json_object_literal(pairs) -> str:
    # pairs: list of (key_str, value_str)
    # keys must be JSON strings already (including quotes)
    return '{' + ','.join(k + ':' + v for k, v in pairs) + '}'

# Compose JSON number literal from int or float or string representing number
def json_number_literal(n) -> str:
    return str(n)

# Compose JSON null literal
json_null_literal = 'null'

# Compose JSON boolean literal
def json_bool_literal(b: bool) -> str:
    return 'true' if b else 'false'

# Strategy for "id" field: integer or stringified integer (both accepted by all)
id_int = st.integers(min_value=0, max_value=2**31-1)
id_as_number = id_int.map(str)
id_as_string = id_int.map(lambda i: json_string_literal(str(i)))
id_field_value = st.one_of(id_as_number, id_as_string)

# Strategy for "amount" field:
# Known: Gson, Moshi, Jackson accept string or number (convert number to string),
# kotlinx rejects number.
# To maximize divergence, sometimes produce number, sometimes string.
amount_number = st.floats(min_value=0, max_value=1e9, allow_infinity=False, allow_nan=False).map(lambda f: ('number', str(round(f,2))))
amount_string = st.text(min_size=0, max_size=20).map(lambda s: ('string', json_string_literal(s)))
amount_field_value = st.one_of(amount_number, amount_string)

# Strategy for "name" field:
# Can be string or null normally.
# Gson and Moshi accept number (convert to string),
# kotlinx rejects number,
# Jackson accepts number as string.
# To maximize divergence, sometimes produce string, null, or number.
name_string = st.text(min_size=0, max_size=20).map(json_string_literal)
name_null = st.just(json_null_literal)
name_number = st.integers(min_value=-1000, max_value=1000).map(str)
name_field_value = st.one_of(name_string, name_null, name_number)

# Strategy for "status" field:
# Enum: "active", "inactive", "unknown"
# Gson accepts unknown enum as null,
# Moshi, kotlinx, Jackson reject unknown enum,
# Gson accepts null for status, others reject null.
# So produce valid enum, unknown enum string, or null.
valid_statuses = ["active", "inactive", "unknown"]
valid_status = st.sampled_from(valid_statuses).map(json_string_literal)
unknown_status = st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_statuses).map(json_string_literal)
status_null = st.just(json_null_literal)
status_field_value = st.one_of(valid_status, unknown_status, status_null)

# Strategy for "tags" field:
# Must be array.
# Gson, Moshi, Jackson accept array with non-string elements (convert to string),
# kotlinx rejects non-string elements.
# So produce array of strings or array with mixed types.
tag_string = st.text(min_size=0, max_size=10).map(json_string_literal)
tag_number = st.integers(min_value=-1000, max_value=1000).map(str)
tag_bool = st.booleans().map(json_bool_literal)
tag_null = st.just(json_null_literal)
# Mixed element types to provoke divergence
tag_element = st.one_of(tag_string, tag_number, tag_bool, tag_null)
# Pure string array or mixed array
tags_array_strings = st.lists(tag_string, min_size=0, max_size=5).map(json_array_literal)
tags_array_mixed = st.lists(tag_element, min_size=0, max_size=5).map(json_array_literal)
tags_field_value = st.one_of(tags_array_strings, tags_array_mixed)

# Strategy for "child" field:
# null or nested record (one level recursion)
# To avoid deep recursion, limit nesting to 1 level.
# We'll define a helper function to generate child JSON text.

# Forward declaration for record JSON text strategy
def record_json_text(allow_child=True):
    # Compose record fields as JSON text strings
    # id, amount, name, status, tags, child
    # Use the above field strategies
    # allow_child: if False, child is always null (to avoid deep recursion)
    # We'll build a strategy returning JSON text string for a record

    # Compose child field value strategy
    if allow_child:
        # child can be null or nested record with allow_child=False (one level)
        child_null = st.just(json_null_literal)
        child_record = record_json_text(allow_child=False)
        child_field_value = st.one_of(child_null, child_record)
    else:
        child_field_value = st.just(json_null_literal)

    # Compose fields as tuples (key, value)
    def build_record(id_v, amount_v, name_v, status_v, tags_v, child_v):
        pairs = [
            (json_string_literal("id"), id_v),
            (json_string_literal("amount"), amount_v),
            (json_string_literal("name"), name_v),
            (json_string_literal("status"), status_v),
            (json_string_literal("tags"), tags_v),
            (json_string_literal("child"), child_v),
        ]
        return json_object_literal(pairs)

    return st.tuples(
        id_field_value,
        amount_field_value,
        name_field_value,
        status_field_value,
        tags_field_value,
        child_field_value,
    ).map(lambda t: build_record(*t))

# The main generated_json strategy returns bytes of JSON text for a record
@st.composite
def generated_json(draw) -> bytes:
    # Draw a record JSON text string with one level of child recursion
    json_text = draw(record_json_text(allow_child=True))
    return json_text.encode('utf-8')