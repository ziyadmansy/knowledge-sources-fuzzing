from hypothesis import strategies as st

# Helper: JSON string with proper escaping of quotes and backslashes only (minimal)
def json_string(draw):
    # Use Hypothesis built-in string with limited chars to avoid complex escaping
    s = draw(st.text(alphabet=st.characters(blacklist_characters=['"', '\\', '\b', '\f', '\n', '\r', '\t']), min_size=0, max_size=10))
    # Escape backslash and quote for JSON string
    s_esc = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s_esc}"'

# Helper: JSON array of strings
def json_string_array(draw):
    # Array length 0..3 for bounded size
    arr_len = draw(st.integers(min_value=0, max_value=3))
    elems = [json_string(draw) for _ in range(arr_len)]
    return '[' + ','.join(elems) + ']'

# Recursive record generator, bounded depth 0 or 1 for "child"
@st.composite
def record(draw, allow_missing_tags=False, allow_missing_name=False, allow_missing_child=False, allow_id_double=False):
    # id: integer or (for json_serializable/freezed) double that will be toInt()-ed
    # To trigger divergence, sometimes produce a double for id (e.g. 1.0)
    if allow_id_double:
        # produce a double that is an integer value (e.g. 1.0) or a large double outside int64 range
        id_choice = draw(st.one_of(
            st.integers(min_value=-(2**53), max_value=2**53).map(float),  # safe double integer
            st.floats(min_value=-(2**63)*2, max_value=(2**63)*2, allow_infinity=False, allow_nan=False)
        ))
        # Format double as JSON number with decimal point to ensure double, not int
        if id_choice == int(id_choice):
            id_str = f'{id_choice:.1f}'
        else:
            id_str = repr(id_choice)
    else:
        id_int = draw(st.integers(min_value=-(2**53), max_value=2**53))
        id_str = str(id_int)

    # amount: string, non-null always present
    amount_str = json_string(draw)

    # name: string or null or missing (nullable)
    if allow_missing_name:
        name_present = draw(st.booleans())
        if name_present:
            name_val = draw(st.one_of(json_string, st.just("null")))
        else:
            name_val = None
    else:
        name_val = draw(st.one_of(json_string, st.just("null")))

    # status: one of "active", "inactive", "unknown"
    status_val = draw(st.sampled_from(['"active"', '"inactive"', '"unknown"']))

    # tags: array of strings, or missing if allow_missing_tags
    if allow_missing_tags:
        tags_present = draw(st.booleans())
        if tags_present:
            tags_val = json_string_array(draw)
        else:
            tags_val = None
    else:
        tags_val = json_string_array(draw)

    # child: null or record or missing if allow_missing_child
    if allow_missing_child:
        child_present = draw(st.booleans())
        if child_present:
            # child is either null or a record with no recursion (depth 1 max)
            child_val = draw(st.one_of(st.just("null"), record(allow_missing_tags=True, allow_missing_name=True, allow_missing_child=True, allow_id_double=True).map(lambda s: s)))
        else:
            child_val = None
    else:
        child_val = draw(st.one_of(st.just("null"), record(allow_missing_tags=True, allow_missing_name=True, allow_missing_child=True, allow_id_double=True).map(lambda s: s)))

    # Compose fields, omitting those allowed to be missing by setting None
    fields = []

    # id always present
    fields.append(f'"id": {id_str}')

    # amount always present
    fields.append(f'"amount": {amount_str}')

    # name nullable, may be missing
    if name_val is not None:
        fields.append(f'"name": {name_val}')

    # status always present
    fields.append(f'"status": {status_val}')

    # tags nullable, may be missing
    if tags_val is not None:
        fields.append(f'"tags": {tags_val}')

    # child nullable, may be missing
    if child_val is not None:
        fields.append(f'"child": {child_val}')

    # Shuffle fields to avoid positional bias
    from random import shuffle
    shuffle(fields)

    return '{' + ','.join(fields) + '}'

@st.composite
def generated_json(draw) -> bytes:
    # Strategy: produce mostly well-formed records with one or two subtle divergences:
    # - sometimes omit tags (built_value accepts, others reject)
    # - sometimes produce id as double (json_serializable/freezed accept, others reject)
    # - sometimes omit nullable fields (name, child)
    # - sometimes produce child null or nested record
    # - always produce syntactically valid JSON object

    # Choose flags controlling subtle divergences
    allow_missing_tags = draw(st.booleans())  # triggers built_value acceptance divergence
    allow_id_double = draw(st.booleans())     # triggers id decoding divergence
    allow_missing_name = draw(st.booleans())  # nullable field missing allowed
    allow_missing_child = draw(st.booleans()) # nullable field missing allowed

    # Generate top-level record with these flags
    top_record = draw(record(
        allow_missing_tags=allow_missing_tags,
        allow_missing_name=allow_missing_name,
        allow_missing_child=allow_missing_child,
        allow_id_double=allow_id_double,
    ))

    # Return as bytes (UTF-8)
    return top_record.encode('utf-8')