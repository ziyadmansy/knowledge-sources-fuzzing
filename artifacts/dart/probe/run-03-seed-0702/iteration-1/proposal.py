from hypothesis import strategies as st

# Helper: JSON string escaping for Hypothesis-generated strings
def json_string(s: str) -> str:
    # Minimal escaping for JSON string: backslash, quote, control chars
    # Hypothesis strings won't have control chars by default, so just escape backslash and quote
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, matching the record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.
    """

    # Enum values for "status"
    valid_statuses = ["active", "inactive", "unknown"]

    # Generate a valid "id" integer as string (to be inserted as number)
    # We will sometimes vary this to a string or float to test type boundaries.
    # But since all reject type mismatches, we mostly keep it int.
    # To maximize subtlety, we generate int but sometimes as stringified int in JSON text.
    # However, the schema requires "id" as integer, so we keep it int.

    # Generate "amount" as string normally, but sometimes inject numeric-looking strings or empty strings
    # to test subtle differences.
    # We do not produce number type for "amount" because all reject that.

    # "name" is nullable string or null.
    # We will sometimes produce null, sometimes string, sometimes empty string.

    # "status" is enum string, always lowercase valid values.
    # We do not produce invalid enums here because all reject them identically.

    # "tags" is array of strings, always strings.
    # We can produce empty arrays or arrays with empty strings or strings with spaces.

    # "child" is either null or a nested record (one level only).
    # We produce null or a nested record with similar constraints.
    # We avoid deeper recursion.

    # To provoke subtle differences, we vary presence/absence of optional fields (like "name" nullable),
    # and vary empty strings vs null, empty arrays vs arrays with empty strings,
    # and numeric strings vs strings with spaces in "amount".

    # We also try to produce duplicate keys in some fields, to confirm last-wins behavior,
    # but since all agree on last-wins, it won't score divergence but is valid.

    # We produce only one or two subtle variations per document.

    # Generate id: integer between 0 and 10000
    id_val = draw(st.integers(min_value=0, max_value=10000))

    # Generate amount: string, sometimes numeric string, sometimes with spaces, sometimes empty
    amount_base = draw(st.one_of(
        st.integers(min_value=0, max_value=100000).map(str),
        st.text(min_size=0, max_size=5).filter(lambda s: all(c not in '"\\' for c in s)),  # no quotes or backslash to avoid escaping complexity
        st.just(""),
    ))

    # Generate name: either null or string (empty or non-empty)
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=10).filter(lambda s: all(c not in '"\\' for c in s)),
    ))

    # Generate status: always valid enum string
    status_val = draw(st.sampled_from(valid_statuses))

    # Generate tags: array of strings, length 0 to 3, strings empty or short
    tags_len = draw(st.integers(min_value=0, max_value=3))
    tags_vals = draw(st.lists(
        st.text(min_size=0, max_size=5).filter(lambda s: all(c not in '"\\' for c in s)),
        min_size=tags_len, max_size=tags_len
    ))

    # Generate child: either null or nested record (one level)
    has_child = draw(st.booleans())
    if has_child:
        # Nested child record fields, similar constraints but no further nesting
        child_id = draw(st.integers(min_value=0, max_value=10000))
        child_amount = draw(st.one_of(
            st.integers(min_value=0, max_value=100000).map(str),
            st.text(min_size=0, max_size=5).filter(lambda s: all(c not in '"\\' for c in s)),
            st.just(""),
        ))
        child_name = draw(st.one_of(
            st.none(),
            st.text(min_size=0, max_size=10).filter(lambda s: all(c not in '"\\' for c in s)),
        ))
        child_status = draw(st.sampled_from(valid_statuses))
        child_tags_len = draw(st.integers(min_value=0, max_value=3))
        child_tags = draw(st.lists(
            st.text(min_size=0, max_size=5).filter(lambda s: all(c not in '"\\' for c in s)),
            min_size=child_tags_len, max_size=child_tags_len
        ))
        child_child = "null"  # no deeper nesting

        # Compose child JSON text
        child_fields = [
            f'"id":{child_id}',
            f'"amount":{json_string(child_amount)}',
            f'"name":{("null" if child_name is None else json_string(child_name))}',
            f'"status":{json_string(child_status)}',
            f'"tags":[{",".join(json_string(t) for t in child_tags)}]',
            f'"child":{child_child}',
        ]
        child_json = "{" + ",".join(child_fields) + "}"
    else:
        child_json = "null"

    # Compose root JSON text
    root_fields = [
        f'"id":{id_val}',
        f'"amount":{json_string(amount_base)}',
        f'"name":{("null" if name_val is None else json_string(name_val))}',
        f'"status":{json_string(status_val)}',
        f'"tags":[{",".join(json_string(t) for t in tags_vals)}]',
        f'"child":{child_json}',
    ]

    # Occasionally add duplicate keys for one field to test last-wins (all agree)
    # We do this rarely to keep documents mostly well-formed with one variation
    add_duplicate = draw(st.booleans())
    if add_duplicate:
        # Pick a field to duplicate: "name" or "amount" or "status"
        dup_field = draw(st.sampled_from(["name", "amount", "status"]))
        # Insert duplicate key with different value before the last occurrence of that field
        # Find index of that field
        idx = next(i for i, f in enumerate(root_fields) if f.startswith(f'"{dup_field}":'))
        # Compose duplicate key with a different value
        if dup_field == "name":
            dup_value = json_string(draw(st.text(min_size=0, max_size=10).filter(lambda s: all(c not in '"\\' for c in s))))
        elif dup_field == "amount":
            dup_value = json_string(draw(st.text(min_size=0, max_size=5).filter(lambda s: all(c not in '"\\' for c in s))))
        else:  # status
            dup_value = json_string(draw(st.sampled_from(valid_statuses)))
        # Insert duplicate key before the original one (so last wins)
        root_fields.insert(idx, f'"{dup_field}":{dup_value}')

    json_text = "{" + ",".join(root_fields) + "}"
    return json_text.encode("utf-8")