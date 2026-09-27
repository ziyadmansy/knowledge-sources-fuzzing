from hypothesis import strategies as st

# Helper: JSON string with proper escaping of quotes and backslashes only (minimal)
# We keep it simple: no control chars, no unicode escapes, just safe ASCII subset.
json_string_chars = st.characters(
    whitelist_categories=('Ll', 'Lu', 'Nd', 'Zs', 'Po'),
    blacklist_characters='"\\'
).filter(lambda c: c not in '\n\r\t')

json_string = st.text(json_string_chars, min_size=0, max_size=10).map(
    lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
)

# JSON number: integer or floating point, as string
# We produce numbers as strings for the "amount" field.
# We allow integers, floats, and edge cases like exponentials.
json_number_str = st.one_of(
    # integer strings (including negative)
    st.integers(min_value=-10**10, max_value=10**10).map(str),
    # floats with decimal point or exponent
    st.floats(allow_nan=False, allow_infinity=False, width=32).map(lambda f: format(f, '.6g'))
).map(lambda s: '"' + s + '"')

# JSON array of strings (tags)
json_string_array = st.lists(json_string, min_size=0, max_size=4).map(
    lambda lst: '[' + ','.join(lst) + ']'
)

# JSON enum for status
status_values = ['"active"', '"inactive"', '"unknown"']
json_status = st.sampled_from(status_values)

# id field: integer or double (to trigger divergence)
# manual and built_value require int (json['id'] as int)
# json_serializable and freezed accept double and convert to int via toInt()
# We produce either a JSON integer literal or a JSON number literal with decimal point.
json_id = st.one_of(
    # integer literal as digits (no quotes)
    st.integers(min_value=-2**63, max_value=2**63 - 1).map(str),
    # double literal as digits with decimal point (e.g. 123.0)
    st.floats(allow_nan=False, allow_infinity=False, width=64).filter(
        lambda f: f.is_integer() and -2**63 <= f <= 2**63 - 1
    ).map(lambda f: format(f, '.1f'))
)

# name field: string or null
json_name = st.one_of(json_string, st.just('null'))

# child field: null or a nested record (one level recursion)
# To avoid infinite recursion, child record is always null or a record with child=null.
# We reuse the same record strategy but with child forced null.
@st.composite
def json_record_nochild(draw):
    # id
    id_val = draw(json_id)
    # amount string
    amount_val = draw(json_number_str)
    # name string or null
    name_val = draw(json_name)
    # status enum
    status_val = draw(json_status)
    # tags array (sometimes missing to trigger divergence)
    # We vary presence of tags to trigger built_value vs others divergence.
    tags_present = draw(st.booleans())
    if tags_present:
        tags_val = draw(json_string_array)
        tags_field = '"tags":' + tags_val
    else:
        tags_field = None
    # child always null here
    child_val = 'null'

    fields = [
        '"id":' + id_val,
        '"amount":' + amount_val,
        '"name":' + name_val,
        '"status":' + status_val,
    ]
    if tags_field is not None:
        fields.append(tags_field)
    fields.append('"child":' + child_val)

    return '{' + ','.join(fields) + '}'

@st.composite
def json_record(draw):
    # id
    id_val = draw(json_id)
    # amount string
    amount_val = draw(json_number_str)
    # name string or null
    name_val = draw(json_name)
    # status enum
    status_val = draw(json_status)
    # tags array (sometimes missing)
    tags_present = draw(st.booleans())
    if tags_present:
        tags_val = draw(json_string_array)
        tags_field = '"tags":' + tags_val
    else:
        tags_field = None
    # child: null or nested record (one level)
    child_present = draw(st.booleans())
    if child_present:
        child_val = draw(json_record_nochild())
    else:
        child_val = 'null'

    fields = [
        '"id":' + id_val,
        '"amount":' + amount_val,
        '"name":' + name_val,
        '"status":' + status_val,
    ]
    if tags_field is not None:
        fields.append(tags_field)
    fields.append('"child":' + child_val)

    return '{' + ','.join(fields) + '}'

@st.composite
def generated_json(draw) -> bytes:
    # Generate a top-level record JSON string
    s = draw(json_record())
    return s.encode('utf-8')