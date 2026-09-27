from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]
    # To induce divergences, we allow one field to be "off" in a controlled way:
    # - missing required field (except "tags" and "child" which built_value sometimes accepts missing)
    # - null for non-nullable (except built_value accepts null tags)
    # - wrong type for a field
    # - enum with unknown value (all reject, so no divergence)
    # - duplicate keys not tested here (too complex to generate valid JSON with duplicates)
    # We'll produce mostly valid documents with one controlled deviation.

    # Helper to produce a valid "id" field (integer)
    valid_id = st.integers(min_value=0, max_value=2**31-1)

    # Helper to produce a valid "amount" field (string)
    # Use decimal-like strings, but allow empty string to test edge
    valid_amount = st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s))

    # Helper to produce a valid "name" field (string or null)
    valid_name = st.one_of(st.none(), st.text(min_size=0, max_size=20))

    # Helper to produce a valid "status" field (enum string)
    valid_status = st.sampled_from(STATUS_VALUES)

    # Helper to produce a valid "tags" field (array of strings)
    valid_tags = st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5)

    # Forward declaration for recursion
    # We'll limit recursion depth to 1 level of child only (as per spec)
    # So child is either null or a record without child (child=null)
    # To avoid infinite recursion, child record's child is always null.

    # Compose a valid record without child (child=null)
    @st.composite
    def record_no_child(draw):
        id_ = draw(valid_id)
        amount = draw(valid_amount)
        name = draw(valid_name)
        status = draw(valid_status)
        tags = draw(valid_tags)
        # Compose JSON text for this record with child=null
        # Escape strings simply by replacing backslash and double quote
        def esc(s):
            return s.replace("\\", "\\\\").replace('"', '\\"')
        name_json = "null" if name is None else '"' + esc(name) + '"'
        tags_json = "[" + ",".join('"' + esc(t) + '"' for t in tags) + "]"
        json_text = (
            '{'
            f'"id":{id_},'
            f'"amount":"{esc(amount)}",'
            f'"name":{name_json},'
            f'"status":"{status}",'
            f'"tags":{tags_json},'
            f'"child":null'
            '}'
        )
        return json_text

    # Compose a valid record with child (child is record_no_child)
    @st.composite
    def record_with_child(draw):
        id_ = draw(valid_id)
        amount = draw(valid_amount)
        name = draw(valid_name)
        status = draw(valid_status)
        tags = draw(valid_tags)
        child_json = draw(record_no_child())
        def esc(s):
            return s.replace("\\", "\\\\").replace('"', '\\"')
        name_json = "null" if name is None else '"' + esc(name) + '"'
        tags_json = "[" + ",".join('"' + esc(t) + '"' for t in tags) + "]"
        json_text = (
            '{'
            f'"id":{id_},'
            f'"amount":"{esc(amount)}",'
            f'"name":{name_json},'
            f'"status":"{status}",'
            f'"tags":{tags_json},'
            f'"child":{child_json}'
            '}'
        )
        return json_text

    # Compose a valid record, randomly with or without child
    valid_record = st.one_of(record_no_child(), record_with_child())

    # Now introduce controlled deviations to induce divergences:
    # We pick one field to "corrupt" or "omit" or "wrong type" or "null" (where allowed)
    # We do this by building a dict of fields as strings, then join with commas.

    # Fields and their valid generators (as JSON text fragments)
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    # Strategies to produce JSON fragments for each field, valid or with one deviation
    # We will produce a dict of fields as strings, then join with commas.

    # id field: integer, required, non-nullable
    # deviations: missing, null, string, float
    id_field_valid = valid_id.map(lambda v: f'"id":{v}')
    id_field_null = st.just('"id":null')
    id_field_string = st.text(min_size=1, max_size=5).map(lambda s: f'"id":"{esc(s)}"')
    id_field_float = st.floats(allow_nan=False, allow_infinity=False).map(lambda f: f'"id":{f}')
    id_field_missing = st.just(None)

    # amount field: string, required, non-nullable
    # deviations: missing, null, number
    amount_field_valid = valid_amount.map(lambda s: f'"amount":"{esc(s)}"')
    amount_field_null = st.just('"amount":null')
    amount_field_number = st.integers(min_value=0, max_value=1000).map(lambda n: f'"amount":{n}')
    amount_field_missing = st.just(None)

    # name field: string or null, nullable
    # deviations: missing (should reject), number
    name_field_valid = st.one_of(st.none().map(lambda _: '"name":null'),
                                st.text(min_size=0, max_size=20).map(lambda s: f'"name":"{esc(s)}"'))
    name_field_number = st.integers(min_value=0, max_value=1000).map(lambda n: f'"name":{n}')
    name_field_missing = st.just(None)

    # status field: enum string, required, non-nullable
    # deviations: missing, null, unknown enum string, uppercase enum string
    status_field_valid = valid_status.map(lambda s: f'"status":"{s}"')
    status_field_null = st.just('"status":null')
    status_field_unknown = st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES).map(lambda s: f'"status":"{esc(s)}"')
    status_field_uppercase = st.sampled_from([s.upper() for s in STATUS_VALUES]).map(lambda s: f'"status":"{s}"')
    status_field_missing = st.just(None)

    # tags field: array of strings, required non-nullable except built_value accepts null or missing as empty
    # deviations: missing, null, wrong type (string, number)
    tags_field_valid = valid_tags.map(lambda lst: '[' + ','.join(f'"{esc(t)}"' for t in lst) + ']')
    tags_field_valid_json = tags_field_valid.map(lambda arr: f'"tags":{arr}')
    tags_field_null = st.just('"tags":null')
    tags_field_string = st.text(min_size=1, max_size=10).map(lambda s: f'"tags":"{esc(s)}"')
    tags_field_number = st.integers(min_value=0, max_value=1000).map(lambda n: f'"tags":{n}')
    tags_field_missing = st.just(None)

    # child field: record or null, required non-nullable except built_value accepts missing as null
    # deviations: missing, null, wrong type (string, number)
    # For child, we reuse valid_record for valid value
    child_field_valid = valid_record.map(lambda s: f'"child":{s}')
    child_field_null = st.just('"child":null')
    child_field_string = st.text(min_size=1, max_size=10).map(lambda s: f'"child":"{esc(s)}"')
    child_field_number = st.integers(min_value=0, max_value=1000).map(lambda n: f'"child":{n}')
    child_field_missing = st.just(None)

    # Now pick one field to deviate, others valid
    # We pick deviation type randomly from allowed deviations per field

    # Compose a dict of fields, with one deviation
    # We pick which field to deviate
    field_names = ["id", "amount", "name", "status", "tags", "child"]
    deviation_field = draw(st.sampled_from(field_names))

    # For each field, pick valid or deviation fragment
    def field_fragment(field):
        if field == deviation_field:
            # produce deviation fragment for this field
            if field == "id":
                deviation = draw(st.sampled_from([
                    id_field_null,
                    id_field_string,
                    id_field_float,
                    id_field_missing,
                ]))
                return deviation
            elif field == "amount":
                deviation = draw(st.sampled_from([
                    amount_field_null,
                    amount_field_number,
                    amount_field_missing,
                ]))
                return deviation
            elif field == "name":
                deviation = draw(st.sampled_from([
                    name_field_number,
                    name_field_missing,
                ]))
                return deviation
            elif field == "status":
                deviation = draw(st.sampled_from([
                    status_field_null,
                    status_field_unknown,
                    status_field_uppercase,
                    status_field_missing,
                ]))
                return deviation
            elif field == "tags":
                deviation = draw(st.sampled_from([
                    tags_field_null,
                    tags_field_string,
                    tags_field_number,
                    tags_field_missing,
                ]))
                return deviation
            elif field == "child":
                deviation = draw(st.sampled_from([
                    child_field_null,
                    child_field_string,
                    child_field_number,
                    child_field_missing,
                ]))
                return deviation
        else:
            # produce valid fragment for this field
            if field == "id":
                return draw(id_field_valid)
            elif field == "amount":
                return draw(amount_field_valid)
            elif field == "name":
                return draw(name_field_valid)
            elif field == "status":
                return draw(status_field_valid)
            elif field == "tags":
                return draw(tags_field_valid_json)
            elif field == "child":
                return draw(child_field_valid)

    # Build list of fragments, filter out None (missing fields)
    fragments = []
    for f in field_names:
        frag = field_fragment(f)
        if frag is not None:
            fragments.append(frag)

    # Shuffle fragments order to avoid bias on field order
    fragments = draw(st.permutations(fragments))

    # Join fragments with commas
    json_text = "{" + ",".join(fragments) + "}"

    return json_text.encode("utf-8")