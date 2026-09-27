from hypothesis import strategies as st

# Constants for enum values and JSON syntax helpers
ENUM_VALUES = ['"active"', '"inactive"', '"unknown"']
EMPTY_OBJ = '{}'
EMPTY_ARRAY = '[]'

# Helper to produce JSON string literal from a Python string (escaping quotes and backslashes)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote for JSON string literal
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate a JSON document as bytes, representing the Record schema with controlled variations
    to maximize divergence among Gson, Moshi, kotlinx.serialization, and Jackson Kotlin module.
    """

    # To control recursion depth for "child" field (one level normally)
    # We'll allow child to be null or a nested record with no further child (depth=1)
    # This avoids deep recursion and large documents.

    # Strategy for "id": integer or null or missing or null-as-value (to test null for non-nullable)
    # id is non-nullable integer, Gson accepts missing or null as 0, others reject missing or null
    id_field_behavior = draw(st.sampled_from([
        'valid',        # present with integer
        'missing',      # missing field
        'null',         # present with null
        'wrong_type',   # present with wrong type (e.g. string)
    ]))

    if id_field_behavior == 'valid':
        id_value = draw(st.integers(min_value=0, max_value=2**31-1))
        id_json = f'"id":{id_value}'
    elif id_field_behavior == 'missing':
        id_json = None
    elif id_field_behavior == 'null':
        id_json = '"id":null'
    else:  # wrong_type
        # Use a string that looks like a number but is string type
        id_json = f'"id":{json_string_literal(str(draw(st.integers(0, 1000))))}'

    # Strategy for "amount": string, non-nullable
    # Gson and Moshi accept numbers for string fields (convert to string), kotlinx rejects wrong type,
    # Jackson accepts convertible types for strings.
    amount_field_behavior = draw(st.sampled_from([
        'valid_string',
        'number_instead_of_string',
        'null',
        'missing',
        'wrong_type_nonconvertible',  # e.g. boolean
    ]))
    if amount_field_behavior == 'valid_string':
        amount_str = draw(st.text(min_size=1, max_size=10))
        amount_json = f'"amount":{json_string_literal(amount_str)}'
    elif amount_field_behavior == 'number_instead_of_string':
        amount_num = draw(st.integers(min_value=0, max_value=10000))
        amount_json = f'"amount":{amount_num}'
    elif amount_field_behavior == 'null':
        amount_json = '"amount":null'
    elif amount_field_behavior == 'missing':
        amount_json = None
    else:
        # boolean for wrong_type_nonconvertible
        amount_json = f'"amount":{str(draw(st.booleans())).lower()}'

    # Strategy for "name": string or null, nullable
    # Gson accepts null, Moshi accepts null, kotlinx accepts null, Jackson accepts null
    # Also test missing (should be rejected by Moshi and kotlinx if non-nullable, but name is nullable)
    # So missing nullable fields accepted by Jackson, rejected by Moshi/kotlinx? Known: Moshi and kotlinx reject missing required fields, name is nullable so it is optional? 
    # From problem: all six fields always present in well-formed document, but we test missing for nullable fields to cause divergence.
    name_field_behavior = draw(st.sampled_from([
        'valid_string',
        'null',
        'missing',
        'wrong_type_number',
    ]))
    if name_field_behavior == 'valid_string':
        name_str = draw(st.text(min_size=0, max_size=10))
        name_json = f'"name":{json_string_literal(name_str)}'
    elif name_field_behavior == 'null':
        name_json = '"name":null'
    elif name_field_behavior == 'missing':
        name_json = None
    else:
        # number instead of string
        name_json = f'"name":{draw(st.integers(0, 1000))}'

    # Strategy for "status": enum, non-nullable
    # Gson accepts missing enum (decodes null), unknown enum values decode as null
    # Moshi, kotlinx, Jackson reject missing enum
    # Moshi, kotlinx, Jackson reject unknown enum values or case variants
    # Gson accepts unknown enum values as null
    status_field_behavior = draw(st.sampled_from([
        'valid_enum',
        'missing',
        'null',
        'unknown_enum',
        'case_variant_enum',
        'wrong_type',
    ]))
    if status_field_behavior == 'valid_enum':
        status_json = f'"status":{draw(st.sampled_from(ENUM_VALUES))}'
    elif status_field_behavior == 'missing':
        status_json = None
    elif status_field_behavior == 'null':
        status_json = '"status":null'
    elif status_field_behavior == 'unknown_enum':
        # unknown enum value as string
        status_json = '"status":"pending"'
    elif status_field_behavior == 'case_variant_enum':
        # case variant of a valid enum (e.g. "Active" instead of "active")
        base = draw(st.sampled_from(['active', 'inactive', 'unknown']))
        variant = base.capitalize()
        status_json = f'"status":"{variant}"'
    else:
        # wrong type, e.g. number
        status_json = f'"status":{draw(st.integers(0, 10))}'

    # Strategy for "tags": array of strings, non-nullable
    # Gson accepts null for non-nullable fields (decodes null as null?), Moshi rejects null, kotlinx rejects null, Jackson rejects null
    # Gson accepts missing fields (decodes as null?), Moshi rejects missing, kotlinx rejects missing, Jackson accepts missing nullable only
    tags_field_behavior = draw(st.sampled_from([
        'valid_array',
        'empty_array',
        'null',
        'missing',
        'wrong_type_string',
        'wrong_type_number',
    ]))
    if tags_field_behavior == 'valid_array':
        # array of 1-3 strings
        tags_list = draw(st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=3))
        tags_json = '"tags":[' + ','.join(json_string_literal(t) for t in tags_list) + ']'
    elif tags_field_behavior == 'empty_array':
        tags_json = '"tags":[]'
    elif tags_field_behavior == 'null':
        tags_json = '"tags":null'
    elif tags_field_behavior == 'missing':
        tags_json = None
    elif tags_field_behavior == 'wrong_type_string':
        tags_json = f'"tags":{json_string_literal(draw(st.text(min_size=1, max_size=5)))}'
    else:
        # wrong_type_number
        tags_json = f'"tags":{draw(st.integers(0, 100))}'

    # Strategy for "child": nullable Record or null or missing or null-as-value or wrong type
    # Gson accepts missing or null child, Moshi accepts missing or null child, kotlinx rejects missing child, Jackson accepts missing child but rejects null if non-nullable
    # child is nullable, so null accepted by all except kotlinx rejects missing child
    # We'll generate child with depth=1 (no further child inside)
    child_field_behavior = draw(st.sampled_from([
        'valid_child',
        'null',
        'missing',
        'wrong_type',
    ]))

    def gen_child_record():
        # child record with no further child (child=null)
        # For simplicity, generate a valid child record with all fields valid
        child_id = draw(st.integers(min_value=0, max_value=1000))
        child_amount = draw(st.text(min_size=1, max_size=5))
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=5)))
        child_status = draw(st.sampled_from(ENUM_VALUES))
        child_tags = draw(st.lists(st.text(min_size=1, max_size=5), min_size=0, max_size=2))
        # child.child is null (no recursion)
        parts = [
            f'"id":{child_id}',
            f'"amount":{json_string_literal(child_amount)}',
            f'"name":' + ('null' if child_name is None else json_string_literal(child_name)),
            f'"status":{child_status}',
            '"tags":[' + ','.join(json_string_literal(t) for t in child_tags) + ']',
            '"child":null',
        ]
        return '{' + ','.join(parts) + '}'

    if child_field_behavior == 'valid_child':
        child_json = f'"child":{gen_child_record()}'
    elif child_field_behavior == 'null':
        child_json = '"child":null'
    elif child_field_behavior == 'missing':
        child_json = None
    else:
        # wrong type, e.g. string
        child_json = f'"child":{json_string_literal(draw(st.text(min_size=1, max_size=5)))}'

    # Compose all fields that are not None
    fields = [f for f in [id_json, amount_json, name_json, status_json, tags_json, child_json] if f is not None]

    # Shuffle fields order to avoid bias
    fields = draw(st.permutations(fields))

    json_text = '{' + ','.join(fields) + '}'

    return json_text.encode('utf-8')