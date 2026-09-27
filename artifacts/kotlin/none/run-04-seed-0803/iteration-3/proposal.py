from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (escaping minimal chars)
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Helper: produce a JSON array of strings
    def json_array_of_strings(lst):
        return "[" + ",".join(json_string(x) for x in lst) + "]"

    # Recursive generator for the "child" field, bounded depth
    def gen_record(depth: int) -> st.SearchStrategy[str]:
        # Base record fields, mostly valid but with small chance of type or presence variation
        # id: integer or sometimes string (type divergence)
        id_strat = st.one_of(
            st.integers(min_value=0, max_value=10**6).map(str),
            st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()),  # invalid id string
        ).flatmap(lambda s: st.just(s))

        # amount: string normally numeric, but sometimes a number or null (type divergence)
        amount_strat = st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s)),
            st.integers(min_value=0, max_value=10000).map(str),
            st.just("null"),  # literal null string (not JSON null)
            st.just("null"),  # to be replaced by JSON null sometimes below
        )

        # name: string or null or missing (simulate missing by empty string, handled below)
        # We'll produce either a JSON string, the literal null, or omit the field by returning None
        name_strat = st.one_of(
            st.none(),
            st.just("null"),
            st.text(min_size=0, max_size=10).map(json_string),
        )

        # status: one of the three strings, or sometimes a wrong string or number
        status_strat = st.one_of(
            st.sampled_from(statuses).map(json_string),
            st.text(min_size=1, max_size=7).filter(lambda s: s not in statuses).map(json_string),
            st.integers(min_value=0, max_value=10).map(str),
        )

        # tags: array of strings, or sometimes null, or array with non-string elements
        tags_strat = st.one_of(
            st.lists(st.text(min_size=1, max_size=5), min_size=0, max_size=3).map(json_array_of_strings),
            st.just("null"),
            st.just("[1,2,3]"),  # invalid tags array with numbers
            st.just("[]"),
        )

        # child: either null, or a nested record (depth limited), or invalid type (string or number)
        if depth <= 0:
            child_strat = st.one_of(
                st.just("null"),
                st.text(min_size=1, max_size=10).map(json_string),
                st.integers(min_value=0, max_value=10).map(str),
            )
        else:
            child_strat = st.one_of(
                st.just("null"),
                gen_record(depth - 1),
                st.text(min_size=1, max_size=10).map(json_string),
                st.integers(min_value=0, max_value=10).map(str),
            )

        # Compose the record fields, allowing some fields to be missing or malformed
        # We'll produce a dict of field_name -> JSON fragment string or None (to omit)
        # Then serialize manually with commas and braces.

        # Draw all fields
        id_val = draw(id_strat)
        amount_val = draw(amount_strat)
        name_val = draw(name_strat)
        status_val = draw(status_strat)
        tags_val = draw(tags_strat)
        child_val = draw(child_strat)

        # Build field strings, omit name if None
        fields = []

        # id field: always present, but sometimes invalid type (string instead of int)
        # id_val is string representing JSON value (either digits or string literal)
        # We want id field as: "id":<value>
        # id_val is string, but if it looks like a number string, output as number, else as string literal
        try:
            int(id_val)
            id_json = f'"id":{id_val}'
        except Exception:
            # id_val is string literal (not digits), quote it
            id_json = f'"id":{json_string(id_val)}'
        fields.append(id_json)

        # amount field: always present, but sometimes null or string or number
        # amount_val is string representing JSON value or literal "null" string
        # If amount_val == "null", output JSON null, else output as string literal or number
        if amount_val == "null":
            amount_json = '"amount":null'
        else:
            # Check if amount_val is numeric string
            try:
                float(amount_val)
                # output as JSON string (quoted)
                amount_json = f'"amount":{json_string(amount_val)}'
            except Exception:
                # output as string literal
                amount_json = f'"amount":{json_string(amount_val)}'
        fields.append(amount_json)

        # name field: omit if None, else if "null" output JSON null, else string literal
        if name_val is not None:
            if name_val == "null":
                name_json = '"name":null'
            else:
                name_json = f'"name":{name_val}'
            fields.append(name_json)
        # else omit name field

        # status field: always present, can be string literal or number literal
        # status_val is string representing JSON value
        # If status_val is digits only, output as number, else as string literal
        try:
            int(status_val)
            status_json = f'"status":{status_val}'
        except Exception:
            status_json = f'"status":{status_val}'
        fields.append(status_json)

        # tags field: always present, can be array of strings, null, or invalid array
        fields.append(f'"tags":{tags_val}')

        # child field: always present, can be null, nested record, or invalid type
        fields.append(f'"child":{child_val}')

        # Join fields with commas
        json_obj = "{" + ",".join(fields) + "}"

        return json_obj

    # Generate top-level record with depth 1 recursion max
    json_text = draw(gen_record(depth=1))

    # Return as bytes
    return json_text.encode("utf-8")