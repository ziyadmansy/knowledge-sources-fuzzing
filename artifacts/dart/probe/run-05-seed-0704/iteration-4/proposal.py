from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for "status" field
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars minimally
        esc = s.replace('\\', '\\\\').replace('"', '\\"')
        # Also escape control chars \b \f \n \r \t for safety
        esc = esc.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return '"' + esc + '"'

    # Helper: produce JSON array of strings
    def json_string_array(arr):
        return '[' + ','.join(json_string(e) for e in arr) + ']'

    # Recursive generator for "child" field, max depth 1 normally, but allow depth=2 for fuzzing
    # We produce a JSON object string or "null"
    def gen_child(depth: int) -> st.SearchStrategy[str]:
        if depth > 2:
            # Beyond depth 2, always null (to avoid infinite recursion)
            return st.just("null")

        # We produce either null or a valid Record object string
        # But to create divergence, sometimes produce a record with one field wrong or missing
        # We do this by generating a dict of fields, then serialize

        # Base valid fields generators for child record
        def gen_record_fields(depth):
            # id: int
            id_val = draw(st.integers(min_value=0, max_value=1000000))
            # amount: string (decimal-ish)
            amount_val = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Nd',))))
            # name: string or null
            name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            # status: one of allowed strings
            status_val = draw(st.sampled_from(STATUS_VALUES))
            # tags: array of strings (0 to 3 elements)
            tags_val = draw(st.lists(st.text(min_size=1, max_size=5), max_size=3))
            # child: recursive call, depth+1
            child_val = draw(gen_child(depth + 1))

            # Compose JSON string for this record
            # Compose fields in fixed order for consistency
            fields = []
            fields.append('"id":' + str(id_val))
            fields.append('"amount":' + json_string(amount_val))
            if name_val is None:
                fields.append('"name":null')
            else:
                fields.append('"name":' + json_string(name_val))
            fields.append('"status":' + json_string(status_val))
            fields.append('"tags":' + json_string_array(tags_val))
            fields.append('"child":' + child_val)
            return '{' + ','.join(fields) + '}'

        # To create divergence, we sometimes produce a record with one field slightly off:
        # - id as string (should be int)
        # - amount as int (should be string)
        # - name as int (should be string or null)
        # - status as invalid string (not in allowed)
        # - tags as array with one non-string element
        # - child as empty object (invalid)
        # - child as missing (not allowed, but let's try)
        # - child as null (valid)
        # - extra unknown field (allowed)
        # - nested child with one level deeper invalid child (should be rejected)
        # But only one such deviation per record to maximize divergence chances.

        # Strategy to pick one deviation or none
        deviation = draw(st.one_of(
            st.just(None),  # no deviation, valid record
            st.just("id_string"),
            st.just("amount_int"),
            st.just("name_int"),
            st.just("status_invalid"),
            st.just("tags_bad_elem"),
            st.just("child_empty_obj"),
            st.just("child_missing"),
            st.just("extra_field"),
            st.just("child_invalid_nested"),
        ))

        # Generate base valid fields for reuse
        id_val = draw(st.integers(min_value=0, max_value=1000000))
        amount_val = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Nd',))))
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        status_val = draw(st.sampled_from(STATUS_VALUES))
        tags_val = draw(st.lists(st.text(min_size=1, max_size=5), max_size=3))
        child_val = draw(gen_child(depth + 1))

        # Compose fields with deviation applied
        fields = []

        # id field
        if deviation == "id_string":
            fields.append('"id":' + json_string(str(id_val)))  # id as string (should cause rejection)
        else:
            fields.append('"id":' + str(id_val))

        # amount field
        if deviation == "amount_int":
            # amount as int (should cause rejection)
            try:
                amount_int = int(amount_val)
            except Exception:
                amount_int = 0
            fields.append('"amount":' + str(amount_int))
        else:
            fields.append('"amount":' + json_string(amount_val))

        # name field
        if deviation == "name_int":
            fields.append('"name":' + str(id_val))  # int instead of string/null
        elif name_val is None:
            fields.append('"name":null')
        else:
            fields.append('"name":' + json_string(name_val))

        # status field
        if deviation == "status_invalid":
            # invalid status string
            fields.append('"status":' + json_string("invalid_status"))
        else:
            fields.append('"status":' + json_string(status_val))

        # tags field
        if deviation == "tags_bad_elem":
            # tags array with one non-string element (int)
            bad_tags = []
            if len(tags_val) == 0:
                bad_tags = [str(id_val)]
            else:
                bad_tags = tags_val[:-1] + [str(id_val)]
            # Compose JSON array with one int element (no quotes)
            arr_parts = []
            for t in bad_tags[:-1]:
                arr_parts.append(json_string(t))
            arr_parts.append(str(id_val))  # int element without quotes
            fields.append('"tags":[' + ','.join(arr_parts) + ']')
        else:
            fields.append('"tags":' + json_string_array(tags_val))

        # child field
        if deviation == "child_empty_obj":
            fields.append('"child":{}')  # empty object invalid
        elif deviation == "child_missing":
            # omit child field entirely (should cause rejection)
            pass
        elif deviation == "child_invalid_nested":
            # child is valid record but its child field is empty object (invalid)
            # Compose nested child with invalid child field
            nested_id = draw(st.integers(min_value=0, max_value=1000000))
            nested_amount = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Nd',))))
            nested_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            nested_status = draw(st.sampled_from(STATUS_VALUES))
            nested_tags = draw(st.lists(st.text(min_size=1, max_size=5), max_size=3))
            # nested child field is empty object (invalid)
            nested_fields = []
            nested_fields.append('"id":' + str(nested_id))
            nested_fields.append('"amount":' + json_string(nested_amount))
            if nested_name is None:
                nested_fields.append('"name":null')
            else:
                nested_fields.append('"name":' + json_string(nested_name))
            nested_fields.append('"status":' + json_string(nested_status))
            nested_fields.append('"tags":' + json_string_array(nested_tags))
            nested_fields.append('"child":{}')  # invalid nested child
            nested_obj = '{' + ','.join(nested_fields) + '}'
            fields.append('"child":' + nested_obj)
        else:
            # normal child
            fields.append('"child":' + child_val)

        # extra unknown field
        if deviation == "extra_field":
            fields.append('"extra_field":' + json_string("extra_value"))

        # Compose final JSON object string
        obj = '{' + ','.join(fields) + '}'
        return st.just(obj)

    # Generate top-level record string with same deviation logic as child, but no child_invalid_nested at top-level
    # We reuse the same deviation set except exclude "child_invalid_nested" at top-level to avoid double nesting complexity
    deviation_top = draw(st.one_of(
        st.just(None),
        st.just("id_string"),
        st.just("amount_int"),
        st.just("name_int"),
        st.just("status_invalid"),
        st.just("tags_bad_elem"),
        st.just("child_empty_obj"),
        st.just("child_missing"),
        st.just("extra_field"),
    ))

    # Generate base valid fields for top-level
    id_val = draw(st.integers(min_value=0, max_value=1000000))
    amount_val = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Nd',))))
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
    status_val = draw(st.sampled_from(STATUS_VALUES))
    tags_val = draw(st.lists(st.text(min_size=1, max_size=5), max_size=3))
    child_val = draw(gen_child(1))

    fields = []

    # id field
    if deviation_top == "id_string":
        fields.append('"id":' + json_string(str(id_val)))
    else:
        fields.append('"id":' + str(id_val))

    # amount field
    if deviation_top == "amount_int":
        try:
            amount_int = int(amount_val)
        except Exception:
            amount_int = 0
        fields.append('"amount":' + str(amount_int))
    else:
        fields.append('"amount":' + json_string(amount_val))

    # name field
    if deviation_top == "name_int":
        fields.append('"name":' + str(id_val))
    elif name_val is None:
        fields.append('"name":null')
    else:
        fields.append('"name":' + json_string(name_val))

    # status field
    if deviation_top == "status_invalid":
        fields.append('"status":' + json_string("invalid_status"))
    else:
        fields.append('"status":' + json_string(status_val))

    # tags field
    if deviation_top == "tags_bad_elem":
        bad_tags = []
        if len(tags_val) == 0:
            bad_tags = [str(id_val)]
        else:
            bad_tags = tags_val[:-1] + [str(id_val)]
        arr_parts = []
        for t in bad_tags[:-1]:
            arr_parts.append(json_string(t))
        arr_parts.append(str(id_val))
        fields.append('"tags":[' + ','.join(arr_parts) + ']')
    else:
        fields.append('"tags":' + json_string_array(tags_val))

    # child field
    if deviation_top == "child_empty_obj":
        fields.append('"child":{}')
    elif deviation_top == "child_missing":
        # omit child field entirely
        pass
    else:
        fields.append('"child":' + child_val)

    # extra unknown field
    if deviation_top == "extra_field":
        fields.append('"extra_field":' + json_string("extra_value"))

    obj = '{' + ','.join(fields) + '}'

    # Return bytes as required
    return obj.encode("utf-8")