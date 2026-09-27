from hypothesis import strategies as st

# Constants for enum values and known divergences
STATUS_ENUMS = ['"active"', '"inactive"', '"unknown"']
INVALID_STATUS_ENUMS = ['"enabled"', '"ACTIVE"', 'null', '123', 'true', 'false', '""']
# For name field: string, null, number (as number or string), boolean (to test rejection)
NAME_VALID = [lambda s: s, lambda s: "null"]
NAME_INVALID = ['123', 'true', 'false', '[]', '{}']

# For amount: string or number (kotlinx rejects number)
# For id: integer or string integer
# For tags: array of strings normally, but can test nulls, non-string elements, or non-array
# For child: null or nested record (one level recursion max)

# Helper to produce JSON string literal with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # minimal escaping for " and \ (no control chars expected in test)
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Compose a record JSON text from fields given as strings (already JSON encoded)
def record_json(id_json, amount_json, name_json, status_json, tags_json, child_json):
    # Compose fields in fixed order with commas
    # All fields always present (except child can be null)
    return (
        '{'
        + '"id":' + id_json + ','
        + '"amount":' + amount_json + ','
        + '"name":' + name_json + ','
        + '"status":' + status_json + ','
        + '"tags":' + tags_json + ','
        + '"child":' + child_json
        + '}'
    )

# Strategy for id: integer or string integer
id_strategy = st.one_of(
    st.integers(min_value=0, max_value=10**6).map(str),
    st.integers(min_value=0, max_value=10**6).map(lambda i: json_string_literal(str(i))),
)

# Strategy for amount: string or number (kotlinx rejects number)
amount_strategy = st.one_of(
    st.text(min_size=1, max_size=10).map(json_string_literal),
    st.floats(allow_nan=False, allow_infinity=False, width=32).map(lambda f: str(f) if f % 1 else str(int(f))),
)

# Strategy for name: string or null or number (as number or string) or boolean (to test rejection)
name_strategy = st.one_of(
    st.none().map(lambda _: "null"),
    st.text(min_size=0, max_size=10).map(json_string_literal),
    st.integers(min_value=-1000, max_value=1000).map(str),
    st.integers(min_value=-1000, max_value=1000).map(lambda i: json_string_literal(str(i))),
    st.booleans().map(lambda b: "true" if b else "false"),
)

# Strategy for status: valid enum or invalid enum (to test rejection)
status_strategy = st.one_of(
    st.sampled_from(STATUS_ENUMS),
    st.sampled_from(INVALID_STATUS_ENUMS),
)

# Strategy for tags: array of strings normally, but can test nulls, non-string elements, or non-array
# We want mostly arrays of strings, sometimes arrays with null or numbers or booleans or empty array, sometimes invalid (non-array)
tags_valid_element = st.one_of(
    st.text(min_size=0, max_size=10).map(json_string_literal),
    st.none().map(lambda _: "null"),
    st.integers(min_value=-1000, max_value=1000).map(str),
    st.booleans().map(lambda b: "true" if b else "false"),
)
tags_array_strategy = st.lists(tags_valid_element, min_size=0, max_size=5).map(
    lambda elems: '[' + ','.join(elems) + ']'
)
tags_non_array_strategy = st.one_of(
    st.none().map(lambda _: "null"),
    st.text(min_size=0, max_size=10).map(json_string_literal),
    st.integers(min_value=-1000, max_value=1000).map(str),
    st.booleans().map(lambda b: "true" if b else "false"),
    st.just('{}'),
    st.just('123'),
)
tags_strategy = st.one_of(
    tags_array_strategy,
    tags_non_array_strategy,
)

# Recursive child record strategy with bounded depth (max 1 level)
# To avoid infinite recursion, child can be null or a record with child=null only
@st.composite
def child_strategy(draw):
    # 50% null, 50% nested record with child=null
    is_null = draw(st.booleans())
    if is_null:
        return "null"
    else:
        # nested record with child=null (no deeper recursion)
        id_json = draw(id_strategy)
        amount_json = draw(amount_strategy)
        name_json = draw(name_strategy)
        status_json = draw(status_strategy)
        tags_json = draw(tags_strategy)
        child_json = "null"
        return record_json(id_json, amount_json, name_json, status_json, tags_json, child_json)

