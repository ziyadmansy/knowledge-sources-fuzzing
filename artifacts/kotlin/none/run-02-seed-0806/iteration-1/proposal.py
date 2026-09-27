from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status
    statuses = ['"active"', '"inactive"', '"unknown"']

    # Helper: produce a JSON string literal from a Python string (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally for JSON string
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        # Also escape control chars minimally (newline, tab)
        s = s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return f'"{s}"'

    # Recursive generator for the "child" field JSON text, bounded depth 1
    def gen_child(depth: int) -> st.SearchStrategy[str]:
        if depth > 1:
            # At max depth, child is null or omitted (we always include child, so null)
            return st.just("null")
        else:
            # Generate a child record JSON text (same schema)
            return gen_record(depth + 1)

    # Generate a JSON array of strings (tags)
    def gen_tags() -> st.SearchStrategy[str]:
        # Tags array length 0 to 3, strings of length 0 to 10
        return st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3).map(
            lambda lst: "[" + ",".join(json_string(s) for s in lst) + "]"
        )

    # Generate the "name" field: either null or string (including empty string)
    def gen_name() -> st.SearchStrategy[str]:
        # We want to vary between null and string, and also try some edge cases:
        # empty string, strings with escapes, unicode, etc.
        # We'll produce the JSON text for the field value only (not the key)
        # Also, to induce divergence, sometimes produce a number or boolean as name (wrong type)
        # but only rarely, to keep "almost well-formed"
        # We'll do this by mixing mostly correct types with a small chance of wrong type.
        base = st.one_of(
            st.just("null"),
            st.text(min_size=0, max_size=10).map(json_string),
        )
        # Add a small chance of wrong type: number or boolean as string
        wrong = st.sampled_from(["123", "true", "false", "0", "-1", "1.5"])
        # 90% base, 10% wrong
        return st.one_of(
            base,
            wrong,
        )

    # Generate the "amount" field: string, but sometimes a number or null (wrong type)
    def gen_amount() -> st.SearchStrategy[str]:
        # Mostly string, sometimes number or null to induce divergence
        base = st.text(min_size=1, max_size=10).map(json_string)
        wrong = st.one_of(
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: format(f, "g")),
            st.just("null"),
            st.just("true"),
            st.just("false"),
        )
        return st.one_of(
            base,
            wrong,
        )

    # Generate the "status" field: mostly valid enum string, sometimes invalid string or wrong type
    def gen_status() -> st.SearchStrategy[str]:
        base = st.sampled_from(statuses)
        # Add invalid enum strings or wrong types (number, null, boolean)
        invalid_enum = st.sampled_from(['"Active"', '"INACTIVE"', '"unk"', '"invalid"', '"null"'])
        wrong_type = st.one_of(
            st.integers(min_value=0, max_value=10).map(str),
            st.just("null"),
            st.just("true"),
            st.just("false"),
        )
        # 80% base, 10% invalid enum, 10% wrong type
        return st.one_of(
            base,
            invalid_enum,
            wrong_type,
        )

    # Generate the "id" field: mostly integer, sometimes string or float or null (wrong type)
    def gen_id() -> st.SearchStrategy[str]:
        base = st.integers(min_value=0, max_value=100000).map(str)
        wrong = st.one_of(
            st.text(min_size=1, max_size=5).map(json_string),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: format(f, "g")),
            st.just("null"),
            st.just("true"),
            st.just("false"),
        )
        return st.one_of(
            base,
            wrong,
        )

    # Generate the entire record JSON text at given depth
    def gen_record(depth: int) -> st.SearchStrategy[str]:
        # Compose fields as JSON key:value pairs (strings)
        # To induce divergence, sometimes omit a field (rarely), or produce wrong type
        # But mostly produce all fields present with mostly correct types, with 1-2 fields off

        # id
        id_field = gen_id().map(lambda v: f'"id":{v}')
        # amount
        amount_field = gen_amount().map(lambda v: f'"amount":{v}')
        # name
        name_field = gen_name().map(lambda v: f'"name":{v}')
        # status
        status_field = gen_status().map(lambda v: f'"status":{v}')
        # tags
        tags_field = gen_tags().map(lambda v: f'"tags":{v}')
        # child
        child_field = gen_child(depth).map(lambda v: f'"child":{v}')

        # Combine all fields into a dict, then join with commas
        # To induce divergence, sometimes shuffle fields order
        # Also, sometimes omit a field (rarely) to test missing fields

        # We will produce a list of (field_name, field_text) pairs
        fields = [
            ("id", id_field),
            ("amount", amount_field),
            ("name", name_field),
            ("status", status_field),
            ("tags", tags_field),
            ("child", child_field),
        ]

        # Draw all fields
        drawn_fields = [draw(f[1]) for f in fields]

        # Occasionally omit one field (except child, which is always present)
        # 10% chance omit one field (except child)
        omit_field = draw(st.booleans())
        if omit_field:
            # Choose one field to omit from first five fields (id, amount, name, status, tags)
            omit_index = draw(st.integers(min_value=0, max_value=4))
            # Remove that field
            drawn_fields.pop(omit_index)
            fields.pop(omit_index)

        # Occasionally shuffle fields order (30% chance)
        shuffle_fields = draw(st.booleans())
        if shuffle_fields:
            combined = list(zip([f[0] for f in fields], drawn_fields))
            draw(st.permutations(combined))  # just to consume draw, but we want to shuffle
            # Actually shuffle deterministically here:
            from random import Random
            rnd = Random(draw(st.integers()))
            rnd.shuffle(combined)
            drawn_fields = [f[1] for f in combined]

        # Join fields with commas
        json_text = "{" + ",".join(drawn_fields) + "}"

        return st.just(json_text)

    # Generate top-level record (depth=0)
    record_json = draw(gen_record(0))

    # Return as bytes (UTF-8)
    return record_json.encode("utf-8")