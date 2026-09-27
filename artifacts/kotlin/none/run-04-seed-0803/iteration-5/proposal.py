from hypothesis import strategies as st

# Constants for the schema
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce a JSON string literal with proper escaping for quotes and backslashes
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote for JSON string literal
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw, _depth=0):
    """
    Generate JSON text for the described schema, with controlled deviations
    to provoke divergence among Gson, Moshi, kotlinx.serialization, and Jackson.

    _depth controls recursion depth for the "child" field.
    """

    # To encourage divergence, we produce mostly well-formed documents with
    # exactly one or two fields having subtle type or presence deviations.

    # Base valid fields:
    # id: integer
    # amount: string
    # name: string or null
    # status: one of "active", "inactive", "unknown"
    # tags: array of strings
    # child: record or null (one level recursion max)

    # Strategy to produce a valid id or a subtly invalid id (e.g. string instead of int)
    id_valid = st.integers(min_value=0, max_value=10**9).map(str)
    id_invalid = st.one_of(
        st.text(min_size=1, max_size=5).map(json_string_literal),  # string instead of int
        st.floats(allow_nan=False, allow_infinity=False).map(lambda f: str(f)),  # float instead of int
        st.just("null"),  # null instead of int
        st.just("true"),  # boolean instead of int
    )
    # id field: mostly valid, sometimes invalid
    id_field = st.one_of(
        id_valid.map(lambda v: ('"id":' + v, True)),
        id_invalid.map(lambda v: ('"id":' + v, False)),
    )

    # amount: string, but sometimes number or null or boolean
    amount_valid = st.text(min_size=1, max_size=10).map(json_string_literal)
    amount_invalid = st.one_of(
        st.integers(min_value=0, max_value=1000).map(str),
        st.just("null"),
        st.just("true"),
        st.just("123.45"),  # number as string but unquoted
    )
    amount_field = st.one_of(
        amount_valid.map(lambda v: ('"amount":' + v, True)),
        amount_invalid.map(lambda v: ('"amount":' + v, False)),
    )

    # name: string or null, sometimes number or boolean or missing
    name_valid = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(json_string_literal),
    )
    name_invalid = st.one_of(
        st.integers(min_value=0, max_value=1000).map(str),
        st.just("true"),
        st.just("false"),
    )
    # Also sometimes omit name field entirely (simulate missing)
    # We'll handle missing by returning None for the field tuple
    name_field = st.one_of(
        name_valid.map(lambda v: ('"name":' + v, True)),
        name_invalid.map(lambda v: ('"name":' + v, False)),
        st.just(None),  # missing field
    )

    # status: one of "active", "inactive", "unknown" (string literals)
    # Sometimes invalid string, number, boolean, or null
    status_valid = st.sampled_from(STATUS_VALUES)
    status_invalid = st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: ('"' + s + '"') not in STATUS_VALUES).map(json_string_literal),
        st.integers(min_value=0, max_value=10).map(str),
        st.just("null"),
        st.just("true"),
    )
    status_field = st.one_of(
        status_valid.map(lambda v: ('"status":' + v, True)),
        status_invalid.map(lambda v: ('"status":' + v, False)),
    )

    # tags: array of strings
    # Valid: ["tag1", "tag2"]
    # Invalid: array with non-string elements, or not an array at all
    tag_str = st.text(min_size=1, max_size=5).map(json_string_literal)
    tags_valid = st.lists(tag_str, min_size=0, max_size=5).map(
        lambda lst: '[' + ','.join(lst) + ']'
    )
    tags_invalid = st.one_of(
        st.integers(min_value=0, max_value=10).map(str),  # number instead of array
        st.just("null"),
        st.just("true"),
        st.lists(st.one_of(st.integers(min_value=0, max_value=10).map(str), st.just("null")), min_size=1, max_size=3).map(
            lambda lst: '[' + ','.join(lst) + ']'
        ),  # array of non-strings
    )
    tags_field = st.one_of(
        tags_valid.map(lambda v: ('"tags":' + v, True)),
        tags_invalid.map(lambda v: ('"tags":' + v, False)),
    )

    # child: either null or a nested record (one level max)
    # To avoid deep recursion, only recurse if _depth == 0
    if _depth == 0:
        # Generate child record or null
        child_null = st.just(('null', True))
        # For child record, recursively call generated_json with _depth=1,
        # but strip outer braces to embed as value of "child" field
        # We'll generate full JSON text for child record, then embed it as value
        child_record = generated_json(_depth=1).map(lambda s: (s.decode('utf-8'), True))
        child_field_value = st.one_of(child_null, child_record)
    else:
        # At depth 1, no further recursion, only null or invalid values
        child_field_value = st.one_of(
            st.just(('null', True)),
            st.just(('123', False)),
            st.just(('true', False)),
            st.just(('""', False)),
        )

    # Compose the record fields
    # Draw all fields
    id_f, id_valid_flag = draw(id_field)
    amount_f, amount_valid_flag = draw(amount_field)
    name_f = None
    name_valid_flag = True
    while True:
        name_f_candidate = draw(name_field)
        # If missing, break
        if name_f_candidate is None:
            name_f = None
            name_valid_flag = True  # missing field is invalid per schema but we treat as valid presence for now
            break
        else:
            name_f, name_valid_flag = name_f_candidate
            break

    status_f, status_valid_flag = draw(status_field)
    tags_f, tags_valid_flag = draw(tags_field)
    child_val, child_valid_flag = draw(child_field_value)

    # We want exactly one or two fields to be invalid or missing to provoke divergence
    # Count invalid fields (including missing name)
    invalid_count = sum([
        not id_valid_flag,
        not amount_valid_flag,
        not name_valid_flag if name_f is not None else 0,
        not status_valid_flag,
        not tags_valid_flag,
        not child_valid_flag,
    ])
    # If name is missing, count as 1 invalid field (to provoke divergence)
    if name_f is None:
        invalid_count += 1

    # We want invalid_count to be 1 or 2 to maximize divergence chances
    # Reject draws with 0 or >2 invalid fields by resampling
    if invalid_count == 0 or invalid_count > 2:
        # Reject and resample
        return draw(generated_json(_depth=_depth))

    # Build JSON text for the record
    # Fields order fixed: id, amount, name (if present), status, tags, child
    fields = []
    fields.append(id_f)
    fields.append(amount_f)
    if name_f is not None:
        fields.append(name_f)
    # else omit name field entirely
    fields.append(status_f)
    fields.append(tags_f)
    # child field is always present
    fields.append('"child":' + child_val)

    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')