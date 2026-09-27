from hypothesis import strategies as st

# Constants for fixed enums and limits
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
MAX_RECURSION_DEPTH = 1

# Helper to produce JSON string literals with safe escaping for quotes and backslashes
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote for JSON string literal
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + s + '"'

@st.composite
def generated_json(draw, _depth=0) -> bytes:
    """
    Generate syntactically valid JSON objects matching the record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.

    The record schema:
    {
      "id": <integer or sometimes double to test int64 boundary>,
      "amount": <string>,
      "name": <string or null or missing>,
      "status": <one of "active", "inactive", "unknown" or sometimes invalid string>,
      "tags": <array of strings or missing>,
      "child": <record or null or missing, one level recursion max>
    }

    Variations to provoke divergence:
    - "id" as int or double (including out-of-64-bit-range double)
    - "tags" present or missing (built_value accepts missing, others reject)
    - "name" present as string or null or missing (all accept missing/null)
    - "status" valid or invalid string (all reject invalid)
    - "child" present as null or nested record or missing (all accept missing/null)
    """

    # --- id field ---
    # Generate an integer in 64-bit signed range or a double outside that range
    # to provoke difference between manual/built_value (require int) and others (accept double.toInt())
    # 64-bit signed int range: -2**63 .. 2**63-1
    INT64_MIN = -(2**63)
    INT64_MAX = 2**63 - 1

    # Strategy to produce id as:
    # - int inside 64-bit range (normal case)
    # - double outside 64-bit range (to be decoded as double by jsonDecode, then toInt() saturates)
    id_type = draw(st.sampled_from(['int64', 'double_out_of_range']))

    if id_type == 'int64':
        # int inside 64-bit range
        id_val = draw(st.integers(min_value=INT64_MIN, max_value=INT64_MAX))
        # JSON integer literal (no quotes)
        id_json = str(id_val)
    else:
        # double outside 64-bit range, e.g. 2**63 + fraction or -(2**63) - fraction
        # Use a float literal with decimal point to force JSON number as double
        # Pick sign randomly
        sign = draw(st.sampled_from(['', '-']))
        # Use a large number > 2**63 as base
        base = 2**63
        fraction = draw(st.floats(min_value=0.1, max_value=0.9))
        double_val = base + fraction
        id_json = sign + str(double_val)

    # --- amount field ---
    # Always required string, generate a simple string (non-empty)
    amount_str = draw(st.text(min_size=1, max_size=10))
    amount_json = json_string_literal(amount_str)

    # --- name field ---
    # Nullable string or missing (all accept missing)
    # To provoke divergence, sometimes omit, sometimes null, sometimes string
    name_choice = draw(st.sampled_from(['present_string', 'present_null', 'missing']))
    if name_choice == 'present_string':
        name_val = draw(st.text(min_size=0, max_size=10))
        name_json = json_string_literal(name_val)
        name_field = f'"name":{name_json}'
    elif name_choice == 'present_null':
        name_field = '"name":null'
    else:
        name_field = None  # missing

    # --- status field ---
    # Required enum string: "active", "inactive", "unknown"
    # To provoke divergence, sometimes invalid string (all reject)
    status_choice = draw(st.sampled_from(['valid', 'invalid']))
    if status_choice == 'valid':
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_field = f'"status":{status_val}'
    else:
        # invalid string, e.g. "invalid_status"
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']))
        status_field = f'"status":"{invalid_status}"'

    # --- tags field ---
    # Array of strings or missing
    # built_value accepts missing tags as empty list, others reject missing
    # To provoke divergence, sometimes omit tags, sometimes present empty or non-empty array
    tags_choice = draw(st.sampled_from(['present_empty', 'present_nonempty', 'missing']))
    if tags_choice == 'present_empty':
        tags_field = '"tags":[]'
    elif tags_choice == 'present_nonempty':
        # array of 1 to 3 strings
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=3))
        # JSON array of strings
        tags_json = '[' + ','.join(json_string_literal(t) for t in tags_list) + ']'
        tags_field = f'"tags":{tags_json}'
    else:
        tags_field = None  # missing

    # --- child field ---
    # Nullable record or missing
    # To provoke divergence, sometimes omit, sometimes null, sometimes nested record (one level max)
    child_choice = draw(st.sampled_from(['present_record', 'present_null', 'missing']))
    if _depth < MAX_RECURSION_DEPTH and child_choice == 'present_record':
        # recursively generate nested record with _depth+1
        child_bytes = draw(generated_json(_depth=_depth + 1))
        # child_bytes is bytes, decode to str for embedding
        child_str = child_bytes.decode('utf-8')
        child_field = f'"child":{child_str}'
    elif child_choice == 'present_null':
        child_field = '"child":null'
    else:
        child_field = None  # missing

    # Compose fields, required fields must be present:
    # id, amount, status always present
    # name, tags, child may be missing

    fields = [
        f'"id":{id_json}',
        f'"amount":{amount_json}',
        status_field,
    ]
    if name_field is not None:
        fields.append(name_field)
    if tags_field is not None:
        fields.append(tags_field)
    if child_field is not None:
        fields.append(child_field)

    # Shuffle fields order to avoid positional bias
    # Hypothesis does not have a built-in shuffle for lists, so do a random permutation by sorting with random keys
    # Use draw(st.lists(...)) with unique keys to shuffle
    # But simpler: just keep order fixed (order of keys in JSON objects is not significant)

    json_obj = '{' + ','.join(fields) + '}'

    return json_obj.encode('utf-8')