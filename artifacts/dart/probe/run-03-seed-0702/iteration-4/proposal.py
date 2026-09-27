from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # We will produce JSON text as bytes, so build strings then encode at the end.

    # Helper: produce a JSON string literal from a Python string (no escapes needed for test)
    def json_str(s: str) -> str:
        # Minimal escaping for quotes and backslashes
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # id: integer (always present)
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    id_json = str(id_val)

    # amount: string (always present)
    # We try to produce mostly normal strings, but sometimes edge cases (empty, numeric-looking)
    amount_val = draw(st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
        st.just("0"),
        st.just("123.45"),
        st.just(""),
    ))
    amount_json = json_str(amount_val)

    # name: string or null (always present)
    # We produce either null or a string (possibly empty)
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
    ))
    name_json = "null" if name_val is None else json_str(name_val)

    # status: enum string (always present)
    # We mostly pick valid enum, but sometimes slightly off case or whitespace to test rejection
    # But since all reject invalid enum, we mostly produce valid ones here.
    # To maximize disagreement, we produce valid or invalid with a small chance.
    status_choice = draw(st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.just('"ACTIVE"'),
        st.just('"enabled"'),
        st.just('" unknown "'),
    ))
    status_json = status_choice

    # tags: array of strings (always present)
    # We produce arrays of strings, sometimes empty, sometimes with empty strings
    # Occasionally inject a null or number to test rejection, but mostly valid.
    tags_len = draw(st.integers(min_value=0, max_value=3))
    tags_elements = []
    for _ in range(tags_len):
        # Mostly strings, sometimes null or number (to test rejection)
        tag_val = draw(st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
            st.just("null"),
            st.just("123"),
        ))
        if tag_val == "null" or tag_val == "123":
            tags_elements.append(tag_val)
        else:
            tags_elements.append(json_str(tag_val))
    tags_json = "[" + ",".join(tags_elements) + "]"

    # child: Record or null (always present)
    # We produce either null or a nested record with one level recursion.
    # The nested record is mostly well-formed, but sometimes with one field off type or missing.
    def gen_child():
        # id
        c_id = draw(st.integers(min_value=0, max_value=2**31-1))
        c_id_json = str(c_id)

        # amount
        c_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
        c_amount_json = json_str(c_amount)

        # name
        c_name = draw(st.one_of(
            st.none(),
            st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
        ))
        c_name_json = "null" if c_name is None else json_str(c_name)

        # status
        c_status = draw(st.sampled_from(STATUS_VALUES))
        c_status_json = c_status

        # tags
        c_tags_len = draw(st.integers(min_value=0, max_value=2))
        c_tags_elements = []
        for _ in range(c_tags_len):
            c_tag = draw(st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
            c_tags_elements.append(json_str(c_tag))
        c_tags_json = "[" + ",".join(c_tags_elements) + "]"

        # child: always null (no deeper recursion)
        c_child_json = "null"

        # Compose child JSON object
        # To maximize disagreement, randomly omit or malform one field in child sometimes
        omit_field = draw(st.booleans())
        malform_field = draw(st.booleans())
        fields = []
        # id field
        if not (omit_field and draw(st.booleans())):
            if malform_field and draw(st.booleans()):
                # malform id as string (should be rejected)
                fields.append(f'"id":{json_str(str(c_id))}')
            else:
                fields.append(f'"id":{c_id_json}')
        # amount field
        if not (omit_field and draw(st.booleans())):
            if malform_field and draw(st.booleans()):
                # malform amount as number (should be rejected)
                try:
                    amt_num = float(c_amount)
                    amt_num_json = str(amt_num)
                except Exception:
                    amt_num_json = "0"
                fields.append(f'"amount":{amt_num_json}')
            else:
                fields.append(f'"amount":{c_amount_json}')
        # name field
        if not (omit_field and draw(st.booleans())):
            if malform_field and draw(st.booleans()):
                # malform name as number (should be rejected)
                fields.append(f'"name":123')
            else:
                fields.append(f'"name":{c_name_json}')
        # status field
        if not (omit_field and draw(st.booleans())):
            if malform_field and draw(st.booleans()):
                # invalid enum value
                fields.append(f'"status":"enabled"')
            else:
                fields.append(f'"status":{c_status_json}')
        # tags field
        if not (omit_field and draw(st.booleans())):
            if malform_field and draw(st.booleans()):
                # tags with invalid element type (number)
                fields.append(f'"tags":[123]')
            else:
                fields.append(f'"tags":{c_tags_json}')
        # child field (always null)
        fields.append(f'"child":{c_child_json}')
        # Shuffle fields order
        from random import shuffle
        shuffle(fields)
        return "{" + ",".join(fields) + "}"

    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json = "null"
    else:
        child_json = gen_child()

    # Compose root JSON object
    # To maximize disagreement, randomly omit or malform one root field sometimes
    omit_root_field = draw(st.booleans())
    malform_root_field = draw(st.booleans())
    root_fields = []

    # id field
    if not (omit_root_field and draw(st.booleans())):
        if malform_root_field and draw(st.booleans()):
            # malform id as string (should be rejected)
            root_fields.append(f'"id":{json_str(str(id_val))}')
        else:
            root_fields.append(f'"id":{id_json}')
    # amount field
    if not (omit_root_field and draw(st.booleans())):
        if malform_root_field and draw(st.booleans()):
            # malform amount as number (should be rejected)
            try:
                amt_num = float(amount_val)
                amt_num_json = str(amt_num)
            except Exception:
                amt_num_json = "0"
            root_fields.append(f'"amount":{amt_num_json}')
        else:
            root_fields.append(f'"amount":{amount_json}')
    # name field
    if not (omit_root_field and draw(st.booleans())):
        if malform_root_field and draw(st.booleans()):
            # malform name as number (should be rejected)
            root_fields.append(f'"name":123')
        else:
            root_fields.append(f'"name":{name_json}')
    # status field
    if not (omit_root_field and draw(st.booleans())):
        root_fields.append(f'"status":{status_json}')
    # tags field
    if not (omit_root_field and draw(st.booleans())):
        root_fields.append(f'"tags":{tags_json}')
    # child field
    root_fields.append(f'"child":{child_json}')

    # Add an extra unknown field sometimes (all accept unknown fields)
    if draw(st.booleans()):
        root_fields.append(f'"extra_field":123')

    # Shuffle root fields order
    from random import shuffle
    shuffle(root_fields)

    json_text = "{" + ",".join(root_fields) + "}"
    return json_text.encode("utf-8")