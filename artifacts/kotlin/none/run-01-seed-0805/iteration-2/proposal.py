from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # We define a bounded recursive strategy for the "child" field.
    # To maximize divergence, we produce mostly well-formed documents,
    # but vary one or two fields with subtle type or value boundary issues.
    # We produce JSON text manually as strings, then encode to bytes.

    # Basic building blocks for JSON text:
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally for JSON string
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    def json_array_of_strings(lst):
        # lst is a list of strings
        return '[' + ','.join(json_string(x) for x in lst) + ']'

    # We define a strategy for the "status" field, which must be one of three strings.
    # To induce divergence, sometimes produce invalid strings or null.
    status_valid = st.sampled_from(["active", "inactive", "unknown"])
    status_invalid = st.one_of(
        st.just('null'),  # string "null" (invalid)
        st.text(min_size=1, max_size=10).filter(lambda x: x not in {"active", "inactive", "unknown"}),
        st.integers(min_value=0, max_value=10).map(str),
    )
    # 80% valid, 20% invalid to keep mostly well-formed
    status_field = st.one_of(
        status_valid.map(lambda s: json_string(s)),
        status_invalid.map(lambda s: json_string(s))
    )

    # "amount" is a string, normally a decimal number string.
    # To induce divergence, sometimes produce a number (no quotes), sometimes null, sometimes empty string.
    amount_valid = st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789.-" for c in s))
    amount_invalid = st.one_of(
        st.integers(min_value=-1000, max_value=1000).map(str),  # unquoted number
        st.just("null"),  # string "null"
        st.just(""),  # empty string
        st.just("true"),  # string "true"
    )
    amount_field = st.one_of(
        amount_valid.map(json_string),
        amount_invalid.map(json_string),
        st.integers(min_value=-1000, max_value=1000).map(str),  # unquoted number (invalid)
        st.just("null"),  # unquoted null (invalid)
    )

    # "name" is string or null.
    # To induce divergence, sometimes produce missing field (omit), sometimes null, sometimes number.
    name_valid = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=20).map(json_string),
    )
    name_invalid = st.one_of(
        st.integers(min_value=-1000, max_value=1000).map(str),
        st.just("true"),
        st.just("false"),
    )
    # 70% valid, 30% invalid
    name_field = st.one_of(name_valid, name_invalid)

    # "tags" is array of strings, can be empty.
    # To induce divergence, sometimes produce array with non-string elements, or null, or missing.
    tags_valid = st.lists(st.text(min_size=0, max_size=10), max_size=5).map(json_array_of_strings)
    tags_invalid = st.one_of(
        st.just("null"),
        st.just("[]"),
        st.lists(st.integers(min_value=0, max_value=10).map(str), max_size=5).map(
            lambda lst: '[' + ','.join(lst) + ']'
        ),
        st.lists(st.one_of(st.text(min_size=1, max_size=5).map(json_string), st.integers(min_value=0, max_value=10).map(str)), max_size=5).map(
            lambda lst: '[' + ','.join(lst) + ']'
        ),
    )
    tags_field = st.one_of(tags_valid, tags_invalid)

    # "id" is integer.
    # To induce divergence, sometimes produce string integer, float, or missing.
    id_valid = st.integers(min_value=0, max_value=10000).map(str)
    id_invalid = st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: not s.isdigit()).map(json_string),
        st.floats(allow_infinity=False, allow_nan=False).map(lambda f: str(f)),
        st.just("null"),
    )
    id_field = st.one_of(id_valid, id_invalid)

    # Recursive "child" field: either null or a nested record.
    # Limit recursion depth to 1.
    # To induce divergence, sometimes produce missing, null, or malformed child.
    # We'll define a helper function to produce child JSON text.

    def record_json(depth):
        # depth 0 means no child recursion
        if depth > 1:
            # produce null child to stop recursion
            child_json = "null"
        else:
            child_json = draw(child_field(depth + 1))

        # Draw fields for this record, but with slight chance of invalidity per field.
        id_val = draw(id_field)
        amount_val = draw(amount_field)
        name_val = draw(name_field)
        status_val = draw(status_field)
        tags_val = draw(tags_field)

        # Compose fields, sometimes omit one field to induce divergence.
        # We'll omit at most one field per record, 10% chance.
        omit_field = draw(st.one_of(st.none(), st.sampled_from(["id", "amount", "name", "status", "tags", "child"])))
        # Compose JSON fields as strings
        fields = []
        if omit_field != "id":
            fields.append('"id":' + id_val)
        if omit_field != "amount":
            fields.append('"amount":' + amount_val)
        if omit_field != "name":
            # name_val can be "null" string or JSON string or number string
            # If name_val == "null" string, output null literal, else output as string or number
            if name_val == "null":
                fields.append('"name":null')
            elif name_val.startswith('"') and name_val.endswith('"'):
                fields.append('"name":' + name_val)
            else:
                # number or boolean string, output as string
                fields.append('"name":' + json_string(name_val))
        if omit_field != "status":
            fields.append('"status":' + status_val)
        if omit_field != "tags":
            fields.append('"tags":' + tags_val)
        if omit_field != "child":
            fields.append('"child":' + child_json)

        return '{' + ','.join(fields) + '}'

    # child_field is a strategy returning JSON text for child record or null or malformed
    def child_field(depth):
        # 70% chance null, 20% chance valid child record, 10% chance malformed child (e.g. string or number)
        return st.one_of(
            st.just("null"),
            st.deferred(lambda: st.just(record_json(depth))),
            st.one_of(
                st.text(min_size=1, max_size=10).map(json_string),
                st.integers(min_value=0, max_value=1000).map(str),
            ),
        )

    # Draw top-level record JSON text
    json_text = record_json(0)

    return json_text.encode("utf-8")