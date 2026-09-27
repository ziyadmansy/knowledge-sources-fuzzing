from hypothesis import strategies as st

# Helper: JSON string escaping for simple strings (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote minimally
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings
def json_array_of_strings(lst):
    return '[' + ','.join(json_string(x) for x in lst) + ']'

# Helper: JSON null
json_null = "null"

# Helper: JSON boolean literals
json_true = "true"
json_false = "false"

# Helper: JSON number as string
def json_number(n: int) -> str:
    return str(n)

# Helper: JSON enum for status
status_values = ['"active"', '"inactive"', '"unknown"']

# Compose a JSON record text from fields (all fields present)
def json_record_text(
    id_text,
    amount_text,
    name_text,
    status_text,
    tags_text,
    child_text,
):
    # Compose fields in fixed order for consistency
    fields = [
        '"id":' + id_text,
        '"amount":' + amount_text,
        '"name":' + name_text,
        '"status":' + status_text,
        '"tags":' + tags_text,
        '"child":' + child_text,
    ]
    return '{' + ','.join(fields) + '}'

# Strategy for id field text:
# Known: id accepts integer or numeric string coercible to int
# We produce either integer literal or string literal of integer
id_int = st.integers(min_value=0, max_value=1000000)
id_as_int = id_int.map(json_number)
id_as_str = id_int.map(lambda i: json_string(str(i)))
id_text = st.one_of(id_as_int, id_as_str)

# Strategy for amount field text:
# Known: amount is string normally
# Gson, Moshi, Jackson accept numeric amount as number (coerce to string)
# kotlinx rejects numeric amount as number
# So produce either string or number for amount
amount_str = st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string)
amount_num = st.floats(allow_infinity=False, allow_nan=False, width=32).map(lambda f: ('%.6g' % f).rstrip('0').rstrip('.') if '.' in ('%.6g' % f) else ('%.6g' % f))
amount_num = amount_num.map(str)
amount_text = st.one_of(amount_str, amount_num)

# Strategy for name field text:
# name is string or null normally
# Gson, Moshi, Jackson accept non-string (number, boolean) coercing to string
# kotlinx rejects non-string name
# So produce string, null, number, boolean for name
name_string = st.one_of(
    st.none().map(lambda _: json_null),
    st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string),
)
name_number = st.one_of(
    st.integers(min_value=-1000, max_value=1000).map(json_number),
    st.floats(allow_infinity=False, allow_nan=False, width=32).map(lambda f: ('%.6g' % f).rstrip('0').rstrip('.') if '.' in ('%.6g' % f) else ('%.6g' % f)),
)
name_boolean = st.booleans().map(lambda b: json_true if b else json_false)
name_text = st.one_of(name_string, name_number, name_boolean)

# Strategy for status field text:
# status is enum string: "active", "inactive", "unknown"
# Invalid enum string causes Moshi, kotlinx, Jackson to reject; Gson accepts with null status
# Also test null status (Gson accepts null, others reject)
# So produce valid enum strings, invalid enum strings, and null
valid_status = st.sampled_from(status_values)
invalid_status = st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string)
null_status = st.just(json_null)
status_text = st.one_of(valid_status, invalid_status, null_status)

# Strategy for tags field text:
# tags is array of strings normally
# All reject non-array tags (string)
# Gson, Moshi, Jackson accept non-string elements and nulls in tags array, coercing or allowing null; kotlinx rejects
# So produce:
# - array of strings (normal)
# - array with some non-string elements (number, boolean, null)
# - non-array (string) to cause rejection by all
tags_string_element = st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s)
tags_string_array = st.lists(tags_string_element, min_size=0, max_size=5).map(json_array_of_strings)

tags_number_element = st.one_of(
    st.integers(min_value=-1000, max_value=1000).map(json_number),
    st.floats(allow_infinity=False, allow_nan=False, width=32).map(lambda f: ('%.6g' % f).rstrip('0').rstrip('.') if '.' in ('%.6g' % f) else ('%.6g' % f)),
)
tags_boolean_element = st.booleans().map(lambda b: json_true if b else json_false)
tags_null_element = st.just(json_null)

tags_mixed_elements = st.lists(
    st.one_of(
        tags_string_element.map(json_string),
        tags_number_element,
        tags_boolean_element,
        tags_null_element,
    ),
    min_size=0,
    max_size=5,
).map(lambda lst: '[' + ','.join(lst) + ']')

tags_non_array = st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s).map(json_string)

tags_text = st.one_of(tags_string_array, tags_mixed_elements, tags_non_array)

# Strategy for child field text:
# child is either null or a nested record (one level recursion normally)
# Known:
# - all accept nested child with correct fields and types
# - all accept nested child with numeric id as string coercing to int
# - extra fields in child accepted by Gson, Moshi; rejected by kotlinx, Jackson
# - empty child object accepted only by Gson (with default/zero values), others reject
# - null child accepted by all
# - nested child with empty child inside rejected by Moshi, kotlinx, Jackson; Gson accepts with defaults
# - nested child with extra fields accepted by Gson, Moshi; rejected by kotlinx, Jackson
# To keep bounded recursion, limit child nesting to 1 level only (child.child is null or empty object)
# We produce child as:
# - null
# - well-formed child record (with fields as above)
# - child with empty object {}
# - child with extra fields
# - child with nested child null
# - child with nested child empty object {}

# To avoid infinite recursion, define child record with child.child = null or empty object only

# We'll define a helper function to produce child record text with controlled child.child

def child_record_text(draw_child_child_text):
    # draw_child_child_text is a strategy for the nested child's child field text
    # Compose child record with fields:
    # id: int or string
    # amount: string or number
    # name: string, null, number, boolean
    # status: valid enum, invalid enum, or null
    # tags: array of strings, mixed array, or non-array string
    # child: draw_child_child_text
    return st.tuples(
        id_text,
        amount_text,
        name_text,
        status_text,
        tags_text,
        draw_child_child_text,
    ).map(lambda t: json_record_text(*t))

# child.child can be null or empty object "{}"
child_child_null = st.just(json_null)
child_child_empty_obj = st.just("{}")

# child.child can be null or empty object only to keep bounded recursion
child_child_text = st.one_of(child_child_null, child_child_empty_obj)

# child record with child.child = null or empty object
child_record = child_record_text(child_child_text)

# child with extra fields (only Gson, Moshi accept)
# Add extra field "extraField":123
child_record_with_extra = child_record.map(lambda s: s[:-1] + ',"extraField":123}')

# child empty object "{}"
child_empty_object = st.just("{}")

# child field text: null, well-formed child, empty object, child with extra fields
child_text = st.one_of(
    st.just(json_null),
    child_record,
    child_empty_object,
    child_record_with_extra,
)

@st.composite
def generated_json(draw) -> bytes:
    # Compose top-level record with fields:
    # id, amount, name, status, tags, child
    # Use the above strategies
    id_val = draw(id_text)
    amount_val = draw(amount_text)
    name_val = draw(name_text)
    status_val = draw(status_text)
    tags_val = draw(tags_text)
    child_val = draw(child_text)

    # Compose JSON text
    json_text = json_record_text(id_val, amount_val, name_val, status_val, tags_val, child_val)

    # Return as bytes (UTF-8)
    return json_text.encode("utf-8")