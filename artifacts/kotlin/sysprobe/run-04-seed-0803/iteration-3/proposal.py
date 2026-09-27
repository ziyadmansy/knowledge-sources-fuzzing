from hypothesis import strategies as st

# Constants for enum values and JSON literals
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
STATUS_UNKNOWN = '"unknown_status"'
NULL = "null"

# Helper to produce a JSON string literal with proper escaping for simple ASCII subset
def json_string(s: str) -> str:
    # Escape backslash and double quote minimally
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Compose a JSON array of strings, given a list of strings (already JSON string literals)
def json_array_of_strings(strs) -> str:
    return "[" + ",".join(strs) + "]"

# Compose a JSON object from a list of (key, value) pairs (both strings)
def json_object(pairs) -> str:
    # pairs: list of (key, value) where key is JSON string literal, value is JSON text
    return "{" + ",".join(k + ":" + v for k, v in pairs) + "}"

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON documents as bytes, representing the described record schema,
    with one or two small divergences from well-formedness to maximize divergence
    between Gson, Moshi, kotlinx.serialization, and Jackson.
    """

    # --- Strategies for fields ---

    # id: integer, but can be null or missing or wrong type for divergence
    # We produce a small integer or null or string or missing
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=1000).map(str),
        st.just(NULL),
        st.text(min_size=1, max_size=5).map(json_string),
        st.none(),  # for missing
    )

    # amount: string, but can be null, missing, number, or wrong type
    amount_strategy = st.one_of(
        st.text(min_size=1, max_size=10).map(json_string),
        st.just(NULL),
        st.integers(min_value=0, max_value=10000).map(str),
        st.none(),  # missing
    )

    # name: string or null, nullable field
    name_strategy = st.one_of(
        st.text(min_size=0, max_size=10).map(json_string),
        st.just(NULL),
        st.none(),  # missing
    )

    # status: enum string, or null, or unknown variant, or missing
    status_strategy = st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.just(NULL),
        st.just(STATUS_UNKNOWN),
        st.none(),  # missing
    )

    # tags: array of strings, but can be null, missing, or array of ints, or empty array
    # We produce arrays of strings or ints coerced to strings, or null, or missing
    tags_strings = st.lists(st.text(min_size=1, max_size=5).map(json_string), min_size=0, max_size=3)
    tags_ints = st.lists(st.integers(min_value=0, max_value=100).map(str), min_size=0, max_size=3)
    tags_strategy = st.one_of(
        tags_strings.map(json_array_of_strings),
        tags_ints.map(json_array_of_strings),
        st.just(NULL),
        st.none(),  # missing
    )

    # child: either null, missing, or a nested record (one level only)
    # To keep recursion bounded, child record will have no child itself (child=null)
    # We allow child to be missing or null or a nested record with no child
    # We reuse the same field strategies but force child.child to null or missing

    # For child record fields, disallow missing to reduce complexity, but allow null and some divergences
    def child_field_strategy(field_name):
        if field_name == "id":
            return st.one_of(
                st.integers(min_value=0, max_value=1000).map(str),
                st.just(NULL),
            )
        elif field_name == "amount":
            return st.one_of(
                st.text(min_size=1, max_size=10).map(json_string),
                st.just(NULL),
                st.integers(min_value=0, max_value=10000).map(str),
            )
        elif field_name == "name":
            return st.one_of(
                st.text(min_size=0, max_size=10).map(json_string),
                st.just(NULL),
            )
        elif field_name == "status":
            return st.one_of(
                st.sampled_from(STATUS_VALUES),
                st.just(NULL),
                st.just(STATUS_UNKNOWN),
            )
        elif field_name == "tags":
            return st.one_of(
                st.lists(st.text(min_size=1, max_size=5).map(json_string), min_size=0, max_size=3).map(json_array_of_strings),
                st.lists(st.integers(min_value=0, max_value=100).map(str), min_size=0, max_size=3).map(json_array_of_strings),
                st.just(NULL),
            )
        elif field_name == "child":
            # For child.child, always null to keep recursion bounded
            return st.just(NULL)
        else:
            raise ValueError("Unknown field for child")

    @st.composite
    def child_record(draw):
        id_val = draw(child_field_strategy("id"))
        amount_val = draw(child_field_strategy("amount"))
        name_val = draw(child_field_strategy("name"))
        status_val = draw(child_field_strategy("status"))
        tags_val = draw(child_field_strategy("tags"))
        child_val = draw(child_field_strategy("child"))  # always null here

        # Compose child object with all fields present (no missing)
        pairs = [
            (json_string("id"), id_val),
            (json_string("amount"), amount_val),
            (json_string("name"), name_val),
            (json_string("status"), status_val),
            (json_string("tags"), tags_val),
            (json_string("child"), child_val),
        ]
        return json_object(pairs)

    # child field strategy: null, missing, or nested record
    child_field_outer_strategy = st.one_of(
        child_record(),
        st.just(NULL),
        st.none(),  # missing
    )

    # --- Compose top-level record ---

    # Draw all fields
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_strategy)
    status_val = draw(status_strategy)
    tags_val = draw(tags_strategy)
    child_val = draw(child_field_outer_strategy)

    # Build list of present fields (skip those with None == missing)
    fields = []
    if id_val is not None:
        fields.append((json_string("id"), id_val))
    if amount_val is not None:
        fields.append((json_string("amount"), amount_val))
    if name_val is not None:
        fields.append((json_string("name"), name_val))
    if status_val is not None:
        fields.append((json_string("status"), status_val))
    if tags_val is not None:
        fields.append((json_string("tags"), tags_val))
    if child_val is not None:
        fields.append((json_string("child"), child_val))

    # To increase divergence, randomly add one unknown extra key (accepted by Gson and Moshi, rejected by others)
    add_extra_key = draw(st.booleans())
    if add_extra_key:
        extra_key = json_string("extra_unknown_key")
        extra_val = draw(st.one_of(
            st.text(min_size=1, max_size=5).map(json_string),
            st.integers(min_value=0, max_value=100).map(str),
            st.just(NULL),
            st.just("true"),
            st.just("false"),
        ))
        fields.append((extra_key, extra_val))

    # To increase divergence, randomly duplicate one key with a different value (last wins)
    add_duplicate_key = draw(st.booleans())
    if add_duplicate_key and fields:
        # Pick a random existing key to duplicate
        dup_index = draw(st.integers(min_value=0, max_value=len(fields)-1))
        dup_key = fields[dup_index][0]
        # Generate a different value for duplicate key
        # For simplicity, if key is "id" or "amount" or "status" or "tags" or "name" or "child", generate a plausible different value
        key_text = dup_key[1:-1]  # remove quotes
        if key_text == "id":
            dup_val = draw(st.one_of(
                st.integers(min_value=0, max_value=1000).map(str),
                st.just(NULL),
                st.text(min_size=1, max_size=5).map(json_string),
            ))
        elif key_text == "amount":
            dup_val = draw(st.one_of(
                st.text(min_size=1, max_size=10).map(json_string),
                st.just(NULL),
                st.integers(min_value=0, max_value=10000).map(str),
            ))
        elif key_text == "name":
            dup_val = draw(st.one_of(
                st.text(min_size=0, max_size=10).map(json_string),
                st.just(NULL),
            ))
        elif key_text == "status":
            dup_val = draw(st.one_of(
                st.sampled_from(STATUS_VALUES),
                st.just(NULL),
                st.just(STATUS_UNKNOWN),
            ))
        elif key_text == "tags":
            dup_val = draw(st.one_of(
                st.lists(st.text(min_size=1, max_size=5).map(json_string), min_size=0, max_size=3).map(json_array_of_strings),
                st.lists(st.integers(min_value=0, max_value=100).map(str), min_size=0, max_size=3).map(json_array_of_strings),
                st.just(NULL),
            ))
        elif key_text == "child":
            dup_val = draw(child_field_outer_strategy)
        else:
            dup_val = draw(st.one_of(
                st.text(min_size=1, max_size=5).map(json_string),
                st.integers(min_value=0, max_value=100).map(str),
                st.just(NULL),
            ))

        fields.append((dup_key, dup_val))

    # Compose final JSON object text
    json_text = json_object(fields)

    # Return bytes (UTF-8)
    return json_text.encode("utf-8")