from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for "status" field
    status_values = st.sampled_from(["active", "inactive", "unknown"])

    # "id": integer
    id_strat = st.integers(min_value=0, max_value=1_000_000)

    # "amount": any string (including numeric-looking)
    # Use ascii digits and some punctuation to keep it simple
    amount_strat = st.text(alphabet=st.characters(blacklist_categories=('Cs', 'Cc')), min_size=1, max_size=10)

    # "name": string or null
    name_strat = st.one_of(st.none(), st.text(min_size=0, max_size=20))

    # "tags": array of strings normally, but to provoke divergence:
    # built_value accepts null or object as empty list, others reject.
    # So we produce mostly arrays of strings, but sometimes null or object.
    # Also, arrays must contain only strings.
    # To maximize divergence, we bias towards null or object sometimes.
    tags_array_strat = st.lists(st.text(min_size=1, max_size=10), max_size=5)
    tags_object_strat = st.fixed_dictionaries({"dummy": st.text(min_size=1, max_size=5)})
    tags_strat = st.one_of(
        tags_array_strat,
        st.none(),
        tags_object_strat,
    )

    # "status": must be one of three strings, no null or unknown values allowed
    status_strat = status_values

    # "child": null or a valid record (one level recursion)
    # To avoid infinite recursion, limit depth to 1.
    # We'll define a helper for child record generation.
    # We'll produce either null or a record with all fields present.
    # To provoke divergence, we can sometimes omit "name" (optional).
    # But "child" must be null or valid record, no arrays or empty objects.
    # We'll reuse the top-level record generator but with depth=1 limit.

    # To avoid circular definition, define a helper function inside:
    def record_strat(depth):
        # If depth == 0, child must be null (no further recursion)
        if depth == 0:
            child_strat = st.none()
        else:
            # child can be null or a record with depth-1
            child_strat = st.one_of(st.none(), record_strat(depth - 1))

        # "id"
        id_s = id_strat
        # "amount"
        amount_s = amount_strat
        # "name" optional: either missing or present as null/string
        # To provoke divergence, sometimes omit "name" (all accept missing as null)
        # We'll produce either present or missing, but since all accept missing as null, no divergence here.
        # But to keep JSON valid, we must produce a JSON object string with or without "name".
        # We'll handle "name" presence in the outer function.

        # "status"
        status_s = status_strat

        # "tags"
        # To provoke divergence, sometimes produce null or object, sometimes array
        tags_s = tags_strat

        # Compose fields as strings, carefully inserting commas
        # We'll produce a dict of fields as strings, then join with commas.

        # "name" presence: 50% chance to omit (missing), 50% chance present (null or string)
        name_present = draw(st.booleans())
        if name_present:
            name_val = draw(name_strat)
            if name_val is None:
                name_field = '"name":null'
            else:
                # Escape quotes and backslashes in name_val
                esc_name = name_val.replace('\\', '\\\\').replace('"', '\\"')
                name_field = f'"name":"{esc_name}"'
        else:
            name_field = None  # omit

        # "id"
        id_val = draw(id_s)
        id_field = f'"id":{id_val}'

        # "amount"
        amount_val = draw(amount_s)
        esc_amount = amount_val.replace('\\', '\\\\').replace('"', '\\"')
        amount_field = f'"amount":"{esc_amount}"'

        # "status"
        status_val = draw(status_s)
        status_field = f'"status":"{status_val}"'

        # "tags"
        tags_val = draw(tags_s)
        if tags_val is None:
            tags_field = '"tags":null'
        elif isinstance(tags_val, list):
            # array of strings
            # escape each string
            esc_tags = [t.replace('\\', '\\\\').replace('"', '\\"') for t in tags_val]
            tags_field = '"tags":[' + ",".join(f'"{t}"' for t in esc_tags) + "]"
        else:
            # object with one key "dummy"
            dummy_val = tags_val["dummy"]
            esc_dummy = dummy_val.replace('\\', '\\\\').replace('"', '\\"')
            tags_field = f'"tags":{{"dummy":"{esc_dummy}"}}'

        # "child"
        child_val = draw(child_strat)
        if child_val is None:
            child_field = '"child":null'
        else:
            # child_val is a JSON string representing a record
            # We must produce it as a JSON object string
            child_field = f'"child":{child_val}'

        # Compose fields list
        fields = [id_field, amount_field]
        if name_field is not None:
            fields.append(name_field)
        fields.append(status_field)
        fields.append(tags_field)
        fields.append(child_field)

        # Join fields with commas
        obj_str = "{" + ",".join(fields) + "}"
        return obj_str

    # Draw top-level record string with depth=1 recursion allowed
    json_str = record_strat(depth=1)

    # Return bytes
    return json_str.encode("utf-8")