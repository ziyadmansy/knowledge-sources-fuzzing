from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal, possibly null or malformed
    def json_string_or_null():
        # 80% chance string, 20% chance null
        return st.one_of(
            st.just("null"),
            st.text(min_size=0, max_size=20).map(lambda s: '"' + s.replace('"', '\\"') + '"')
        )

    # Helper to produce a JSON string literal, but allow some type errors:
    # sometimes produce a number or boolean or null instead of string
    def json_string_or_other_type():
        # 70% string or null, 30% other types (number, bool)
        return st.one_of(
            json_string_or_null(),
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
        )

    # Helper to produce a JSON array of strings, possibly empty
    def json_array_of_strings():
        # 90% well-formed array of strings, 10% malformed (e.g. array of numbers or mixed)
        good_array = st.lists(st.text(min_size=0, max_size=10).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
                             min_size=0, max_size=5).map(lambda elems: "[" + ",".join(elems) + "]")
        # malformed array: numbers, booleans, nulls mixed in
        bad_array = st.lists(
            st.one_of(
                st.text(min_size=0, max_size=10).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
                st.integers(min_value=-1000, max_value=1000).map(str),
                st.booleans().map(lambda b: "true" if b else "false"),
                st.just("null"),
            ),
            min_size=0, max_size=5
        ).map(lambda elems: "[" + ",".join(elems) + "]")
        return st.one_of(good_array, bad_array)

    # Recursive record generator with bounded depth
    def record(depth):
        # At max depth, child is always null
        if depth <= 0:
            child_strat = st.just("null")
        else:
            # 70% chance child is null, 30% chance child is a record (depth-1)
            child_strat = st.one_of(
                st.just("null"),
                record(depth - 1)
            )

        # id field: mostly integer as string, sometimes as number, sometimes missing or wrong type
        # But since id must be integer, we produce integer as number or string, or sometimes a string that is not a number
        id_value = st.one_of(
            st.integers(min_value=0, max_value=10000).map(str),  # number as string
            st.integers(min_value=0, max_value=10000).map(str),  # number as string again (to keep simple)
            st.integers(min_value=0, max_value=10000).map(str),  # repeated to keep weight
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            st.integers(min_value=0, max_value=10000).map(str),  # repeated
            # Occasionally produce number as number (no quotes)
            st.integers(min_value=0, max_value=10000).map(lambda i: str(i)),
            # Occasionally produce string that is not a number (to cause parse errors)
            st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
        )

        # amount field: string, but sometimes a number or boolean or null
        amount_value = json_string_or_other_type()

        # name field: string or null, sometimes number or boolean to cause divergence
        name_value = json_string_or_other_type()

        # status field: mostly one of the three strings, sometimes null or wrong string or number
        status_value = st.one_of(
            st.sampled_from(STATUS_VALUES),
            st.just("null"),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(lambda s: '"' + s.replace('"', '\\"') + '"'),
            st.integers(min_value=0, max_value=10).map(str),
        )

        # tags field: array of strings, sometimes array of mixed types, sometimes null or string
        tags_value = st.one_of(
            json_array_of_strings(),
            st.just("null"),
            json_string_or_null(),
        )

        # Compose fields with 1 or 2 fields possibly missing or malformed to cause divergence
        # But always include all fields to keep "almost well-formed"
        # We produce a dict of field_name -> JSON text, then join with commas

        fields = {
            "id": draw(id_value),
            "amount": draw(amount_value),
            "name": draw(name_value),
            "status": draw(status_value),
            "tags": draw(tags_value),
            "child": draw(child_strat),
        }

        # Occasionally omit one field to cause divergence (10% chance)
        omit_field = draw(st.one_of(st.none(), st.sampled_from(list(fields.keys()))))
        if omit_field is not None:
            del fields[omit_field]

        # Build JSON object string
        items = []
        for k, v in fields.items():
            items.append('"' + k + '":' + v)
        json_obj = "{" + ",".join(items) + "}"
        return json_obj

    # Draw a record with max depth 1 (one level of recursion)
    json_text = draw(record(depth=1))
    return json_text.encode("utf-8")