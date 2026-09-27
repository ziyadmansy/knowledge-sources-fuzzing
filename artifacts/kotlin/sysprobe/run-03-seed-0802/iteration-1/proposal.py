from hypothesis import strategies as st

# Constants for enum values and JSON literals
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
NULL = "null"

# Helper to produce JSON string literals with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # Minimal escaping for quotes and backslash
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text for the described record schema, aiming to produce
    behavioral divergence between Gson, Moshi, kotlinx.serialization, and Jackson.

    Strategy:
    - Start from a mostly valid record.
    - Introduce at most one or two subtle divergences:
      * Missing required fields (id, amount, status, tags)
      * Null in non-nullable fields (id, amount, status, tags)
      * Wrong type for fields (e.g. number instead of string, string instead of number)
      * Enum variants (unknown, case variants)
      * Null arrays or null nested objects
      * Extra unknown keys (rarely, since it causes rejection by kotlinx and Jackson)
      * Nested object fields with null/missing
      * Null arrays for "tags"
    - Limit recursion depth to 1 for "child".
    - Use last-key-wins for duplicate keys by repeating a key with different values.
    """

    # Recursion depth control
    max_depth = 1
    def record(depth: int) -> st.SearchStrategy[str]:
        # Base fields with mostly valid values
        # id: integer (required)
        # amount: string (required)
        # name: string or null (nullable)
        # status: enum string (required)
        # tags: array of strings (required)
        # child: record or null (nullable, one level recursion)

        # Decide on subtle divergence for this record:
        # We'll pick one or two fields to "mutate" to cause divergence.

        # Field presence control: sometimes omit required fields (id, amount, status, tags)
        # But only one field missing at a time to maximize divergence chances.
        # Also try null in non-nullable fields.
        # Also try wrong types.

        # Choose which field(s) to mutate
        mutate_field = draw(st.sampled_from([
            None,
            "missing_id",
            "missing_amount",
            "missing_status",
            "missing_tags",
            "null_id",
            "null_amount",
            "null_status",
            "null_tags",
            "wrong_type_id",
            "wrong_type_amount",
            "wrong_type_status",
            "wrong_type_tags",
            "enum_unknown_status",
            "enum_case_variant_status",
            "null_name",
            "wrong_type_name",
            "null_child",
            "missing_child",
            "wrong_type_child",
            "extra_unknown_key",
            "duplicate_key_id",
            "duplicate_key_amount",
            "duplicate_key_status",
            "duplicate_key_tags",
            "duplicate_key_name",
            "duplicate_key_child",
            None  # no mutation, fully valid
        ]))

        # id field
        def gen_id():
            if mutate_field == "missing_id":
                return None
            if mutate_field == "null_id":
                return NULL
            if mutate_field == "wrong_type_id":
                # id is integer, give string or array
                return draw(st.sampled_from([
                    json_string_literal("123"),
                    "[]",
                    "{}",
                    "true",
                    "false"
                ]))
            # normal id integer
            return str(draw(st.integers(min_value=0, max_value=10000)))

        # amount field (string)
        def gen_amount():
            if mutate_field == "missing_amount":
                return None
            if mutate_field == "null_amount":
                return NULL
            if mutate_field == "wrong_type_amount":
                # amount is string, give number or array
                return draw(st.sampled_from([
                    str(draw(st.integers(min_value=0, max_value=10000))),
                    "[]",
                    "{}",
                    "true",
                    "false"
                ]))
            # normal string
            return json_string_literal(draw(st.text(min_size=1, max_size=10)))

        # name field (string or null)
        def gen_name():
            if mutate_field == "null_name":
                return NULL
            if mutate_field == "wrong_type_name":
                # name is string or null, give number or array
                return draw(st.sampled_from([
                    str(draw(st.integers(min_value=0, max_value=10000))),
                    "[]",
                    "{}",
                    "true",
                    "false"
                ]))
            # normal string or null
            return draw(st.one_of(
                st.just(NULL),
                st.text(min_size=1, max_size=10).map(json_string_literal)
            ))

        # status field (enum string)
        def gen_status():
            if mutate_field == "missing_status":
                return None
            if mutate_field == "null_status":
                return NULL
            if mutate_field == "wrong_type_status":
                # status is enum string, give number or array
                return draw(st.sampled_from([
                    str(draw(st.integers(min_value=0, max_value=10))),
                    "[]",
                    "{}",
                    "true",
                    "false"
                ]))
            if mutate_field == "enum_unknown_status":
                # unknown enum string not in allowed set
                return json_string_literal("not_a_status")
            if mutate_field == "enum_case_variant_status":
                # case variant of allowed enum (e.g. "Active" instead of "active")
                base = draw(st.sampled_from(["active", "inactive", "unknown"]))
                variant = base.capitalize()
                return json_string_literal(variant)
            # normal enum string
            return draw(st.sampled_from(STATUS_VALUES))

        # tags field (array of strings)
        def gen_tags():
            if mutate_field == "missing_tags":
                return None
            if mutate_field == "null_tags":
                return NULL
            if mutate_field == "wrong_type_tags":
                # tags is array of strings, give string or number or object
                return draw(st.sampled_from([
                    json_string_literal("not_an_array"),
                    str(draw(st.integers(min_value=0, max_value=10))),
                    "{}",
                    "true",
                    "false"
                ]))
            # normal array of strings (0 to 3 elements)
            arr = draw(st.lists(st.text(min_size=1, max_size=10).map(json_string_literal), max_size=3))
            return "[" + ",".join(arr) + "]"

        # child field (record or null)
        def gen_child():
            if mutate_field == "missing_child":
                return None
            if mutate_field == "null_child":
                return NULL
            if mutate_field == "wrong_type_child":
                # child is object or null, give string or number or array
                return draw(st.sampled_from([
                    json_string_literal("not_an_object"),
                    str(draw(st.integers(min_value=0, max_value=10))),
                    "[]",
                    "true",
                    "false"
                ]))
            if depth >= max_depth:
                # no recursion beyond max_depth
                return NULL
            # normal nested record
            return record(depth + 1).example()

        # Compose fields
        fields = []

        # id
        id_val = gen_id()
        if id_val is not None:
            fields.append(f'"id":{id_val}')

        # amount
        amount_val = gen_amount()
        if amount_val is not None:
            fields.append(f'"amount":{amount_val}')

        # name
        name_val = gen_name()
        fields.append(f'"name":{name_val}')

        # status
        status_val = gen_status()
        if status_val is not None:
            fields.append(f'"status":{status_val}')

        # tags
        tags_val = gen_tags()
        if tags_val is not None:
            fields.append(f'"tags":{tags_val}')

        # child
        child_val = gen_child()
        if child_val is not None:
            fields.append(f'"child":{child_val}')

        # Possibly add one extra unknown key to trigger divergence on extra keys
        if mutate_field == "extra_unknown_key":
            # Add an unknown key with a simple value
            fields.append('"unknown_key":123')

        # Possibly add duplicate keys to test last-key-wins
        if mutate_field and mutate_field.startswith("duplicate_key_"):
            key = mutate_field[len("duplicate_key_"):]
            # Add the key twice with different values
            # For simplicity, use fixed values differing from the first occurrence
            # First occurrence is already in fields if present, else add a default
            # We'll add a second occurrence with a different value
            # Remove existing key if present to avoid confusion
            fields = [f for f in fields if not f.startswith(f'"{key}":')]
            # Add first occurrence with a value
            if key == "id":
                fields.append(f'"id":1')
                fields.append(f'"id":2')
            elif key == "amount":
                fields.append(f'"amount":"first"')
                fields.append(f'"amount":"second"')
            elif key == "status":
                fields.append(f'"status":"active"')
                fields.append(f'"status":"inactive"')
            elif key == "tags":
                fields.append(f'"tags":["a"]')
                fields.append(f'"tags":["b"]')
            elif key == "name":
                fields.append(f'"name":"first"')
                fields.append(f'"name":"second"')
            elif key == "child":
                # child is object, two different children
                child1 = record(depth + 1).example()
                child2 = record(depth + 1).example()
                fields.append(f'"child":{child1}')
                fields.append(f'"child":{child2}')

        # Compose JSON object text
        json_text = "{" + ",".join(fields) + "}"

        return json_text

    # Generate top-level record at depth 0
    json_str = draw(record(0))
    return json_str.encode("utf-8")