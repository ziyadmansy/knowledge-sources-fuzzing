from hypothesis import strategies as st

# Constants for enum values and JSON literals
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
NULL = "null"

# Helper to produce JSON string literal with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # Minimal escaping for quotes and backslashes
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw, _depth=0) -> bytes:
    """
    Generate JSON text for the Record schema with controlled variations to maximize
    divergence among Gson, Moshi, kotlinx.serialization, and Jackson Kotlin module.
    """

    # Limit recursion depth to 1 (only one level of child)
    max_depth = 1

    # --- id field ---
    # id is integer, non-nullable
    # Known divergences:
    # - Gson and Jackson accept null for id (decode as 0)
    # - Gson accepts missing id (decode as 0)
    # - Moshi and kotlinx reject missing or null id
    # So id can be:
    # - present integer
    # - present null
    # - missing (only if depth==0, because child is optional)
    id_present = True
    if _depth == 0:
        # At top level, allow missing id sometimes to trigger divergence
        id_present = draw(st.booleans())
    if id_present:
        # id can be integer or null (null triggers divergence)
        id_val = draw(st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            st.just(NULL)
        ))
    else:
        id_val = None  # missing

    # --- amount field ---
    # amount is string, non-nullable
    # Known divergences:
    # - Gson and Jackson accept null (decode as null)
    # - Moshi and kotlinx reject null
    # - Gson, Moshi, Jackson accept number coercing to string
    # - Moshi and kotlinx reject missing amount
    # So amount can be:
    # - string (normal)
    # - null
    # - number (int or float)
    # - missing (only if depth==0, but Moshi and kotlinx reject missing)
    amount_present = True
    if _depth == 0:
        amount_present = draw(st.booleans())
    if amount_present:
        amount_val = draw(st.one_of(
            st.text(min_size=1, max_size=10).map(json_string_literal),
            st.just(NULL),
            st.integers(min_value=0, max_value=100000).map(str),
            st.floats(allow_infinity=False, allow_nan=False).map(lambda f: format(f, '.6g'))
        ))
    else:
        amount_val = None  # missing

    # --- name field ---
    # name is string or null, nullable
    # Known divergences: none specifically noted for name
    # Accept null or string, always present (required)
    # Moshi and kotlinx reject missing required fields, so always present
    name_val = draw(st.one_of(
        st.none().map(lambda _: NULL),
        st.text(min_size=0, max_size=20).map(json_string_literal)
    ))

    # --- status field ---
    # enum: "active", "inactive", "unknown"
    # Known divergences:
    # - Gson accepts unknown or case-variant as null
    # - Moshi, kotlinx, Jackson reject unknown or case-variant
    # - Gson and Jackson accept null (decode as null)
    # - Moshi and kotlinx reject null
    # So status can be:
    # - one of enum values (normal)
    # - null
    # - unknown string (e.g. "Active", "invalid", "ACTIVE")
    # - missing (Moshi and kotlinx reject missing)
    status_present = True
    if _depth == 0:
        status_present = draw(st.booleans())
    if status_present:
        status_val = draw(st.one_of(
            st.sampled_from(STATUS_VALUES),
            st.just(NULL),
            st.sampled_from(['"Active"', '"inactivee"', '"INVALID"', '"ACTIVE"', '"unknowns"'])
        ))
    else:
        status_val = None  # missing

    # --- tags field ---
    # array of strings, non-nullable
    # Known divergences:
    # - Gson and Jackson accept null (decode as null)
    # - Moshi and kotlinx reject null
    # - Gson, Moshi, Jackson accept arrays of integers coercing to strings
    # - Moshi and kotlinx reject missing
    tags_present = True
    if _depth == 0:
        tags_present = draw(st.booleans())
    if tags_present:
        # tags can be:
        # - null
        # - array of strings
        # - array of integers (coerced to strings by Gson, Moshi, Jackson)
        tags_type = draw(st.sampled_from(['null', 'str_array', 'int_array']))
        if tags_type == 'null':
            tags_val = NULL
        elif tags_type == 'str_array':
            # array of strings, possibly empty
            arr = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
            arr_json = "[" + ",".join(json_string_literal(s) for s in arr) + "]"
            tags_val = arr_json
        else:  # int_array
            arr = draw(st.lists(st.integers(min_value=0, max_value=1000), max_size=5))
            arr_json = "[" + ",".join(str(i) for i in arr) + "]"
            tags_val = arr_json
    else:
        tags_val = None  # missing

    # --- child field ---
    # child is Record or null, nullable
    # Known divergences:
    # - Gson and Moshi accept missing child
    # - kotlinx rejects missing child
    # - Jackson accepts missing child
    # - Gson and Jackson accept null child
    # - Moshi and kotlinx reject null child
    # So child can be:
    # - missing (only at top level)
    # - null
    # - a nested record (one level only)
    child_present = True
    if _depth == 0:
        child_present = draw(st.booleans())
    if child_present:
        child_null = draw(st.booleans())
        if child_null:
            child_val = NULL
        else:
            # nested record, depth+1
            if _depth < max_depth:
                child_val = (yield generated_json(_depth=_depth+1)).decode()
            else:
                # At max depth, child must be null or missing, so null here
                child_val = NULL
    else:
        child_val = None  # missing

    # --- extra unknown keys ---
    # Gson and Moshi accept unknown keys; kotlinx and Jackson reject
    # Add zero or one unknown key to trigger divergence
    add_unknown = draw(st.booleans())
    unknown_key = '"unknown_key"'
    unknown_val = '"unknown_value"'

    # --- duplicate keys ---
    # All accept duplicate keys, last wins
    # We can add duplicates for one field to see if it triggers divergence
    # But no known divergence from duplicates, so keep minimal duplicates
    # Optionally duplicate one field once
    duplicate_field = draw(st.sampled_from([None, "id", "amount", "name", "status", "tags", "child"]))
    duplicate_value = None
    if duplicate_field is not None:
        # For duplicate value, produce a different value than original to test last-wins
        if duplicate_field == "id":
            if id_val is None:
                duplicate_value = "123"
            else:
                duplicate_value = "0" if id_val != "0" else "1"
        elif duplicate_field == "amount":
            if amount_val is None:
                duplicate_value = json_string_literal("dup")
            else:
                duplicate_value = json_string_literal("dup") if amount_val != json_string_literal("dup") else json_string_literal("dup2")
        elif duplicate_field == "name":
            duplicate_value = NULL if name_val != NULL else json_string_literal("dupname")
        elif duplicate_field == "status":
            duplicate_value = '"active"' if status_val != '"active"' else '"inactive"'
        elif duplicate_field == "tags":
            duplicate_value = "null" if tags_val != "null" else "[]"
        elif duplicate_field == "child":
            duplicate_value = NULL if child_val != NULL else "{}"
    else:
        duplicate_value = None

    # --- Compose JSON object fields as strings ---
    fields = []

    def add_field(key, val):
        if val is not None:
            fields.append(f'"{key}":{val}')

    # Add fields in fixed order for readability
    add_field("id", id_val)
    add_field("amount", amount_val)
    add_field("name", name_val)
    add_field("status", status_val)
    add_field("tags", tags_val)
    add_field("child", child_val)

    # Add unknown key if requested
    if add_unknown:
        fields.append(f'{unknown_key}:{unknown_val}')

    # Add duplicate field if requested
    if duplicate_field is not None and duplicate_value is not None:
        # Insert duplicate field at random position (simulate duplicate keys)
        # For simplicity, append duplicate at end
        fields.append(f'"{duplicate_field}":{duplicate_value}')

    # Compose JSON object text
    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")