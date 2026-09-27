from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper: produce a JSON string literal with proper escaping of " and \ only (minimal)
    def json_string(s: str) -> str:
        # minimal escaping for " and \
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id: integer
    id_strat = st.integers(min_value=-(2**31), max_value=2**31-1)

    # amount: string, but try normal numeric strings and some edge cases
    # We include numeric strings, empty string, strings with spaces, and strings with unicode digits
    amount_strat = st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),  # printable ascii
        st.just(""),  # empty string
        st.sampled_from(["0", "-0", "123.45", "1e10", " 42 ", "007", "+3.14", "NaN", "Infinity", "-Infinity"]),
    )

    # name: string or null, include empty string, unicode, and some special chars
    name_strat = st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),  # ascii printable
        st.just(""),  # empty string
        st.just("null"),  # string "null"
        st.just("None"),  # string "None"
    )

    # status: one of "active", "inactive", "unknown"
    # Also try to produce strings close to these but invalid (typos, case variants) to provoke divergence
    status_valid = st.sampled_from(["active", "inactive", "unknown"])
    status_invalid = st.sampled_from([
        "Active", "Inactive", "Unknown",  # case variants
        "activ", "inactiv", "unknwn",  # typos
        "", " ", "null", "none", "ACTIVE"
    ])
    # Mix valid and invalid with bias toward valid (80%)
    status_strat = st.one_of(
        status_valid,
        status_invalid,
    ).filter(lambda s: isinstance(s, str))

    # tags: array of strings
    # Try empty array, array with empty string, array with null (invalid type), array with numbers (invalid)
    # But we must produce valid JSON, so null is valid JSON but invalid type for tags elements
    # We want to provoke divergence by sometimes putting null or numbers in tags
    tag_element = st.one_of(
        st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
        st.just(""),  # empty string
        st.none(),
        st.integers(min_value=-10, max_value=10),
        st.booleans(),
    )
    tags_strat = st.lists(tag_element, min_size=0, max_size=5)

    # child: either null or a nested record (one level only)
    # To avoid infinite recursion, child record is generated with a flag to disallow further child nesting
    # We will define a helper function to generate a record with a parameter to disable child nesting

    def record_strat(allow_child: bool):
        # Compose fields as strings, then join with commas inside {}
        # We build JSON text directly

        # id
        id_val = draw(id_strat)
        id_json = f'"id":{id_val}'

        # amount
        amount_val = draw(amount_strat)
        amount_json = f'"amount":{json_string(amount_val)}'

        # name
        name_val = draw(name_strat)
        if name_val is None:
            name_json = '"name":null'
        else:
            name_json = f'"name":{json_string(name_val)}'

        # status
        status_val = draw(status_strat)
        status_json = f'"status":{json_string(status_val)}'

        # tags
        tags_val = draw(tags_strat)
        # Serialize tags array elements carefully:
        # - strings as JSON strings
        # - null as null
        # - numbers as numbers
        # - booleans as true/false
        def serialize_tag_element(e):
            if e is None:
                return "null"
            elif isinstance(e, bool):
                return "true" if e else "false"
            elif isinstance(e, int):
                return str(e)
            else:
                # string
                return json_string(str(e))
        tags_json = '"tags":[' + ",".join(serialize_tag_element(e) for e in tags_val) + ']'

        # child
        if allow_child:
            # 50% chance null, 50% chance nested record with allow_child=False
            child_is_null = draw(st.booleans())
            if child_is_null:
                child_json = '"child":null'
            else:
                # nested record with no further child nesting
                nested = record_strat(False)
                child_json = f'"child":{nested}'
        else:
            child_json = '"child":null'

        # Join all fields in order
        fields = [id_json, amount_json, name_json, status_json, tags_json, child_json]
        return "{" + ",".join(fields) + "}"

    # Draw top-level record with child allowed
    top_record = record_strat(True)

    # Return as bytes
    return top_record.encode("utf-8")