from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for fixed enums and nullability
    status_values = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
    null_or_string = st.one_of(st.just("null"), st.text(min_size=0).map(lambda s: '"' + s.replace('"', '\\"') + '"'))
    # tags is array of strings (always strings, no nulls)
    tags_array = st.lists(st.text(min_size=0).map(lambda s: '"' + s.replace('"', '\\"') + '"'), max_size=5).map(
        lambda lst: "[" + ",".join(lst) + "]"
    )
    # id is integer, but we will sometimes produce wrong types or boundary values
    # amount is string, but we will sometimes produce wrong types or boundary values

    # To produce subtle divergences, we vary one or two fields per document,
    # mostly keeping the rest valid.

    # Strategy for id field: mostly int, sometimes string or float or null or missing
    id_field = st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),
        st.text(min_size=1).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
        st.floats(allow_nan=False, allow_infinity=False).map(lambda f: repr(f)),
        st.just("null"),
    )

    # Strategy for amount field: mostly string, sometimes number, null, or missing
    amount_field = st.one_of(
        st.text(min_size=0).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
        st.integers().map(str),
        st.floats(allow_nan=False, allow_infinity=False).map(lambda f: repr(f)),
        st.just("null"),
    )

    # Strategy for name field: string or null or number or missing
    name_field = st.one_of(
        null_or_string,
        st.integers().map(str),
        st.just("null"),
    )

    # Strategy for status field: mostly correct enum, sometimes wrong string, number, or null
    status_field = st.one_of(
        status_values,
        st.text(min_size=1).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
        st.integers().map(str),
        st.just("null"),
    )

    # Strategy for tags field: mostly array of strings, sometimes array of numbers, null, or missing
    tags_field = st.one_of(
        tags_array,
        st.lists(st.integers().map(str), max_size=5).map(lambda lst: "[" + ",".join(lst) + "]"),
        st.just("null"),
    )

    # Recursive child field: either null or a nested record (one level max)
    # To avoid infinite recursion, child can only be null or a record with child=null
    # We'll build child record with same strategy but child=null always

    def child_record():
        # child record fields, child always null here
        id_c = st.integers(min_value=0, max_value=2**31-1).map(str)
        amount_c = st.text(min_size=0).map(lambda s: '"' + s.replace('"', '\\"') + '"')
        name_c = null_or_string
        status_c = status_values
        tags_c = tags_array
        child_c = st.just("null")

        return st.tuples(id_c, amount_c, name_c, status_c, tags_c, child_c).map(
            lambda t: (
                '{'
                + '"id":' + t[0] + ','
                + '"amount":' + t[1] + ','
                + '"name":' + t[2] + ','
                + '"status":' + t[3] + ','
                + '"tags":' + t[4] + ','
                + '"child":' + t[5]
                + '}'
            )
        )

    # child field: either null or a nested record
    child_field = st.one_of(
        st.just("null"),
        child_record(),
    )

    # Now build the top-level record with mostly valid fields but one or two fields replaced by "wrong" types
    # We'll pick 0,1 or 2 fields to "corrupt" to increase chance of divergence

    # Fields as a dict of name -> strategy
    fields = {
        "id": id_field,
        "amount": amount_field,
        "name": name_field,
        "status": status_field,
        "tags": tags_field,
        "child": child_field,
    }

    # Draw which fields to corrupt (0 to 2)
    corrupt_count = draw(st.integers(min_value=0, max_value=2))
    corrupt_fields = draw(st.lists(st.sampled_from(list(fields.keys())), min_size=corrupt_count, max_size=corrupt_count, unique=True))

    # For each field, draw value: if corrupt, draw from "corrupt" strategy, else from "valid" strategy
    # We define "valid" strategies for each field:

    valid_fields = {
        "id": st.integers(min_value=0, max_value=2**31-1).map(str),
        "amount": st.text(min_size=0).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
        "name": null_or_string,
        "status": status_values,
        "tags": tags_array,
        "child": child_field,
    }

    # For corrupt fields, pick from the original fields strategy but exclude the valid one
    # We'll do this by filtering out the valid values for id, amount, status, etc.
    # To keep it simple, we just reuse the original fields strategy (which includes invalid types)
    # but for valid fields we pick only valid_fields

    # Draw values for all fields
    field_values = {}
    for fname in fields.keys():
        if fname in corrupt_fields:
            # corrupt: draw from fields[fname] (which includes invalid types)
            val = draw(fields[fname])
            # But avoid accidentally drawing a valid value for corrupt fields by retrying if equal to valid
            # This is a heuristic to increase divergence
            # We do a small retry loop here
            for _ in range(3):
                if val == draw(valid_fields[fname]):
                    val = draw(fields[fname])
                else:
                    break
            field_values[fname] = val
        else:
            # valid
            val = draw(valid_fields[fname])
            field_values[fname] = val

    # Compose JSON object text
    # Fields order fixed for consistency
    json_text = (
        '{'
        + '"id":' + field_values["id"] + ','
        + '"amount":' + field_values["amount"] + ','
        + '"name":' + field_values["name"] + ','
        + '"status":' + field_values["status"] + ','
        + '"tags":' + field_values["tags"] + ','
        + '"child":' + field_values["child"]
        + '}'
    )

    return json_text.encode("utf-8")