from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    statuses = ["active", "inactive", "unknown"]

    # Base primitives
    id_strat = st.integers(min_value=-(2**31), max_value=2**31-1).map(str)
    # amount is string, but try to produce numeric strings and some edge cases
    amount_strat = st.one_of(
        st.decimals(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False).map(lambda d: format(d, 'f')),
        st.just("0"),
        st.just("0.0"),
        st.just("-0"),
        st.just("1e10"),
        st.just(""),
        st.just(" 123 "),  # spaces inside string
    )
    # name: string or null, but also try empty string and whitespace string
    name_strat = st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20),
        st.just(""),
        st.just(" "),
        st.just("\n"),
    )
    # status: one of enum strings, but also try wrong casing or whitespace variants
    status_strat = st.one_of(
        st.sampled_from(statuses),
        st.sampled_from([s.upper() for s in statuses]),
        st.sampled_from([s.capitalize() for s in statuses]),
        st.sampled_from([s + " " for s in statuses]),
        st.sampled_from(["active", "inactive", "unknown", "activee", "inactiv", "unknwn"]),
    )
    # tags: array of strings, but also try empty array, array with null, array with empty string
    tags_strat = st.lists(
        st.one_of(
            st.text(min_size=0, max_size=10),
            st.just(""),
            st.none(),
        ),
        min_size=0,
        max_size=5,
    )

    # Recursive child record, bounded depth 1 (child can be null or a record with child=null)
    # To induce divergence, child can be null or a record with one field off type or missing
    # We produce a record with one field possibly wrong type or missing, or correct

    # Helper to produce a record as dict of strings (JSON text pieces)
    def record_strat(depth=0):
        # At depth 1, child must be null (no deeper recursion)
        if depth >= 1:
            child_val = st.just("null")
        else:
            # child can be null or a record with one field off or missing
            # We produce either:
            # - a fully valid record (all fields correct)
            # - a record with one field missing
            # - a record with one field wrong type (e.g. id as string, amount as number, status as number, tags as string, child as string)
            # - a record with one field null where not allowed (e.g. id null)
            # This will maximize divergence chances.

            # Fully valid record
            valid_rec = st.deferred(lambda: record_strat(depth=depth+1))

            # For one field off, pick one field to alter
            def one_field_off():
                # pick field to alter
                field = draw(st.sampled_from(["id", "amount", "name", "status", "tags", "child"]))
                # produce a valid record dict first
                base = draw(record_dict_strat(depth=depth+1, allow_missing=False, allow_wrong_type=False))
                # alter one field
                if field == "id":
                    # id as string instead of int (wrong type)
                    base["id"] = '"' + draw(st.text(min_size=1, max_size=5)) + '"'
                elif field == "amount":
                    # amount as number (no quotes)
                    base["amount"] = draw(st.integers(min_value=-1000, max_value=1000)).__str__()
                elif field == "name":
                    # name as number or missing
                    if draw(st.booleans()):
                        base["name"] = draw(st.integers(min_value=0, max_value=100)).__str__()
                    else:
                        base.pop("name")
                elif field == "status":
                    # status as number or missing
                    if draw(st.booleans()):
                        base["status"] = draw(st.integers(min_value=0, max_value=10)).__str__()
                    else:
                        base.pop("status")
                elif field == "tags":
                    # tags as string or missing
                    if draw(st.booleans()):
                        base["tags"] = '"' + draw(st.text(min_size=1, max_size=5)) + '"'
                    else:
                        base.pop("tags")
                elif field == "child":
                    # child as string or missing
                    if draw(st.booleans()):
                        base["child"] = '"' + draw(st.text(min_size=1, max_size=5)) + '"'
                    else:
                        base.pop("child")
                # convert dict to JSON text object string
                items = []
                for k, v in base.items():
                    items.append(f'"{k}":{v}')
                return "{" + ",".join(items) + "}"

            # For one field missing, pick one field to remove from valid record
            def one_field_missing():
                base = draw(record_dict_strat(depth=depth+1, allow_missing=False, allow_wrong_type=False))
                field = draw(st.sampled_from(["id", "amount", "name", "status", "tags", "child"]))
                base.pop(field)
                items = []
                for k, v in base.items():
                    items.append(f'"{k}":{v}')
                return "{" + ",".join(items) + "}"

            # Compose choices
            return draw(
                st.one_of(
                    record_dict_strat(depth=depth, allow_missing=False, allow_wrong_type=False).map(
                        lambda d: "{" + ",".join(f'"{k}":{v}' for k, v in d.items()) + "}"
                    ),
                    st.deferred(lambda: one_field_off()),
                    st.deferred(lambda: one_field_missing()),
                    st.just("null"),
                )
            )

    # Helper to produce dict of JSON text pieces for fields, with options to allow missing or wrong type
    def record_dict_strat(depth=0, allow_missing=True, allow_wrong_type=True):
        # id: integer as string (JSON number)
        id_val = id_strat.map(lambda s: s)
        # amount: string with quotes
        amount_val = amount_strat.map(lambda s: '"' + s + '"')
        # name: string or null with quotes or null literal
        def name_val():
            return st.one_of(
                name_strat.map(lambda s: "null" if s is None else '"' + s.replace('"', '\\"') + '"'),
                st.just("null"),
            )
        # status: string with quotes
        def status_val():
            return status_strat.map(lambda s: '"' + s + '"')

        # tags: array of strings or null
        def tags_val():
            # produce JSON array text
            def tags_array():
                return tags_strat.map(
                    lambda arr: "[" + ",".join(
                        "null" if x is None else '"' + x.replace('"', '\\"') + '"' for x in arr
                    ) + "]"
                )
            return tags_array()

        # child: null or record string
        def child_val():
            if depth >= 1:
                return st.just("null")
            else:
                # child can be null or a record with one field off or missing
                # To avoid infinite recursion, limit depth
                return st.one_of(
                    st.just("null"),
                    record_strat(depth=depth+1),
                )

        fields = {}

        # For each field, decide if missing or present
        def field_or_missing(name, strat):
            if allow_missing:
                return st.one_of(st.just(None), strat)
            else:
                return strat

        fields["id"] = field_or_missing("id", id_val)
        fields["amount"] = field_or_missing("amount", amount_val)
        fields["name"] = field_or_missing("name", name_val())
        fields["status"] = field_or_missing("status", status_val())
        fields["tags"] = field_or_missing("tags", tags_val())
        fields["child"] = field_or_missing("child", child_val())

        # Compose dict of present fields only
        def build(d):
            return {k: v for k, v in d.items() if v is not None}

        return st.fixed_dictionaries(fields).map(build)

    # Compose top-level record JSON text string
    rec_dict = draw(record_dict_strat(depth=0, allow_missing=True, allow_wrong_type=True))
    # Compose JSON object string
    items = []
    for k, v in rec_dict.items():
        items.append(f'"{k}":{v}')
    json_text = "{" + ",".join(items) + "}"
    return json_text.encode("utf-8")