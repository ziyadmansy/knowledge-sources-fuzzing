from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal (quoted, escaped)
    def json_string(s: str) -> str:
        # Minimal escaping for JSON string: backslash and quote
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars (simplified)
        s = s.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{s}"'

    # Helper to produce JSON array of strings
    def json_string_array(strings):
        return "[" + ",".join(json_string(s) for s in strings) + "]"

    # Helper to produce JSON null or a nested record (one level recursion)
    # We'll limit recursion depth to 1 here by design.
    def json_record(depth=0):
        # id: integer (but we will sometimes produce a string to cause divergence)
        # amount: string (but sometimes a number or null)
        # name: string or null (sometimes missing or wrong type)
        # status: one of "active", "inactive", "unknown" (sometimes wrong string or null)
        # tags: array of strings (sometimes empty, sometimes wrong type)
        # child: null or record (only one level deep)
        # We'll produce mostly valid fields, but vary one or two fields subtly.

        # Start with valid fields
        # id: mostly int, sometimes string (to cause divergence)
        id_val = draw(st.one_of(st.integers(min_value=0, max_value=1000), st.text(min_size=1, max_size=5)))
        # amount: mostly string, sometimes number or null
        amount_val = draw(st.one_of(
            st.text(min_size=1, max_size=10),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: str(f)),
            st.just("null")
        ))
        # name: string or null, sometimes missing or wrong type (int)
        name_choice = draw(st.integers(min_value=0, max_value=4))
        if name_choice == 0:
            name_val = None
        elif name_choice == 1:
            name_val = draw(st.text(min_size=0, max_size=10))
        elif name_choice == 2:
            name_val = draw(st.integers(min_value=0, max_value=100))
        else:
            name_val = "null"  # string "null" to confuse

        # status: mostly valid enum string, sometimes wrong string or null
        status_choice = draw(st.integers(min_value=0, max_value=4))
        if status_choice <= 2:
            status_val = statuses[status_choice]
        elif status_choice == 3:
            status_val = "invalid_status"
        else:
            status_val = None

        # tags: array of strings, sometimes empty, sometimes array of ints, sometimes null
        tags_choice = draw(st.integers(min_value=0, max_value=3))
        if tags_choice == 0:
            tags_val = []
        elif tags_choice == 1:
            tags_val = draw(st.lists(st.text(min_size=1, max_size=5), max_size=3))
        elif tags_choice == 2:
            tags_val = draw(st.lists(st.integers(min_value=0, max_value=10), max_size=3))
        else:
            tags_val = None

        # child: null or nested record (only if depth==0)
        if depth == 0:
            child_choice = draw(st.integers(min_value=0, max_value=2))
            if child_choice == 0:
                child_val = None
            else:
                child_val = json_record(depth=1)
        else:
            child_val = None

        # Build JSON object string with subtle variations:
        # Sometimes omit fields (except id and amount which are always present)
        # Sometimes put wrong types or nulls

        # id field (always present)
        if isinstance(id_val, int):
            id_str = f'"id":{id_val}'
        else:
            # id as string (wrong type)
            id_str = f'"id":{json_string(str(id_val))}'

        # amount field (always present)
        if amount_val == "null":
            amount_str = '"amount":null'
        else:
            # amount as string or number string
            # If amount_val looks like a float string, quote it sometimes
            try:
                float(amount_val)
                # 50% chance quote or not
                if draw(st.booleans()):
                    amount_str = f'"amount":{amount_val}'
                else:
                    amount_str = f'"amount":{json_string(amount_val)}'
            except Exception:
                amount_str = f'"amount":{json_string(amount_val)}'

        # name field (optional or present with null or wrong type)
        if name_val is None:
            name_str = '"name":null'
        elif name_val == "null":
            name_str = f'"name":{json_string("null")}'
        elif isinstance(name_val, int):
            name_str = f'"name":{name_val}'
        else:
            name_str = f'"name":{json_string(name_val)}'

        # status field (optional or present with null or invalid string)
        if status_val is None:
            status_str = '"status":null'
        else:
            status_str = f'"status":{json_string(status_val)}'

        # tags field (optional or present with null or wrong type)
        if tags_val is None:
            tags_str = '"tags":null'
        elif isinstance(tags_val, list):
            if len(tags_val) == 0:
                tags_str = '"tags":[]'
            else:
                # Check if all strings or all ints
                if all(isinstance(t, str) for t in tags_val):
                    tags_str = f'"tags":{json_string_array(tags_val)}'
                elif all(isinstance(t, int) for t in tags_val):
                    # array of ints instead of strings (wrong type)
                    tags_str = "[" + ",".join(str(t) for t in tags_val) + "]"
                    tags_str = f'"tags":{tags_str}'
                else:
                    # mixed types, encode as strings forcibly
                    tags_str = f'"tags":{json_string_array([str(t) for t in tags_val])}'
        else:
            # unexpected type, encode as string forcibly
            tags_str = f'"tags":{json_string_array([str(tags_val)])}'

        # child field (null or nested record)
        if child_val is None:
            child_str = '"child":null'
        else:
            child_str = f'"child":{child_val}'

        # Compose fields, sometimes omit optional fields (name, status, tags, child)
        fields = [id_str, amount_str]

        # Omit name 10% of time
        if draw(st.booleans()) or draw(st.booleans()):
            fields.append(name_str)
        # Omit status 10% of time
        if draw(st.booleans()) or draw(st.booleans()):
            fields.append(status_str)
        # Omit tags 10% of time
        if draw(st.booleans()) or draw(st.booleans()):
            fields.append(tags_str)
        # Always include child (null or record)
        fields.append(child_str)

        # Shuffle fields order to vary JSON text
        draw(st.randoms())  # consume randomness
        # We cannot shuffle easily without importing random, so just join in order

        obj = "{" + ",".join(fields) + "}"
        return obj

    # Generate top-level record JSON string
    json_obj = json_record(depth=0)

    # Return bytes
    return json_obj.encode("utf-8")