from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Hypothesis string,
    # escaping quotes and backslashes minimally.
    def json_string(s: str) -> str:
        # Escape backslash and quote for JSON string
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Helper: produce JSON text for a record, with bounded recursion depth.
    # We vary one or two fields at a time to induce subtle divergences.
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # Base fields with mostly valid types
        # We will vary one or two fields with "almost valid" or "wrong" types or values.

        # id: mostly integer, but sometimes string or float to cause divergence
        id_strat = st.one_of(
            st.integers(min_value=0, max_value=1000).map(str),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: str(f)),
            st.text(min_size=1, max_size=5).map(json_string),
        )

        # amount: normally string, but sometimes number or null or boolean
        amount_strat = st.one_of(
            st.text(min_size=1, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=1000).map(str),
            st.just("null"),
            st.just("true"),
            st.just("false"),
        )

        # name: string or null or number or boolean or missing (simulate missing by empty string)
        # But missing fields are tricky since we must produce valid JSON with all fields present.
        # So instead, sometimes produce null, sometimes string, sometimes number or boolean.
        name_strat = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=1000).map(str),
            st.just("true"),
            st.just("false"),
        )

        # status: one of the three valid strings, or invalid string, or number
        status_strat = st.one_of(
            st.sampled_from(statuses).map(json_string),
            st.text(min_size=1, max_size=7).filter(lambda s: s not in statuses).map(json_string),
            st.integers(min_value=0, max_value=10).map(str),
        )

        # tags: array of strings normally, but sometimes array of numbers, or null, or empty array
        # We produce JSON array text manually.
        def tags_array():
            # Elements: mostly strings, sometimes numbers or booleans
            elem = st.one_of(
                st.text(min_size=0, max_size=5).map(json_string),
                st.integers(min_value=0, max_value=100).map(str),
                st.just("true"),
                st.just("false"),
            )
            # Length 0 to 3 for small arrays
            return st.lists(elem, min_size=0, max_size=3).map(
                lambda elems: "[" + ",".join(elems) + "]"
            )

        tags_strat = st.one_of(
            tags_array(),
            st.just("null"),
        )

        # child: either null or a nested record (depth limit 1)
        if depth <= 0:
            child_strat = st.just("null")
        else:
            # To keep divergence subtle, child can be null or a valid record with depth-1
            child_strat = st.one_of(
                st.just("null"),
                record_json(depth - 1).map(lambda s: s),
            )

        # Compose fields as JSON key-value pairs
        # We will vary one or two fields per record to induce divergence.
        # To do this, we draw a "variation selector" to pick which fields to vary.

        variation_choices = [
            ("id",),
            ("amount",),
            ("name",),
            ("status",),
            ("tags",),
            ("child",),
            ("id", "amount"),
            ("name", "status"),
            ("tags", "child"),
            ("amount", "name"),
        ]
        vary_fields = draw(st.sampled_from(variation_choices))

        # For each field, if in vary_fields, draw from the "variant" strat,
        # else draw from a "normal" strat (valid values only).

        # Normal strat for each field (valid values only)
        normal_id = st.integers(min_value=0, max_value=1000).map(str)
        normal_amount = st.text(min_size=1, max_size=10).map(json_string)
        normal_name = st.one_of(st.none(), st.text(min_size=0, max_size=10)).map(
            lambda v: "null" if v is None else json_string(v)
        )
        normal_status = st.sampled_from(statuses).map(json_string)
        normal_tags = st.lists(st.text(min_size=0, max_size=5).map(json_string), min_size=0, max_size=3).map(
            lambda elems: "[" + ",".join(elems) + "]"
        )
        normal_child = st.one_of(
            st.just("null"),
            record_json(depth - 1) if depth > 0 else st.just("null"),
        )

        def pick_field(field_name):
            if field_name == "id":
                return id_strat if "id" in vary_fields else normal_id
            elif field_name == "amount":
                return amount_strat if "amount" in vary_fields else normal_amount
            elif field_name == "name":
                return name_strat if "name" in vary_fields else normal_name
            elif field_name == "status":
                return status_strat if "status" in vary_fields else normal_status
            elif field_name == "tags":
                return tags_strat if "tags" in vary_fields else normal_tags
            elif field_name == "child":
                return child_strat if "child" in vary_fields else normal_child
            else:
                raise ValueError("Unknown field " + field_name)

        id_val = draw(pick_field("id"))
        amount_val = draw(pick_field("amount"))
        name_val = draw(pick_field("name"))
        status_val = draw(pick_field("status"))
        tags_val = draw(pick_field("tags"))
        child_val = draw(pick_field("child"))

        # Compose JSON object text
        json_obj = (
            '{'
            + '"id":' + id_val + ','
            + '"amount":' + amount_val + ','
            + '"name":' + name_val + ','
            + '"status":' + status_val + ','
            + '"tags":' + tags_val + ','
            + '"child":' + child_val
            + '}'
        )
        return st.just(json_obj)

    # Generate top-level record with depth=1 recursion allowed
    json_text = draw(record_json(depth=1))
    return json_text.encode("utf-8")