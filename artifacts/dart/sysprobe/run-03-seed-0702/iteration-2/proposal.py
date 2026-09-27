from hypothesis import strategies as st

# Constants for enum values and field names
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
FIELD_NAMES = ['"id"', '"amount"', '"name"', '"status"', '"tags"', '"child"']

# Helper to produce a JSON string literal with proper escaping of " and \ only (minimal)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote only (minimal JSON escaping)
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, matching the record schema,
    with bounded recursion (max depth=1 for "child"), and designed to produce
    behavioral divergence between four Dart JSON deserializers.

    Strategy:
    - Produce a mostly valid record with all required fields present.
    - Vary one or two fields subtly to trigger divergence:
      * "tags": sometimes null (built_value accepts as empty array, others reject)
      * "child": sometimes null, sometimes present with variations
      * "name": string or null (all accept null)
      * "status": always valid enum (to avoid universal rejection)
      * "amount": string, but sometimes empty or unusual strings
      * "id": integer, but sometimes boundary values or zero
    - Occasionally omit "tags" or "child" to test built_value acceptance of missing tags/child.
    - Occasionally insert duplicate keys with different values to test last-wins behavior.
    """

    # Max recursion depth = 1 (child can have no further child)
    def record(depth=0):
        # id: integer (always present, never null)
        # Use boundary values and normal values
        id_val = draw(st.one_of(
            st.integers(min_value=0, max_value=0),  # zero boundary
            st.integers(min_value=1, max_value=1000),
            st.integers(min_value=2**31-10, max_value=2**31-1),  # large int near 32-bit max
        ))
        id_json = f'"id":{id_val}'

        # amount: string (always present, never null)
        # Use normal numeric strings, empty string, or unusual numeric-like strings
        amount_val = draw(st.one_of(
            st.text(min_size=1, max_size=10, alphabet='0123456789.-'),  # numeric-ish strings
            st.just("0"),
            st.just(""),
            st.just("-0"),
            st.just("1.0"),
            st.just("0001"),
        ))
        amount_json = f'"amount":{json_string_literal(amount_val)}'

        # name: string or null (always present)
        name_val = draw(st.one_of(
            st.none(),
            st.text(min_size=0, max_size=20).map(json_string_literal),
        ))
        name_json = f'"name":{("null" if name_val is None else name_val)}'

        # status: enum string, always valid (to avoid universal rejection)
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_json = f'"status":{status_val}'

        # tags: array of strings, or null (built_value accepts null as empty array)
        # Sometimes omit tags (built_value accepts missing tags)
        tags_present = draw(st.booleans())
        if tags_present:
            # tags can be null or array of strings
            tags_null = draw(st.booleans())
            if tags_null:
                tags_json = '"tags":null'
            else:
                # array of strings, possibly empty or with duplicates
                tags_list = draw(st.lists(
                    st.text(min_size=0, max_size=10).map(json_string_literal),
                    min_size=0, max_size=5
                ))
                tags_json = '"tags":[' + ",".join(tags_list) + ']'
        else:
            tags_json = None  # omit tags field

        # child: null or nested record (depth max 1)
        # Sometimes omit child (built_value accepts missing child)
        child_present = draw(st.booleans())
        if child_present:
            child_null = draw(st.booleans())
            if child_null:
                child_json = '"child":null'
            else:
                # nested record, no further child (depth=1)
                # Use a simpler nested record with no recursion
                # id: integer > 0
                child_id = draw(st.integers(min_value=1, max_value=1000))
                child_id_json = f'"id":{child_id}'

                # amount: string numeric
                child_amount = draw(st.text(min_size=1, max_size=10, alphabet='0123456789'))
                child_amount_json = f'"amount":{json_string_literal(child_amount)}'

                # name: string or null
                child_name = draw(st.one_of(
                    st.none(),
                    st.text(min_size=0, max_size=10).map(json_string_literal),
                ))
                child_name_json = f'"name":{("null" if child_name is None else child_name)}'

                # status: valid enum
                child_status = draw(st.sampled_from(STATUS_VALUES))
                child_status_json = f'"status":{child_status}'

                # tags: array of strings or null (built_value accepts null)
                child_tags_null = draw(st.booleans())
                if child_tags_null:
                    child_tags_json = '"tags":null'
                else:
                    child_tags_list = draw(st.lists(
                        st.text(min_size=0, max_size=5).map(json_string_literal),
                        min_size=0, max_size=3
                    ))
                    child_tags_json = '"tags":[' + ",".join(child_tags_list) + ']'

                # child: always null at depth=1 (no further recursion)
                child_child_json = '"child":null'

                # Compose child object fields, possibly with duplicates to trigger last-wins
                child_fields = [
                    child_id_json,
                    child_amount_json,
                    child_name_json,
                    child_status_json,
                    child_tags_json,
                    child_child_json,
                ]

                # Possibly insert a duplicate key for "id" or "tags" in child to test last-wins
                dup_key = draw(st.one_of(st.none(), st.just("id"), st.just("tags")))
                if dup_key == "id":
                    # duplicate id with different value
                    dup_id_val = child_id + 1 if child_id < 2**31-1 else child_id - 1
                    child_fields.append(f'"id":{dup_id_val}')
                elif dup_key == "tags":
                    # duplicate tags with different array or null
                    alt_tags_null = not child_tags_null
                    if alt_tags_null:
                        child_fields.append('"tags":null')
                    else:
                        alt_tags_list = draw(st.lists(
                            st.text(min_size=0, max_size=5).map(json_string_literal),
                            min_size=0, max_size=2
                        ))
                        child_fields.append('"tags":[' + ",".join(alt_tags_list) + ']')

                child_json = '"child":{' + ",".join(child_fields) + '}'
        else:
            child_json = None  # omit child field

        # Compose top-level fields, possibly with duplicates to test last-wins
        fields = [id_json, amount_json, name_json, status_json]

        if tags_json is not None:
            fields.append(tags_json)
        if child_json is not None:
            fields.append(child_json)

        # Possibly omit "tags" or "child" (already done)
        # Possibly insert duplicate keys for "id", "amount", or "status" to test last-wins
        dup_key = draw(st.one_of(st.none(), st.just("id"), st.just("amount"), st.just("status")))
        if dup_key == "id":
            dup_id_val = id_val + 1 if id_val < 2**31-1 else id_val - 1
            fields.append(f'"id":{dup_id_val}')
        elif dup_key == "amount":
            dup_amount_val = "9999"
            fields.append(f'"amount":{json_string_literal(dup_amount_val)}')
        elif dup_key == "status":
            # duplicate status with different valid enum
            alt_status = draw(st.sampled_from([s for s in STATUS_VALUES if s != status_val]))
            fields.append(f'"status":{alt_status}')

        # Shuffle fields to vary order (to avoid fixed order)
        fields = draw(st.permutations(fields))

        json_text = "{" + ",".join(fields) + "}"
        return json_text.encode("utf-8")

    return record(depth=0)