from hypothesis import strategies as st

# Constants for enum values and field names
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
FIELD_NAMES = ['"id"', '"amount"', '"name"', '"status"', '"tags"', '"child"']

# Helper to produce a JSON string literal with proper escaping for Hypothesis strings
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote for JSON string literal
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations designed to trigger behavioral divergence among four Dart JSON
    deserializers (manual, json_serializable, freezed, built_value).

    Strategy:
    - Generate a mostly valid record with all required fields present.
    - Introduce at most one or two subtle deviations:
      * null vs missing for nullable/non-nullable fields
      * empty array vs null for "tags"
      * nested child present or null
      * slight type variations on "name" (string or null)
      * enum "status" always valid (to avoid universal rejection)
      * duplicate keys with last occurrence wins (sometimes)
    - Limit recursion depth to 1 for "child".
    """

    # Recursive helper to generate a record JSON string (not bytes yet)
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # Base valid fields:
        # id: integer (non-null)
        # amount: string (non-null)
        # name: string or null (nullable)
        # status: enum string (non-null, one of "active", "inactive", "unknown")
        # tags: array of strings (non-null, but built_value accepts null as empty array)
        # child: record or null (nullable, max depth 1)

        # id: integer >= 0 (to avoid negative edge cases)
        id_val = st.integers(min_value=0, max_value=1000000).map(str)

        # amount: string, non-empty, digits or decimal
        amount_val = st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c == '.' for c in s)).map(json_string_literal)

        # name: string or null
        # To trigger divergence, sometimes null, sometimes string
        name_val = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=20).map(json_string_literal)
        )

        # status: enum string, only valid values (to avoid universal rejection)
        status_val = st.sampled_from(STATUS_VALUES)

        # tags: array of strings, non-null normally, but built_value accepts null as empty array
        # To trigger divergence, sometimes null, sometimes empty array, sometimes array of strings
        tags_array = st.lists(
            st.text(min_size=1, max_size=10).map(json_string_literal),
            min_size=0,
            max_size=5
        ).map(lambda lst: "[" + ",".join(lst) + "]")

        tags_val = st.one_of(
            st.just("null"),  # null tags (built_value accepts, others reject)
            tags_array
        )

        # child: null or nested record (depth limited)
        if depth >= 1:
            # At max depth, child must be null to avoid deep recursion
            child_val = st.just("null")
        else:
            # child is null or nested record (depth+1)
            child_val = st.one_of(
                st.just("null"),
                record_json(depth + 1)
            )

        # Compose fields in a dict, then serialize to JSON object string
        # To trigger divergence, sometimes omit a nullable field (only "name" and "child" are nullable)
        # But all four reject missing "name" (probe 4), so do not omit "name"
        # built_value accepts missing "tags" and "child" (probe 6), so sometimes omit "tags" or "child" to trigger divergence

        # Decide which fields to omit (only "tags" and "child" can be omitted to trigger divergence)
        omit_tags = draw(st.booleans())
        omit_child = draw(st.booleans())

        # To keep divergence focused, do not omit both at once (too malformed)
        if omit_tags and omit_child:
            omit_child = False

        # To trigger duplicate keys divergence, sometimes duplicate one key with different value
        duplicate_key = draw(st.one_of(st.none(), st.sampled_from(FIELD_NAMES)))

        # Draw all field values
        id_str = draw(id_val)
        amount_str = draw(amount_val)
        name_str = draw(name_val)
        status_str = draw(status_val)
        tags_str = None if omit_tags else draw(tags_val)
        child_str = None if omit_child else draw(child_val)

        # Build list of key-value pairs as strings
        kv_pairs = [
            f'"id":{id_str}',
            f'"amount":{amount_str}',
            f'"name":{name_str}',
            f'"status":{status_str}',
        ]
        if tags_str is not None:
            kv_pairs.append(f'"tags":{tags_str}')
        if child_str is not None:
            kv_pairs.append(f'"child":{child_str}')

        # If duplicate key requested, add a duplicate with a different value
        # For "tags" duplicate, use empty array if original was non-null, or vice versa
        # For "child" duplicate, toggle null vs nested record
        # For "name" duplicate, toggle null vs string
        # For "id" duplicate, add +1 to id
        # For "amount" duplicate, add "0" suffix
        # For "status" duplicate, use another valid enum value different from original
        if duplicate_key is not None:
            # Find original value for the duplicate key
            def dup_value(key):
                if key == '"id"':
                    try:
                        val = int(id_str)
                        return str(val + 1)
                    except Exception:
                        return id_str
                elif key == '"amount"':
                    # Append "0" if not already endswith 0
                    if amount_str.endswith('0"'):
                        return amount_str
                    else:
                        # Remove trailing quote, add 0, add quote
                        return amount_str[:-1] + "0\""
                elif key == '"name"':
                    # Toggle null vs string "dup"
                    return '"dup"' if name_str == "null" else "null"
                elif key == '"status"':
                    # Pick a different valid enum value
                    others = [v for v in STATUS_VALUES if v != status_str]
                    return others[0] if others else status_str
                elif key == '"tags"':
                    # Toggle null vs empty array
                    if tags_str == "null":
                        return "[]"
                    else:
                        return "null"
                elif key == '"child"':
                    # Toggle null vs a minimal nested record with fixed values
                    if child_str == "null":
                        # minimal nested record with valid fields, no recursion
                        return '{"id":0,"amount":"0","name":null,"status":"active","tags":[],"child":null}'
                    else:
                        return "null"
                else:
                    return None

            dup_val = dup_value(duplicate_key)
            if dup_val is not None:
                # Append duplicate key at the end (last occurrence wins)
                kv_pairs.append(f'{duplicate_key}:{dup_val}')

        # Shuffle keys to vary order (except duplicates always last)
        # Keep duplicates last to respect "last occurrence wins"
        if duplicate_key is None:
            # Shuffle all keys
            from random import shuffle
            kv_pairs_shuffled = list(kv_pairs)
            shuffle(kv_pairs_shuffled)
        else:
            # All except last duplicate
            base_pairs = kv_pairs[:-1]
            from random import shuffle
            kv_pairs_shuffled = list(base_pairs)
            shuffle(kv_pairs_shuffled)
            kv_pairs_shuffled.append(kv_pairs[-1])

        # Compose JSON object string
        json_obj_str = "{" + ",".join(kv_pairs_shuffled) + "}"

        return json_obj_str

    # Draw top-level record JSON string with depth=0
    json_str = draw(record_json(0))

    # Return bytes
    return json_str.encode("utf-8")