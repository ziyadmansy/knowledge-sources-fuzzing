from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values and nullability
    STATUS_VALUES = ["active", "inactive", "unknown"]
    # Weights chosen to produce mostly valid documents with small focused deviations
    # to maximize divergence among the four deserializers.

    # Helper: produce a JSON string literal with proper escaping of backslash and quote
    def json_string_literal(s: str) -> str:
        # Minimal escaping for " and \ only, enough for test purposes
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return '"' + s + '"'

    # Helper: produce JSON array of strings (with possible coercion to ints later)
    def json_array_of_strings(draw):
        # Generate list of strings, possibly empty
        strs = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        # Map to JSON string literals
        return "[" + ",".join(json_string_literal(s) for s in strs) + "]"

    # Helper: produce JSON array of strings or ints (to test coercion)
    def json_array_of_strings_or_ints(draw):
        # Generate list of elements, each either string or int
        elems = draw(st.lists(st.one_of(
            st.text(min_size=0, max_size=10).map(json_string_literal),
            st.integers(min_value=-1000, max_value=1000).map(str)
        ), min_size=0, max_size=5))
        return "[" + ",".join(elems) + "]"

    # Helper: produce JSON string or number for "amount" field, or null, or missing
    def amount_field(draw):
        # Decide variant: correct string, number coerced to string, null, missing
        variant = draw(st.sampled_from(["string", "number", "null", "missing"]))
        if variant == "missing":
            return None
        elif variant == "string":
            s = draw(st.text(min_size=0, max_size=10))
            return json_string_literal(s)
        elif variant == "number":
            n = draw(st.integers(min_value=-1000, max_value=1000))
            return str(n)
        else:  # null
            return "null"

    # Helper: produce JSON for "id" field: integer, null, or missing
    def id_field(draw):
        variant = draw(st.sampled_from(["int", "null", "missing"]))
        if variant == "missing":
            return None
        elif variant == "int":
            n = draw(st.integers(min_value=0, max_value=10000))
            return str(n)
        else:  # null
            return "null"

    # Helper: produce JSON for "name" field: string, null, or missing
    def name_field(draw):
        variant = draw(st.sampled_from(["string", "null", "missing"]))
        if variant == "missing":
            return None
        elif variant == "string":
            s = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            if s is None:
                # name can be null or string, so null allowed
                return "null"
            else:
                return json_string_literal(s)
        else:  # null
            return "null"

    # Helper: produce JSON for "status" field: valid enum, unknown enum, case variant, null, missing
    def status_field(draw):
        variant = draw(st.sampled_from(["valid", "unknown_enum", "case_variant", "null", "missing"]))
        if variant == "missing":
            return None
        elif variant == "valid":
            val = draw(st.sampled_from(STATUS_VALUES))
            return json_string_literal(val)
        elif variant == "unknown_enum":
            # A string not in enum
            val = draw(st.text(min_size=1, max_size=10).filter(lambda x: x.lower() not in STATUS_VALUES))
            return json_string_literal(val)
        elif variant == "case_variant":
            val = draw(st.sampled_from(STATUS_VALUES))
            # Change case randomly
            val = "".join(c.upper() if draw(st.booleans()) else c.lower() for c in val)
            # Ensure it's different case from original
            if val.lower() == val:
                val = val.upper()
            return json_string_literal(val)
        else:  # null
            return "null"

    # Helper: produce JSON for "tags" field: array of strings, array of ints, null, missing
    def tags_field(draw):
        variant = draw(st.sampled_from(["string_array", "int_array", "null", "missing"]))
        if variant == "missing":
            return None
        elif variant == "string_array":
            return json_array_of_strings(draw)
        elif variant == "int_array":
            return json_array_of_strings_or_ints(draw)
        else:  # null
            return "null"

    # Helper: produce JSON for "child" field: null, missing, or nested record (one level recursion)
    def child_field(draw, depth=0):
        # Limit recursion depth to 1 (one level)
        variant = draw(st.sampled_from(["null", "missing", "record"]))
        if variant == "missing":
            return None
        elif variant == "null":
            return "null"
        else:
            # nested record, depth limited to 1
            if depth >= 1:
                # At max depth, produce null or missing only
                return draw(st.sampled_from(["null", None]))
            else:
                # Produce nested record JSON string (without bytes conversion)
                nested = record_json(draw, depth=depth+1)
                return nested

    # Compose a record JSON string (not bytes)
    def record_json(draw, depth=0):
        # Compose fields with possible missing or null or wrong types per known divergence points
        fields = []

        # id field
        id_val = id_field(draw)
        if id_val is not None:
            fields.append('"id":' + id_val)

        # amount field
        amount_val = amount_field(draw)
        if amount_val is not None:
            fields.append('"amount":' + amount_val)

        # name field
        name_val = name_field(draw)
        if name_val is not None:
            fields.append('"name":' + name_val)

        # status field
        status_val = status_field(draw)
        if status_val is not None:
            fields.append('"status":' + status_val)

        # tags field
        tags_val = tags_field(draw)
        if tags_val is not None:
            fields.append('"tags":' + tags_val)

        # child field
        child_val = child_field(draw, depth=depth)
        if child_val is not None:
            fields.append('"child":' + child_val)

        # Possibly add extra unknown keys to trigger divergence on unknown keys acceptance
        add_unknown = draw(st.booleans())
        if add_unknown:
            # Add one or two unknown keys with simple values
            unknown_count = draw(st.integers(min_value=1, max_value=2))
            for i in range(unknown_count):
                key = f'"unknown{i}"'
                # Value either string or number or null
                val = draw(st.one_of(
                    st.text(min_size=0, max_size=10).map(json_string_literal),
                    st.integers(min_value=-1000, max_value=1000).map(str),
                    st.just("null")
                ))
                fields.append(f"{key}:{val}")

        # Possibly add duplicate keys for one field to test last-wins behavior
        add_duplicate = draw(st.booleans())
        if add_duplicate and len(fields) > 0:
            # Pick a random existing field key to duplicate
            keys = [f.split(":", 1)[0] for f in fields]
            dup_key = draw(st.sampled_from(keys))
            # Generate a new value for the duplicate key
            # For simplicity, duplicate with a fixed value depending on key
            if dup_key == '"id"':
                dup_val = str(draw(st.integers(min_value=0, max_value=10000)))
            elif dup_key == '"amount"':
                dup_val = json_string_literal(draw(st.text(min_size=0, max_size=10)))
            elif dup_key == '"name"':
                dup_val = json_string_literal(draw(st.text(min_size=0, max_size=10)))
            elif dup_key == '"status"':
                dup_val = json_string_literal(draw(st.sampled_from(STATUS_VALUES)))
            elif dup_key == '"tags"':
                dup_val = json_array_of_strings(draw)
            elif dup_key == '"child"':
                # duplicate child with null for simplicity
                dup_val = "null"
            else:
                dup_val = json_string_literal(draw(st.text(min_size=0, max_size=10)))
            # Append duplicate key last (last wins)
            fields.append(f"{dup_key}:{dup_val}")

        # Compose JSON object string
        return "{" + ",".join(fields) + "}"

    # Generate top-level record JSON string
    json_str = record_json(draw, depth=0)

    # Return as bytes
    return json_str.encode("utf-8")