# Compose the top-level record with one or two fields tweaked to produce divergences
@st.composite
def generated_json(draw) -> bytes:
    # Start with a valid base record (all fields well-formed)
    base_id = draw(id_strategy)
    base_amount = draw(st.text(min_size=1, max_size=10).map(json_string_literal))
    base_name = draw(st.one_of(st.none().map(lambda _: "null"), st.text(min_size=0, max_size=10).map(json_string_literal)))
    base_status = draw(st.sampled_from(STATUS_ENUMS))
    base_tags = draw(st.lists(st.text(min_size=0, max_size=10).map(json_string_literal), min_size=0, max_size=5).map(
        lambda elems: '[' + ','.join(elems) + ']'
    ))
    base_child = draw(st.one_of(st.none().map(lambda _: "null"), child_strategy()))

    # Now decide which divergence to inject (one or two fields off)
    # Weighted choices to maximize known divergences:
    divergence_type = draw(st.sampled_from([
        "amount_number_vs_string",       # amount as number (kotlinx rejects number)
        "name_nonstring",                # name as number or boolean (kotlinx rejects non-string non-null)
        "status_invalid_enum",           # invalid enum (Gson accepts null, others reject)
        "tags_non_array",                # tags not array (all reject except Gson?)
        "tags_array_with_null",          # tags array with null (kotlinx rejects)
        "child_empty_object",            # child empty object (Gson accepts, others reject)
        "unknown_field_in_child",        # unknown field in child (Gson, Moshi ignore, others reject)
        "amount_null_in_child",          # amount null in child (Gson accepts, others reject)
        "tags_null_in_child",            # tags null in child (Gson accepts, others reject)
        "name_number_string_vs_number", # name as number string vs number (Gson, Moshi accept both, kotlinx rejects number)
    ]))

    # Prepare fields to override
    id_json = base_id
    amount_json = base_amount
    name_json = base_name
    status_json = base_status
    tags_json = base_tags
    child_json = base_child

    # Apply divergence tweaks
    if divergence_type == "amount_number_vs_string":
        # amount as number (kotlinx rejects number)
        amount_json = draw(st.one_of(
            st.floats(allow_nan=False, allow_infinity=False, width=32).map(lambda f: str(f) if f % 1 else str(int(f))),
            st.text(min_size=1, max_size=10).map(json_string_literal)
        ))
    elif divergence_type == "name_nonstring":
        # name as number or boolean (kotlinx rejects non-string non-null)
        name_json = draw(st.one_of(
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
        ))
    elif divergence_type == "status_invalid_enum":
        # invalid enum (Gson accepts null, others reject)
        status_json = draw(st.sampled_from(INVALID_STATUS_ENUMS))
    elif divergence_type == "tags_non_array":
        # tags not array (all reject except Gson?)
        tags_json = draw(st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=1, max_size=10).map(json_string_literal),
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
            st.just('{}'),
            st.just('123'),
        ))
    elif divergence_type == "tags_array_with_null":
        # tags array with null (kotlinx rejects)
        tags_json = draw(st.lists(
            st.one_of(
                st.text(min_size=0, max_size=10).map(json_string_literal),
                st.none().map(lambda _: "null")
            ),
            min_size=1, max_size=5
        ).map(lambda elems: '[' + ','.join(elems) + ']'))
    elif divergence_type == "child_empty_object":
        # child empty object {} (Gson accepts, others reject)
        child_json = "{}"
    elif divergence_type == "unknown_field_in_child":
        # child with unknown field (Gson, Moshi ignore, others reject)
        # Compose a valid child record plus unknown field
        id_c = draw(id_strategy)
        amount_c = draw(amount_strategy)
        name_c = draw(name_strategy)
        status_c = draw(status_strategy)
        tags_c = draw(tags_strategy)
        # unknown field "unknownField": 123
        child_json = (
            '{'
            + '"id":' + id_c + ','
            + '"amount":' + amount_c + ','
            + '"name":' + name_c + ','
            + '"status":' + status_c + ','
            + '"tags":' + tags_c + ','
            + '"child":null,'
            + '"unknownField":123'
            + '}'
        )
    elif divergence_type == "amount_null_in_child":
        # child with amount=null (Gson accepts, others reject)
        id_c = draw(id_strategy)
        name_c = draw(name_strategy)
        status_c = draw(status_strategy)
        tags_c = draw(tags_strategy)
        child_json = (
            '{'
            + '"id":' + id_c + ','
            + '"amount":null,'
            + '"name":' + name_c + ','
            + '"status":' + status_c + ','
            + '"tags":' + tags_c + ','
            + '"child":null'
            + '}'
        )
    elif divergence_type == "tags_null_in_child":
        # child with tags=null (Gson accepts, others reject)
        id_c = draw(id_strategy)
        amount_c = draw(amount_strategy)
        name_c = draw(name_strategy)
        status_c = draw(status_strategy)
        child_json = (
            '{'
            + '"id":' + id_c + ','
            + '"amount":' + amount_c + ','
            + '"name":' + name_c + ','
            + '"status":' + status_c + ','
            + '"tags":null,'
            + '"child":null'
            + '}'
        )
    elif divergence_type == "name_number_string_vs_number":
        # name as number string vs number (Gson, Moshi accept both, kotlinx rejects number)
        # randomly pick one of these two
        name_json = draw(st.one_of(
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.integers(min_value=-1000, max_value=1000).map(lambda i: json_string_literal(str(i))),
        ))

    # Compose final JSON text
    json_text = record_json(id_json, amount_json, name_json, status_json, tags_json, child_json)

    # Return as bytes (UTF-8)
    return json_text.encode('utf-8')