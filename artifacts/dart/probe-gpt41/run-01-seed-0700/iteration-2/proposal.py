from hypothesis import strategies as st

# Constants for known valid values
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper: produce a JSON string literal from a Python string (no escapes needed for test)
def json_string_literal(s: str) -> str:
    # Minimal escaping for quotes and backslashes
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.
    """

    # --- id: integer, required ---
    # Always present and integer (no fuzz here, as wrong type always rejected identically)
    id_val = draw(st.integers(min_value=0, max_value=10**9))

    # --- amount: string, required ---
    # Always present and string (no fuzz here, as wrong type always rejected identically)
    amount_val = draw(st.text(min_size=1, max_size=10))
    amount_json = json_string_literal(amount_val)

    # --- name: string or null, optional (missing treated as null) ---
    # We fuzz presence and null vs string, but never wrong type (e.g. int)
    name_option = draw(st.one_of(
        st.none(),  # null
        st.text(min_size=0, max_size=10).map(json_string_literal),
        st.just(None),  # missing field (None means omit)
    ))
    # name_option == None means omit field

    # --- status: enum string, required ---
    # We fuzz presence, valid values, invalid values (to provoke ArgumentError),
    # and also try null (wrong type)
    status_choice = draw(st.one_of(
        st.sampled_from(STATUS_VALUES),  # valid
        st.just(None),                   # missing field (None means omit)
        st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string_literal),  # invalid enum string
        st.just('null'),                # null literal (wrong type)
    ))

    # --- tags: array of strings, required ---
    # We fuzz presence, empty array, array with strings, array with non-string element (wrong type)
    # and missing field (None means omit)
    tags_option = draw(st.one_of(
        st.lists(st.text(min_size=0, max_size=5).map(json_string_literal), min_size=0, max_size=3).map(lambda lst: '[' + ','.join(lst) + ']'),  # valid array of strings
        st.just('[]'),  # empty array
        st.just(None),  # missing field (None means omit)
        # array with one non-string element (int)
        st.just('[123]'),
        # array with mixed string and non-string
        st.just('["tag1", 42]'),
    ))

    # --- child: Record or null or missing ---
    # We allow one level recursion with bounded depth = 1
    # child can be null, missing, or a nested record (with no further child)
    # We produce a nested record with all required fields valid, but fuzz name and status as above
    # or null or missing

    # To avoid infinite recursion, child record has no child field (always null or missing)
    # We reuse some of the above logic but simpler for child

    # Child id
    child_id = draw(st.integers(min_value=0, max_value=10**9))
    # Child amount
    child_amount = draw(st.text(min_size=1, max_size=10))
    child_amount_json = json_string_literal(child_amount)
    # Child name: string or null or missing
    child_name_option = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=10).map(json_string_literal),
        st.just(None),
    ))
    # Child status: valid enum only (to keep child mostly well-formed)
    child_status = draw(st.sampled_from(STATUS_VALUES))
    # Child tags: valid array of strings or empty array
    child_tags = draw(st.one_of(
        st.lists(st.text(min_size=0, max_size=5).map(json_string_literal), min_size=0, max_size=3).map(lambda lst: '[' + ','.join(lst) + ']'),
        st.just('[]'),
    ))
    # Child child: always null or missing (to avoid deep recursion)
    child_child_option = draw(st.one_of(
        st.just('null'),
        st.just(None),
    ))

    # Compose child JSON object or null or missing
    child_obj_fields = []
    child_obj_fields.append(f'"id":{child_id}')
    child_obj_fields.append(f'"amount":{child_amount_json}')
    if child_name_option is not None:
        child_obj_fields.append(f'"name":{child_name_option}')
    # else omit name
    child_obj_fields.append(f'"status":{child_status}')
    child_obj_fields.append(f'"tags":{child_tags}')
    if child_child_option is not None:
        child_obj_fields.append(f'"child":{child_child_option}')
    # else omit child

    child_obj_json = '{' + ','.join(child_obj_fields) + '}'

    child_option = draw(st.one_of(
        st.just('null'),
        st.just(None),  # omit child field
        st.just(child_obj_json),
    ))

    # --- Compose top-level JSON object fields ---

    fields = []
    fields.append(f'"id":{id_val}')
    fields.append(f'"amount":{amount_json}')
    if name_option is not None:
        fields.append(f'"name":{name_option}')
    # else omit name
    if status_choice is not None:
        fields.append(f'"status":{status_choice}')
    # else omit status
    if tags_option is not None:
        fields.append(f'"tags":{tags_option}')
    # else omit tags
    if child_option is not None:
        fields.append(f'"child":{child_option}')
    # else omit child

    # Shuffle fields order to avoid positional bias
    fields = draw(st.permutations(fields))

    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')