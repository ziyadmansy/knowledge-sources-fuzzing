from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper: JSON string with proper escaping of " and \
    def json_string():
        # Use ascii chars excluding control chars, quote, backslash
        # Hypothesis text with whitelist chars, then escape " and \
        base = st.text(
            alphabet=st.characters(
                blacklist_characters=['\\', '"', '\b', '\f', '\n', '\r', '\t'],
                min_codepoint=0x20,
                max_codepoint=0x7E,
            ),
            min_size=0,
            max_size=20,
        )
        # Escape " and \ by doubling backslash and prefixing "
        # We'll do manual escaping in map
        def esc(s):
            # Escape backslash first
            s = s.replace('\\', '\\\\')
            s = s.replace('"', '\\"')
            return '"' + s + '"'
        return base.map(esc)

    # JSON null literal
    json_null = st.just("null")

    # JSON boolean literals
    json_true = st.just("true")
    json_false = st.just("false")

    # JSON number as string, representing a JSON number literal
    # We want to produce numbers that test boundaries and type differences:
    # - integers within 64-bit range (int64)
    # - integers outside 64-bit range (to become double in jsonDecode)
    # - floating point numbers (to test toInt() behavior)
    # - zero, negative zero, negative numbers
    # - large exponent numbers
    # We'll produce strings representing these numbers (no quotes)
    json_number_str = st.one_of(
        # Int64 range integers as strings
        st.integers(min_value=-(2**63), max_value=2**63 - 1).map(str),
        # Integers outside int64 range (to become double)
        st.one_of(
            st.integers(min_value=-(2**70), max_value=-(2**63 + 1)),
            st.integers(min_value=2**63, max_value=2**70),
        ).map(str),
        # Floating point numbers as strings
        st.floats(
            allow_infinity=False,
            allow_nan=False,
            width=32,
            min_value=-1e10,
            max_value=1e10,
        ).map(lambda f: format(f, '.10g')),
        # Special zero variants
        st.sampled_from(["0", "-0", "0.0", "-0.0"]),
        # Large exponent floats
        st.sampled_from(["1e10", "-1e10", "1e-10", "-1e-10"]),
    )

    # JSON array of strings (tags)
    # tags must be array of strings (possibly empty)
    # We'll produce arrays of 0 to 3 strings
    json_array_of_strings = st.lists(
        json_string(),
        min_size=0,
        max_size=3,
    ).map(lambda elems: "[" + ",".join(elems) + "]")

    # JSON enum status: one of "active", "inactive", "unknown"
    # We will produce correct values or occasionally an invalid string to test rejection
    # But invalid status is rejected by all four, so no divergence there.
    # So only produce valid status strings.
    json_status = st.sampled_from(['"active"', '"inactive"', '"unknown"'])

    # JSON nullable string: either null or a JSON string
    json_nullable_string = st.one_of(json_null, json_string())

    # JSON nullable child: either null or a nested record (one level recursion)
    # To avoid deep recursion, limit recursion depth to 1
    # We'll define a helper function for record JSON text (without bytes)
    # But since we must produce bytes at the end, we build strings and encode at the end

    # Forward declaration for record JSON string
    # We'll define a helper function that returns a strategy producing JSON text for a record
    def record_json(depth=0):
        # id: int or double (to test divergence)
        # We want to sometimes produce int64-range int, sometimes double (out-of-range int or float)
        # Use json_number_str but restrict to int or float as needed
        # But id must be present and non-null, so always produce a number string (no quotes)
        id_str = json_number_str

        # amount: string (non-null)
        amount_str = json_string()

        # name: nullable string
        name_str = json_nullable_string

        # status: enum string
        status_str = json_status

        # tags: array of strings or missing (to test divergence)
        # Missing tags is accepted only by built_value, rejected by others
        # So we produce either present or missing tags field
        # To maximize divergence, produce tags present most of the time, missing sometimes
        tags_present = draw(st.booleans())
        if tags_present:
            tags_strat = json_array_of_strings
        else:
            tags_strat = st.just(None)  # missing field

        # child: nullable record or missing (missing accepted by all)
        # But missing child is accepted by all, so no divergence there
        # So produce present child field with null or nested record (depth limited)
        if depth >= 1:
            # At max depth, child is null or missing
            child_present = draw(st.booleans())
            if child_present:
                child_strat = json_null
            else:
                child_strat = st.just(None)
        else:
            # depth < 1: child present with null or nested record
            child_present = draw(st.booleans())
            if child_present:
                # nested record
                nested = record_json(depth + 1)
                child_strat = nested
            else:
                child_strat = st.just(None)

        # Compose fields, with tags and child possibly missing
        # We will build a dict of field_name -> JSON text or None (missing)
        # Then serialize to JSON object string

        id_val = draw(id_str)
        amount_val = draw(amount_str)
        name_val = draw(name_str)
        status_val = draw(status_str)
        tags_val = draw(tags_strat)
        child_val = draw(child_strat)

        fields = []
        # id (number, no quotes)
        fields.append('"id":' + id_val)
        # amount (string)
        fields.append('"amount":' + amount_val)
        # name (nullable string)
        fields.append('"name":' + name_val)
        # status (enum string)
        fields.append('"status":' + status_val)
        # tags (array of strings) or missing
        if tags_val is not None:
            fields.append('"tags":' + tags_val)
        # child (nullable record or null) or missing
        if child_val is not None:
            fields.append('"child":' + child_val)

        return "{" + ",".join(fields) + "}"

    # Draw top-level record JSON string
    json_text = record_json(depth=0)

    # Encode to bytes
    return json_text.encode("utf-8")