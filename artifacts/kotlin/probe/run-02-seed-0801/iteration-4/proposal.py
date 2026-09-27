from hypothesis import strategies as st

# Helper: JSON string escape for double quotes and backslash only (minimal)
def json_string_escape(s: str) -> str:
    # We cannot import json, so do minimal escaping:
    # Replace \ with \\, " with \"
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text for the Record schema, aiming to produce documents
    that cause divergence among Gson, Moshi, kotlinx.serialization, and Jackson.

    Strategy:
    - Start from a valid record baseline.
    - Vary one or two fields with "almost valid" or borderline values.
    - Use bounded recursion for "child" with depth 0 or 1.
    - Use known divergence points from the problem statement.
    """

    # Constants
    STATUS_ENUMS = ['"active"', '"inactive"', '"unknown"']
    STATUS_INVALIDS = ['"Active"', '"inactivee"', '"unknown "', '123', 'null', 'true', 'false', '""']

    # Base valid values
    base_id_int = st.integers(min_value=0, max_value=2**31-1)
    base_id_str_int = st.integers(min_value=0, max_value=2**31-1).map(lambda i: f'"{i}"')
    base_id = st.one_of(base_id_int.map(str), base_id_str_int)

    base_amount_str = st.text(min_size=1, max_size=10).map(json_string_escape).map(lambda s: f'"{s}"')
    base_amount_num_str = st.floats(allow_nan=False, allow_infinity=False, width=32).map(lambda f: str(int(f) if f.is_integer() else f))
    # amount can be string or number (except kotlinx rejects number)
    amount_str_or_num = st.one_of(base_amount_str, base_amount_num_str)

    # name: string or null normally; Gson/Jackson accept number or bool converted to string
    # Moshi/kotlinx reject non-string non-null
    # We'll vary name among:
    # - null
    # - string
    # - number (as JSON number)
    # - boolean (true/false)
    # - invalid (array, object) to cause rejection by all (less useful)
    name_null = st.just("null")
    name_string = st.text(min_size=0, max_size=10).map(json_string_escape).map(lambda s: f'"{s}"')
    name_number = st.integers(min_value=-1000, max_value=1000).map(str)
    name_boolean = st.sampled_from(["true", "false"])
    # We'll avoid invalid types for name (like array/object) because all reject.

    name_choice = st.one_of(name_null, name_string, name_number, name_boolean)

    # status: exact enum strings accepted by all except Gson accepts invalid but sets null
    # We'll pick either valid enum or invalid enum string or null
    status_valid = st.sampled_from(STATUS_ENUMS)
    status_invalid = st.sampled_from(STATUS_INVALIDS)
    status_choice = st.one_of(status_valid, status_invalid)

    # tags: must be array; non-array rejected by all
    # Elements: strings normally; Gson/Moshi/Jackson accept non-string elements converted to string; kotlinx rejects non-string elements
    # Also null elements accepted by Gson/Moshi/Jackson; rejected by kotlinx
    # We'll vary tags as:
    # - array of strings
    # - array with some non-string elements (number, boolean, null)
    # - empty array
    # - array with null elements
    tag_string = st.text(min_size=0, max_size=5).map(json_string_escape).map(lambda s: f'"{s}"')
    tag_number = st.integers(min_value=-1000, max_value=1000).map(str)
    tag_boolean = st.sampled_from(["true", "false"])
    tag_null = st.just("null")

    tag_element = st.one_of(tag_string, tag_number, tag_boolean, tag_null)
    # To maximize divergence, sometimes all strings, sometimes mixed
    tags_all_strings = st.lists(tag_string, min_size=0, max_size=5)
    tags_mixed = st.lists(tag_element, min_size=1, max_size=5)
    tags_choice = st.one_of(tags_all_strings, tags_mixed)

    # child: null or nested record (depth 1 max)
    # We'll recursively generate child with depth control
    def gen_child(depth: int):
        if depth <= 0:
            return st.just("null")
        else:
            # Generate a nested record with depth-1
            return record_strategy(depth - 1)

    # id field: integer or string convertible to integer
    id_field = base_id

    # amount field: string or number (kotlinx rejects number)
    amount_field = amount_str_or_num

    # name field: string, null, number, boolean
    name_field = name_choice

    # status field: valid or invalid enum string
    status_field = status_choice

    # tags field: array of strings or mixed elements
    tags_field = tags_choice

    # child field: null or nested record
    # We'll generate child with 50% chance null, 50% nested
    # To avoid too large documents, limit recursion depth to 1
    def record_strategy(depth: int):
        return st.fixed_dictionaries({
            "id": id_field,
            "amount": amount_field,
            "name": name_field,
            "status": status_field,
            "tags": tags_field,
            "child": gen_child(depth)
        }).map(record_to_json)

    # Convert record dict of strings (already JSON fragments) to JSON text
    def record_to_json(d: dict) -> str:
        # d fields are JSON fragments (strings) for each field value
        # Compose JSON object text
        # Fields order fixed for consistency
        parts = []
        parts.append(f'"id":{d["id"]}')
        parts.append(f'"amount":{d["amount"]}')
        parts.append(f'"name":{d["name"]}')
        parts.append(f'"status":{d["status"]}')
        parts.append(f'"tags":[{",".join(d["tags"]) if isinstance(d["tags"], list) else d["tags"]}]' if isinstance(d["tags"], list) else f'"tags":{d["tags"]}')
        # child is JSON text or "null"
        parts.append(f'"child":{d["child"]}')
        return "{" + ",".join(parts) + "}"

    # Because tags_field is a list of JSON fragments, but record_strategy expects tags as list of strings,
    # we need to adjust tags_field to produce list of JSON fragments (strings) for tags elements.

    # So redefine tags_field to produce list of JSON fragments (strings)
    tags_field = st.one_of(
        st.lists(tag_string, min_size=0, max_size=5),
        st.lists(tag_element, min_size=1, max_size=5),
    )

    # Now generate top-level record with depth=1
    record = record_strategy(depth=1)

    # Return bytes of JSON text
    return record.map(lambda s: s.encode("utf-8")).example() if False else record.map(lambda s: s.encode("utf-8"))