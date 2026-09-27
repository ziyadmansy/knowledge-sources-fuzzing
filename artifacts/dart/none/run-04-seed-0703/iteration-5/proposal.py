from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for the enum 'status'
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Escape backslash and double quotes minimally
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control characters minimally (newline, tab)
        s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{s}"'

    # Generate a JSON string literal or null for the "name" field
    name_strategy = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=20).map(json_string),
    )

    # Generate the "status" field as a JSON string literal
    status_strategy = st.sampled_from(statuses).map(json_string)

    # Generate the "amount" field as a JSON string literal
    # To induce divergence, sometimes produce numeric strings, sometimes weird numeric-like strings,
    # sometimes empty string, sometimes strings with spaces or signs.
    amount_strategy = st.one_of(
        # Normal decimal numbers as strings
        st.decimals(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)
        .map(lambda d: json_string(format(d, "f"))),
        # Empty string
        st.just(json_string("")),
        # Numeric-like strings with leading/trailing spaces
        st.text(alphabet=" 0123456789.-+", min_size=1, max_size=10).map(json_string),
        # Strings with letters mixed in (to test parsing robustness)
        st.text(alphabet="0123456789.-+eEabc", min_size=1, max_size=10).map(json_string),
    )

    # Generate the "tags" field as a JSON array of strings
    # To induce divergence, sometimes produce empty array, sometimes array with nulls (invalid),
    # sometimes array with empty strings, sometimes array with strings with special chars.
    tags_strategy = st.lists(
        st.one_of(
            st.text(min_size=0, max_size=10).map(json_string),
            st.just("null"),  # invalid element type (null instead of string)
        ),
        min_size=0,
        max_size=5,
    ).map(lambda elems: "[" + ",".join(elems) + "]")

    # Generate the "id" field as an integer (JSON number)
    # To induce divergence, sometimes produce integer as number, sometimes as string,
    # sometimes produce float (should be rejected), sometimes produce null (should be rejected).
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=1_000_000).map(str),
        st.integers(min_value=0, max_value=1_000_000).map(lambda i: json_string(str(i))),
        st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False).map(lambda f: str(f)),
        st.just("null"),
    )

    # Recursive generation of the "child" field:
    # Either null or a nested record (one level max)
    # To induce divergence, sometimes omit fields in child, sometimes produce wrong types in child fields.
    # But since the schema says all six fields always present in well-formed document,
    # we produce mostly well-formed child or null, but sometimes with one field wrong type.

    # We'll define a helper to generate a record as JSON text (string)
    def record_json(level: int) -> st.SearchStrategy[str]:
        # At level 1 (child), no further recursion
        if level > 1:
            # Only null allowed
            return st.just("null")

        # For child record, we produce mostly well-formed records,
        # but with a small chance to produce one field with wrong type or missing.

        # Strategy to produce one field wrong or missing:
        # We'll pick zero or one field to corrupt.

        # Fields: id, amount, name, status, tags, child

        # Generate all fields normally first:
        id_field = id_strategy
        amount_field = amount_strategy
        name_field = name_strategy
        status_field = status_strategy
        tags_field = tags_strategy
        # child field at level 1 is always null (no further recursion)
        child_field = st.just("null")

        # Compose fields into a dict of field_name -> JSON text
        base_fields = st.tuples(
            id_field,
            amount_field,
            name_field,
            status_field,
            tags_field,
            child_field,
        ).map(
            lambda t: {
                "id": t[0],
                "amount": t[1],
                "name": t[2],
                "status": t[3],
                "tags": t[4],
                "child": t[5],
            }
        )

        # Now define a strategy that corrupts zero or one field:
        def corrupt_fields(fields):
            # Decide whether to corrupt a field or not
            corrupt = draw(st.booleans())
            if not corrupt:
                return fields

            # Pick one field to corrupt
            field_to_corrupt = draw(st.sampled_from(list(fields.keys())))

            # Corruption types:
            # - Replace with null if not null
            # - Replace with wrong type (e.g. number instead of string, string instead of number)
            # - Omit the field (remove it)
            # We'll pick one corruption type randomly

            corruption_type = draw(st.sampled_from(["nullify", "wrong_type", "omit"]))

            corrupted = dict(fields)  # copy

            if corruption_type == "omit":
                # Remove the field
                corrupted.pop(field_to_corrupt)
            elif corruption_type == "nullify":
                # Replace with null (as JSON text)
                corrupted[field_to_corrupt] = "null"
            else:  # wrong_type
                # Replace with a wrong type value depending on field
                if field_to_corrupt == "id":
                    # id normally number or string number, replace with string literal non-numeric
                    corrupted[field_to_corrupt] = json_string("notanumber")
                elif field_to_corrupt == "amount":
                    # amount normally string, replace with number literal
                    corrupted[field_to_corrupt] = "12345"
                elif field_to_corrupt == "name":
                    # name normally string or null, replace with number literal
                    corrupted[field_to_corrupt] = "123"
                elif field_to_corrupt == "status":
                    # status normally one of enum strings, replace with invalid string literal
                    corrupted[field_to_corrupt] = json_string("invalid_status")
                elif field_to_corrupt == "tags":
                    # tags normally array of strings, replace with string literal
                    corrupted[field_to_corrupt] = json_string("notanarray")
                elif field_to_corrupt == "child":
                    # child normally null or record, replace with string literal
                    corrupted[field_to_corrupt] = json_string("notanobject")
                else:
                    # fallback: null
                    corrupted[field_to_corrupt] = "null"

            return corrupted

        # Compose the final record JSON text from fields dict
        def dict_to_json(d):
            # Compose JSON object text from dict d (field_name -> JSON text)
            # Fields order fixed for determinism
            keys = ["id", "amount", "name", "status", "tags", "child"]
            # If a field is missing (omitted), skip it
            parts = []
            for k in keys:
                if k in d:
                    parts.append(json_string(k) + ":" + d[k])
            return "{" + ",".join(parts) + "}"

        # Use a composite strategy to draw corruption inside
        @st.composite
        def corrupted_record(draw_inner):
            base = draw_inner(base_fields)
            corrupted = corrupt_fields(base)
            return dict_to_json(corrupted)

        return corrupted_record()

    # Generate the top-level record similarly, but allow recursion depth 1 for child
    # Compose top-level record JSON text

    # Generate all top-level fields normally first:
    id_field = id_strategy
    amount_field = amount_strategy
    name_field = name_strategy
    status_field = status_strategy
    tags_field = tags_strategy
    child_field = record_json(level=1)

    base_fields = st.tuples(
        id_field,
        amount_field,
        name_field,
        status_field,
        tags_field,
        child_field,
    ).map(
        lambda t: {
            "id": t[0],
            "amount": t[1],
            "name": t[2],
            "status": t[3],
            "tags": t[4],
            "child": t[5],
        }
    )

    # Corrupt zero or one field at top-level similarly to child
    def corrupt_fields_top(fields):
        corrupt = draw(st.booleans())
        if not corrupt:
            return fields

        field_to_corrupt = draw(st.sampled_from(list(fields.keys())))
        corruption_type = draw(st.sampled_from(["nullify", "wrong_type", "omit"]))

        corrupted = dict(fields)

        if corruption_type == "omit":
            corrupted.pop(field_to_corrupt)
        elif corruption_type == "nullify":
            corrupted[field_to_corrupt] = "null"
        else:  # wrong_type
            if field_to_corrupt == "id":
                corrupted[field_to_corrupt] = json_string("notanumber")
            elif field_to_corrupt == "amount":
                corrupted[field_to_corrupt] = "12345"
            elif field_to_corrupt == "name":
                corrupted[field_to_corrupt] = "123"
            elif field_to_corrupt == "status":
                corrupted[field_to_corrupt] = json_string("invalid_status")
            elif field_to_corrupt == "tags":
                corrupted[field_to_corrupt] = json_string("notanarray")
            elif field_to_corrupt == "child":
                corrupted[field_to_corrupt] = json_string("notanobject")
            else:
                corrupted[field_to_corrupt] = "null"

        return corrupted

    # Compose JSON object text from dict d (field_name -> JSON text)
    def dict_to_json(d):
        keys = ["id", "amount", "name", "status", "tags", "child"]
        parts = []
        for k in keys:
            if k in d:
                parts.append(json_string(k) + ":" + d[k])
        return "{" + ",".join(parts) + "}"

    @st.composite
    def top_record(draw_top):
        base = draw_top(base_fields)
        corrupted = corrupt_fields_top(base)
        return dict_to_json(corrupted)

    # Draw the final JSON text string
    json_text = draw(top_record())

    # Return as bytes (UTF-8)
    return json_text.encode("utf-8")