from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ['active', 'inactive', 'unknown']

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for JSON string: backslash and quote
        esc = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{esc}"'

    # Recursive record generator with bounded depth
    def record(depth: int) -> st.SearchStrategy[str]:
        # id field:
        # Manual requires int exactly (rejects floats like 1.0)
        # json_serializable/freezed accept floats like 1.0 (cast to int)
        # To maximize divergence, sometimes produce int, sometimes float with .0
        id_int = st.integers(min_value=0, max_value=1000)
        id_float = id_int.map(lambda i: float(i) + 0.0)  # e.g. 1.0
        # Also try a float with fractional part to cause manual reject but others reject too
        id_choice = st.one_of(
            id_int.map(str),
            id_float.map(lambda f: f'{f:.1f}'),  # e.g. "1.0"
        )

        # amount field: must be string exactly
        # To cause divergence, sometimes produce string, sometimes number (manual rejects number)
        amount_str = st.text(min_size=1, max_size=10).map(json_string)
        # Also produce a number as string to cause manual reject
        amount_num = st.one_of(
            st.integers(min_value=0, max_value=1000),
            st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)
        ).map(str)
        amount_choice = st.one_of(amount_str, amount_num)

        # name field: string or null
        # Manual and json_serializable/freezed accept null or string
        # built_value accepts missing or null
        # To cause divergence, sometimes omit name (built_value accepts), sometimes null, sometimes string
        # But schema says all six fields always present in well-formed document, so omit only in child maybe
        # Here always present, so produce null or string
        name_val = st.one_of(
            st.none().map(lambda _: 'null'),
            st.text(min_size=0, max_size=10).map(json_string)
        )

        # status field: one of "active", "inactive", "unknown"
        # To cause divergence, sometimes produce invalid enum string
        # Manual throws raw ArgumentError, others throw CheckedFromJsonException or BuiltValueNestedFieldError
        status_val = st.one_of(
            st.sampled_from(STATUS_VALUES).map(json_string),
            # invalid enum string to cause divergence
            st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES).map(json_string)
        )

        # tags field: array of strings
        # Manual rejects non-string tags, json_serializable/freezed cast, built_value expects BuiltList<String>
        # To cause divergence, sometimes produce array with non-string elements (numbers, null)
        # or empty array or array of strings
        tag_string = st.text(min_size=0, max_size=5).map(json_string)
        tag_number = st.integers(min_value=0, max_value=100).map(str)
        tag_null = st.just('null')
        tag_elem = st.one_of(tag_string, tag_number, tag_null)
        tags_arr = st.lists(tag_elem, min_size=0, max_size=5).map(
            lambda elems: '[' + ','.join(elems) + ']'
        )

        # child field: null or nested record (one level recursion max)
        # built_value rejects invalid nested objects, throws BuiltValueNestedFieldError on partial/malformed child
        # To cause divergence, sometimes produce null, sometimes nested record, sometimes malformed child (e.g. missing fields)
        if depth <= 0:
            child_val = st.just('null')
        else:
            # Nested record or null or malformed child (e.g. missing fields)
            # Malformed child: produce object missing some fields or with wrong types
            # To keep JSON valid, produce object with some fields missing or wrong types
            def malformed_child():
                # Missing one field randomly or wrong type for one field
                # Use only one error to keep close to well-formed
                base = draw(record(depth - 1))
                # base is JSON string of a record, parse it manually is impossible here,
                # so instead produce a minimal malformed child string manually:
                # e.g. {"id":1,"amount":"a","name":null,"status":"active","tags":[]}
                # but missing "child" field or "tags" field or with wrong type for "id"
                # We'll produce a child with missing "child" field (omit it)
                # or with "id" as string instead of int
                # or with "tags" as number instead of array
                # We'll produce these manually here:
                malformed_options = [
                    # missing "child"
                    '{"id":1,"amount":"a","name":null,"status":"active","tags":[]}',
                    # id as string
                    '{"id":"notint","amount":"a","name":null,"status":"active","tags":[],"child":null}',
                    # tags as number
                    '{"id":1,"amount":"a","name":null,"status":"active","tags":123,"child":null}',
                ]
                return draw(st.sampled_from(malformed_options))

            child_val = st.one_of(
                st.just('null'),
                record(depth - 1),
                malformed_child()
            )

        # Compose the record JSON string
        # id, amount, name, status, tags, child
        # id and amount are raw JSON values (id_choice and amount_choice produce strings representing JSON values)
        # name_val, status_val, tags_arr, child_val are JSON strings already
        # Compose with keys in fixed order for consistency
        def compose_record(id_s, amount_s, name_s, status_s, tags_s, child_s):
            return (
                '{'
                f'"id":{id_s},'
                f'"amount":{amount_s},'
                f'"name":{name_s},'
                f'"status":{status_s},'
                f'"tags":{tags_s},'
                f'"child":{child_s}'
                '}'
            )

        # Draw all fields
        id_s = draw(id_choice)
        amount_s = draw(amount_choice)
        name_s = draw(name_val)
        status_s = draw(status_val)
        tags_s = draw(tags_arr)
        child_s = draw(child_val)

        return compose_record(id_s, amount_s, name_s, status_s, tags_s, child_s)

    # Generate top-level record with depth=1 (one level recursion)
    json_text = draw(record(1))
    return json_text.encode('utf-8')