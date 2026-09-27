from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for the schema
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Helper to produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Minimal escaping for quotes and backslashes only, enough for test purposes
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Recursive generator for a Record JSON text (string), with bounded depth
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # At max depth, child must be null
        if depth <= 0:
            # child is null
            child_strat = st.just("null")
        else:
            # child can be null or a nested record (one level recursion normally)
            child_strat = st.one_of(
                st.just("null"),
                record_json(depth - 1)
            )

        # id: integer
        id_strat = st.integers(min_value=-(2**31), max_value=2**31-1).map(str)

        # amount: string (any string)
        # To induce divergences, sometimes produce empty string, sometimes numeric strings, sometimes strings with escapes
        amount_strat = st.text(min_size=0, max_size=10).map(json_string_literal)

        # name: string or null
        # To induce divergences, sometimes null, sometimes string (including empty)
        name_strat = st.one_of(
            st.just("null"),
            st.text(min_size=0, max_size=10).map(json_string_literal)
        )

        # status: one of "active", "inactive", "unknown"
        # To induce divergences, sometimes produce correct strings, sometimes produce wrong types or wrong strings
        # But per hint, vary one or two fields at a time, so mostly correct here
        status_strat = st.sampled_from(STATUS_VALUES)

        # tags: array of strings
        # To induce divergences, sometimes empty array, sometimes array with strings, sometimes array with null or wrong types
        # But mostly well-formed arrays of strings, sometimes empty
        tags_strat = st.lists(
            st.text(min_size=0, max_size=8).map(json_string_literal),
            min_size=0,
            max_size=5
        ).map(lambda lst: "[" + ",".join(lst) + "]")

        # Compose the record JSON string
        def compose_record(id_s, amount_s, name_s, status_s, tags_s, child_s):
            # Compose fields in order with quotes around keys
            # Use minimal spacing to reduce variability
            return (
                '{'
                + '"id":' + id_s + ','
                + '"amount":' + amount_s + ','
                + '"name":' + name_s + ','
                + '"status":' + status_s + ','
                + '"tags":' + tags_s + ','
                + '"child":' + child_s
                + '}'
            )

        return st.tuples(id_strat, amount_strat, name_strat, status_strat, tags_strat, child_strat).map(
            lambda t: compose_record(*t)
        )

    # Generate a base valid record at depth 1 (one level recursion)
    base_record = record_json(depth=1)

    # Now, to induce divergences, we produce variants of the base record with exactly one or two fields slightly off:
    # - missing a field (remove one field)
    # - field with wrong type (e.g. number instead of string, string instead of number, null instead of string, etc)
    # - field with boundary values (empty string, empty array, null where allowed, or null where not allowed)
    # - field with unexpected extra whitespace or escape sequences (some libs may tolerate, others not)
    # We do this by parsing the base record string and then replacing one field's value with a variant.

    # Since we cannot parse JSON here, we build the JSON string manually with a helper that can replace one or two fields.

    # Strategy to pick one or two fields to mutate
    fields = ["id", "amount", "name", "status", "tags", "child"]

    # Mutations per field:
    # id: normally integer string, mutate to string, float string, null, missing
    id_mutations = st.one_of(
        st.integers(min_value=-(2**31), max_value=2**31-1).map(str),  # valid int string
        st.text(min_size=1, max_size=5).map(json_string_literal),    # string instead of int
        st.floats(allow_infinity=False, allow_nan=False).map(lambda f: str(f)),  # float string
        st.just("null"),                                             # null instead of int
    )

    # amount: normally string, mutate to number, null, missing, empty string, badly escaped string
    amount_mutations = st.one_of(
        st.text(min_size=0, max_size=10).map(json_string_literal),   # valid string
        st.integers().map(str),                                      # number instead of string
        st.just("null"),                                             # null instead of string
        st.just('""'),                                               # empty string
        st.just('"bad\\escape"'),                                    # string with escape
    )

    # name: string or null, mutate to number, missing, boolean, empty string
    name_mutations = st.one_of(
        st.just("null"),
        st.text(min_size=0, max_size=10).map(json_string_literal),
        st.integers().map(str),
        st.just("true"),
        st.just('""'),
    )

    # status: one of three strings, mutate to wrong string, number, null, missing
    status_mutations = st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.just('"invalid_status"'),
        st.integers().map(str),
        st.just("null"),
    )

    # tags: array of strings, mutate to array with null, array with numbers, null, string, missing
    tags_mutations = st.one_of(
        st.lists(st.text(min_size=0, max_size=8).map(json_string_literal), min_size=0, max_size=5).map(lambda lst: "[" + ",".join(lst) + "]"),
        st.just("[null]"),
        st.just("[123]"),
        st.just("null"),
        st.text(min_size=0, max_size=10).map(json_string_literal),
    )

    # child: record or null, mutate to null, missing, string, number, malformed record
    # malformed record: missing a field or wrong type in nested record
    def malformed_child():
        # Nested record with one field wrong type or missing
        # Generate a nested record normally, then mutate one field to wrong type or missing
        base = record_json(depth=0)
        # Pick one field to mutate in nested record
        def mutate_nested(rec_str):
            # rec_str is JSON string of nested record, we cannot parse, so build a new nested record with mutation
            # Instead, just produce a malformed nested record string directly here:
            # e.g. missing "id" field or "id" as string instead of int
            # We'll just produce a nested record with id as string (wrong type)
            nested_id = json_string_literal("not_an_int")
            nested_amount = json_string_literal("10.0")
            nested_name = "null"
            nested_status = '"active"'
            nested_tags = "[]"
            nested_child = "null"
            return (
                '{'
                + '"id":' + nested_id + ','
                + '"amount":' + nested_amount + ','
                + '"name":' + nested_name + ','
                + '"status":' + nested_status + ','
                + '"tags":' + nested_tags + ','
                + '"child":' + nested_child
                + '}'
            )
        return st.one_of(
            st.just("null"),
            base,
            st.just(mutate_nested("")),
            st.text(min_size=0, max_size=10).map(json_string_literal),
            st.integers().map(str),
        )

    child_mutations = malformed_child()

    # Map field name to mutation strategy
    field_to_mutation = {
        "id": id_mutations,
        "amount": amount_mutations,
        "name": name_mutations,
        "status": status_mutations,
        "tags": tags_mutations,
        "child": child_mutations,
    }

    # Strategy to pick 0, 1 or 2 fields to mutate (0 means no mutation, just base record)
    mutate_count = st.integers(min_value=0, max_value=2)

    # Compose final JSON string with mutations applied
    def apply_mutations(base_rec_str, mutations):
        # mutations: dict field -> mutated value (string)
        # We rebuild the JSON string with mutated fields replacing base fields
        # Since we cannot parse base_rec_str, we reconstruct from mutations and base values

        # To get base values, parse base_rec_str by generating base record again with record_json(depth=1)
        # But we cannot parse JSON here, so instead, we generate base record fields separately and then override

        # So we do this by generating base record fields separately and then override with mutations

        # This means we must generate base record fields separately here, so we change approach:
        # Instead of generating base record as JSON string, generate base record fields separately here

        # So we refactor: generate base record fields as a tuple, then apply mutations, then compose JSON string

        # This function is only called inside a .flatmap where base record fields are available as tuple

        raise NotImplementedError("apply_mutations should be called inside flatmap with base fields")

    # So we refactor: generate base record fields tuple, then apply mutations

    @st.composite
    def mutated_record(draw):
        # Generate base record fields separately
        id_val = draw(st.integers(min_value=-(2**31), max_value=2**31-1))
        amount_val = draw(st.text(min_size=0, max_size=10))
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
        tags_val = draw(st.lists(st.text(min_size=0, max_size=8), min_size=0, max_size=5))
        # child is either None or nested record with depth=0 (no further recursion)
        # nested record fields:
        nested_id_val = draw(st.integers(min_value=-(2**31), max_value=2**31-1))
        nested_amount_val = draw(st.text(min_size=0, max_size=10))
        nested_name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        nested_status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
        nested_tags_val = draw(st.lists(st.text(min_size=0, max_size=8), min_size=0, max_size=5))
        nested_child_val = None  # no recursion beyond this

        # Compose nested child JSON string
        def json_str(s):
            return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

        def nested_child_json():
            def name_json(n):
                return "null" if n is None else json_str(n)
            tags_json = "[" + ",".join(json_str(t) for t in nested_tags_val) + "]"
            return (
                '{'
                + '"id":' + str(nested_id_val) + ','
                + '"amount":' + json_str(nested_amount_val) + ','
                + '"name":' + name_json(nested_name_val) + ','
                + '"status":' + json_str(nested_status_val) + ','
                + '"tags":' + tags_json + ','
                + '"child":null'
                + '}'
            )

        child_json_val = draw(st.one_of(
            st.just("null"),
            st.just(nested_child_json())
        ))

        # Compose base record fields as strings
        def name_json(n):
            return "null" if n is None else json_str(n)
        tags_json = "[" + ",".join(json_str(t) for t in tags_val) + "]"

        base_fields = {
            "id": str(id_val),
            "amount": json_str(amount_val),
            "name": name_json(name_val),
            "status": json_str(status_val),
            "tags": tags_json,
            "child": child_json_val,
        }

        # Pick how many fields to mutate: 0,1,2
        n_mutate = draw(mutate_count)
        mutate_fields = draw(st.lists(st.sampled_from(fields), min_size=n_mutate, max_size=n_mutate, unique=True))

        # For each mutate field, draw a mutated value from corresponding mutation strategy
        mutated_values = {}
        for f in mutate_fields:
            mutated_values[f] = draw(field_to_mutation[f])

        # Apply mutations to base_fields
        for f, val in mutated_values.items():
            base_fields[f] = val

        # Compose final JSON string from base_fields
        # Compose fields in order
        json_text = (
            '{'
            + '"id":' + base_fields["id"] + ','
            + '"amount":' + base_fields["amount"] + ','
            + '"name":' + base_fields["name"] + ','
            + '"status":' + base_fields["status"] + ','
            + '"tags":' + base_fields["tags"] + ','
            + '"child":' + base_fields["child"]
            + '}'
        )

        return json_text.encode("utf-8")

    return mutated_record()