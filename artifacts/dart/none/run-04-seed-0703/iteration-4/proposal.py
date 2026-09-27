from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Base primitive strategies for fields
    id_strat = st.integers(min_value=-(2**31), max_value=2**31-1)
    # amount is string, but we will sometimes produce numeric strings, sometimes malformed numeric strings,
    # sometimes empty string, sometimes strings with whitespace or signs
    amount_strat = st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in "+-." for c in s)),
        st.text(min_size=0, max_size=10).filter(lambda s: len(s) > 0 and any(c.isalpha() for c in s)),  # letters in amount
        st.just(""),  # empty string
        st.just(" 123 "),  # spaces around digits
        st.just("+123.45"),
        st.just("-0.99"),
        st.just("0"),
    )
    # name: string or null, but sometimes produce wrong types (number, bool) to cause divergence
    name_strat = st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20),
        st.integers(min_value=-1000, max_value=1000).map(str),  # stringified int (valid)
        st.integers(min_value=-1000, max_value=1000),  # int (invalid type)
        st.booleans(),  # bool (invalid type)
    )
    # status: one of the three strings, but sometimes wrong strings or null or number
    status_strat = st.one_of(
        st.sampled_from(statuses),
        st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses),
        st.none(),
        st.integers(min_value=0, max_value=10),
    )
    # tags: array of strings, but sometimes empty array, sometimes array with nulls or numbers or booleans
    tag_element_strat = st.one_of(
        st.text(min_size=0, max_size=10),
        st.none(),
        st.integers(min_value=0, max_value=100),
        st.booleans(),
    )
    tags_strat = st.lists(tag_element_strat, min_size=0, max_size=5)

    # Recursive child: either null or a nested record (one level max)
    # To avoid infinite recursion, we limit depth to 1.
    # We produce a record with the same schema but with child=null.
    # We also sometimes produce wrong types for child (string, number, bool)
    @st.composite
    def child_record(draw):
        # child record with child=null (no further recursion)
        id_ = draw(id_strat)
        amount = draw(amount_strat)
        name = draw(name_strat)
        status = draw(status_strat)
        tags = draw(tags_strat)
        # child is null here to avoid deep recursion
        child = None

        # Build JSON text for this child record
        # We must produce syntactically valid JSON text with correct commas and quotes
        def json_str(s):
            # Escape quotes and backslashes minimally
            return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

        # Serialize tags array
        def serialize_tags(tags):
            elems = []
            for t in tags:
                if t is None:
                    elems.append("null")
                elif isinstance(t, bool):
                    elems.append("true" if t else "false")
                elif isinstance(t, int):
                    elems.append(str(t))
                else:
                    elems.append(json_str(str(t)))
            return "[" + ",".join(elems) + "]"

        # Serialize name (string or null or invalid type)
        def serialize_name(n):
            if n is None:
                return "null"
            elif isinstance(n, bool):
                return "true" if n else "false"
            elif isinstance(n, int):
                return str(n)
            else:
                return json_str(str(n))

        # Serialize status (string, null, int)
        def serialize_status(s):
            if s is None:
                return "null"
            elif isinstance(s, bool):
                return "true" if s else "false"
            elif isinstance(s, int):
                return str(s)
            else:
                return json_str(str(s))

        # Serialize amount (string)
        def serialize_amount(a):
            return json_str(str(a))

        # Serialize child (always null here)
        child_json = "null"

        json_obj = (
            "{" +
            f'"id":{id_},' +
            f'"amount":{serialize_amount(amount)},' +
            f'"name":{serialize_name(name)},' +
            f'"status":{serialize_status(status)},' +
            f'"tags":{serialize_tags(tags)},' +
            f'"child":{child_json}' +
            "}"
        )
        return json_obj

    # Now draw the top-level record fields
    id_ = draw(id_strat)
    amount = draw(amount_strat)
    name = draw(name_strat)
    status = draw(status_strat)
    tags = draw(tags_strat)

    # For child, either null, a valid child record, or an invalid type (string, int, bool)
    child_choice = draw(st.one_of(
        st.just(None),
        child_record(),
        st.text(min_size=0, max_size=10),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
    ))

    def json_str(s):
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    def serialize_tags(tags):
        elems = []
        for t in tags:
            if t is None:
                elems.append("null")
            elif isinstance(t, bool):
                elems.append("true" if t else "false")
            elif isinstance(t, int):
                elems.append(str(t))
            else:
                elems.append(json_str(str(t)))
        return "[" + ",".join(elems) + "]"

    def serialize_name(n):
        if n is None:
            return "null"
        elif isinstance(n, bool):
            return "true" if n else "false"
        elif isinstance(n, int):
            return str(n)
        else:
            return json_str(str(n))

    def serialize_status(s):
        if s is None:
            return "null"
        elif isinstance(s, bool):
            return "true" if s else "false"
        elif isinstance(s, int):
            return str(s)
        else:
            return json_str(str(s))

    def serialize_amount(a):
        return json_str(str(a))

    # Serialize child
    if child_choice is None:
        child_json = "null"
    elif isinstance(child_choice, str):
        child_json = json_str(child_choice)
    elif isinstance(child_choice, bool):
        child_json = "true" if child_choice else "false"
    elif isinstance(child_choice, int):
        child_json = str(child_choice)
    else:
        # child_choice is a JSON string representing a record
        child_json = child_choice

    json_obj = (
        "{" +
        f'"id":{id_},' +
        f'"amount":{serialize_amount(amount)},' +
        f'"name":{serialize_name(name)},' +
        f'"status":{serialize_status(status)},' +
        f'"tags":{serialize_tags(tags)},' +
        f'"child":{child_json}' +
        "}"
    )

    return json_obj.encode("utf-8")