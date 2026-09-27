from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and nullability
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # We will sometimes produce invalid enum values or invalid types for one field only,
    # to try to trigger divergence.
    # But mostly produce valid values.

    # Helper to produce a JSON string literal from a Python string (no escapes except \")
    def json_string(s: str) -> str:
        # Escape backslash and double quotes minimally
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # id: integer normally, but sometimes string (invalid)
    def id_strategy():
        # Mostly valid int as string, sometimes invalid string
        return st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            st.text(min_size=1, max_size=5).filter(lambda x: not x.isdigit())
        ).map(lambda s: s)

    # amount: string normally, sometimes number (invalid)
    def amount_strategy():
        # Mostly valid string decimal, sometimes number (invalid)
        valid_amount = st.text(min_size=1, max_size=10).filter(lambda s: all(c in '0123456789.' for c in s) and s.count('.') <= 1)
        invalid_amount = st.floats(allow_nan=False, allow_infinity=False).map(str)
        return st.one_of(valid_amount, invalid_amount)

    # name: string or null normally, sometimes number (invalid)
    def name_strategy():
        valid_name = st.one_of(st.none(), st.text(min_size=0, max_size=10)).map(lambda v: 'null' if v is None else json_string(v))
        invalid_name = st.integers(min_value=0, max_value=100).map(str)
        return st.one_of(valid_name, invalid_name)

    # status: valid enum string or invalid enum string (case variants or unknown)
    def status_strategy():
        valid = st.sampled_from(STATUS_VALUES)
        invalid = st.sampled_from(['"enabled"', '"ACTIVE"', '"unknowns"', '"act ive"', '"inactive "'])
        return st.one_of(valid, invalid)

    # tags: array of strings normally, sometimes array with invalid element types (number or null)
    def tags_strategy():
        valid_tag = st.text(min_size=1, max_size=8).map(json_string)
        valid_tags = st.lists(valid_tag, min_size=0, max_size=5)
        invalid_element = st.one_of(st.integers(min_value=0, max_value=100).map(str), st.just('null'))
        # Mix valid and invalid elements sometimes
        mixed_tags = st.lists(st.one_of(valid_tag, invalid_element), min_size=1, max_size=5)
        return st.one_of(valid_tags, mixed_tags).map(lambda lst: '[' + ','.join(lst) + ']')

    # child: null or nested record (one level only)
    # We produce either null or a nested record with no further child (child=null)
    # Occasionally produce invalid child: empty object or invalid nested fields
    @st.composite
    def child_strategy(draw):
        # Decide if child is null, valid nested record, or invalid nested record
        choice = draw(st.integers(min_value=0, max_value=9))
        if choice == 0:
            # invalid child: empty object
            return '{}'
        elif choice == 1:
            # invalid nested fields: e.g. id as string, or missing fields
            # We'll produce a nested record with one field wrong type
            # id as string (invalid)
            nested_id = draw(st.text(min_size=1, max_size=5).filter(lambda x: not x.isdigit()))
            nested_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c in '0123456789.' for c in s) and s.count('.') <= 1))
            nested_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            nested_status = draw(st.sampled_from(STATUS_VALUES))
            nested_tags = draw(st.lists(st.text(min_size=1, max_size=8).map(json_string), min_size=0, max_size=3))
            # child null (no deeper recursion)
            nested_child = 'null'
            # Compose nested record with id as string (invalid)
            nested = (
                '{'
                f'"id":{json_string(nested_id)},'
                f'"amount":{json_string(nested_amount)},'
                f'"name":{("null" if nested_name is None else json_string(nested_name))},'
                f'"status":{nested_status},'
                f'"tags":[{",".join(nested_tags)}],'
                f'"child":{nested_child}'
                '}'
            )
            return nested
        else:
            # valid nested record with child=null
            nested_id = draw(st.integers(min_value=0, max_value=2**31-1))
            nested_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c in '0123456789.' for c in s) and s.count('.') <= 1))
            nested_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            nested_status = draw(st.sampled_from(STATUS_VALUES))
            nested_tags = draw(st.lists(st.text(min_size=1, max_size=8).map(json_string), min_size=0, max_size=3))
            nested_child = 'null'
            nested = (
                '{'
                f'"id":{nested_id},'
                f'"amount":{json_string(nested_amount)},'
                f'"name":{("null" if nested_name is None else json_string(nested_name))},'
                f'"status":{nested_status},'
                f'"tags":[{",".join(nested_tags)}],'
                f'"child":{nested_child}'
                '}'
            )
            return nested

    # Compose the root record with mostly valid fields, but one or two fields possibly invalid
    # We also sometimes omit a field to test missing field behavior (though not known to cause divergence)
    # But mostly produce all fields present.

    # We produce a dict of fields as strings, then join with commas inside {}

    # Draw fields
    id_val = draw(id_strategy())
    amount_val = draw(amount_strategy())
    name_val = draw(name_strategy())
    status_val = draw(status_strategy())
    tags_val = draw(tags_strategy())
    child_val = draw(child_strategy())

    # Compose JSON object string
    # We always include all six fields (no missing fields), but some fields may be invalid types or values.

    json_obj = (
        '{'
        f'"id":{id_val},'
        f'"amount":{json_string(amount_val) if amount_val.replace(".","",1).isdigit() else amount_val},'
        f'"name":{name_val},'
        f'"status":{status_val},'
        f'"tags":{tags_val},'
        f'"child":{child_val}'
        '}'
    )

    return json_obj.encode('utf-8')