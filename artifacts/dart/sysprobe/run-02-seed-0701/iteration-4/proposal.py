from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations designed to trigger behavioral divergence among four Dart JSON deserializers:
    manual, json_serializable, freezed, built_value.

    Strategy:
    - Always produce all six fields (id, amount, name, status, tags, child) present.
    - Vary one or two fields per document to be "almost valid" but with subtle type or value deviations.
    - Use bounded recursion for child (max depth 1).
    - Use string concatenation to build JSON text.
    - Produce bytes output.
    """

    # Constants
    STATUSES = ["active", "inactive", "unknown"]
    # For subtle divergence, also try "status" as null or missing (but here always present),
    # or as wrong case (known rejected by all, so skip),
    # or as unknown enum (rejected by all, skip).
    # Instead, try "status" as string but with trailing spaces or unicode escapes (should be accepted identically).
    # But since trailing spaces in enum likely rejected, keep enum exact.

    # Helper to produce JSON string literal with proper escaping of quotes and backslashes
    def json_string(s: str) -> str:
        # Minimal escaping for " and \ and control chars
        # Hypothesis strings are unicode, so escape backslash and quote
        # and control chars <0x20 as \u00XX
        res = []
        for c in s:
            o = ord(c)
            if c == '"':
                res.append('\\"')
            elif c == '\\':
                res.append('\\\\')
            elif o < 0x20:
                res.append('\\u%04x' % o)
            else:
                res.append(c)
        return '"' + ''.join(res) + '"'

    # Recursive record generator with max depth 1
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # id: integer, but try subtle variants:
        # - valid integer as number (e.g. 0..1000)
        # - integer as string (should be rejected by all, but we want to test)
        # - integer as float (e.g. 1.0) (known rejected by all, skip)
        # - integer as string with leading zeros (should be string, rejected)
        # But since "id" must be integer, try only integer number or string number to provoke divergence.

        # amount: string, try normal decimal strings, empty string, or numeric strings with leading zeros,
        # or string with spaces, or string with unicode escapes.
        # Also try amount as number string vs number (number rejected by all, skip).
        # Try amount as string but empty or "0".

        # name: string or null, try normal strings, null, empty string, or string with unicode escapes.

        # status: one of "active", "inactive", "unknown" exactly.
        # Try also null (known rejected by all except built_value?), but per known, null status rejected by all except built_value.
        # We always produce present field, so try null here to provoke divergence.

        # tags: array of strings, try empty array, array with normal strings, array with empty strings,
        # or null (accepted only by built_value as empty array).
        # Try null tags to provoke divergence.

        # child: null or record (depth 0 or 1).
        # If depth == 1, child must be null (no deeper recursion).
        # If depth == 0, child can be null or record with depth=1.

        # We will produce all fields always present, but vary one or two fields subtly.

        # To provoke divergence, randomly choose one or two fields to "mutate" subtly.

        # Base valid values:
        base_id = draw(st.integers(min_value=0, max_value=1000))
        base_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)))
        # restrict amount to ascii printable to avoid complex escaping
        base_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))))
        base_status = draw(st.sampled_from(STATUSES))
        base_tags = draw(st.lists(st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), max_size=5))
        # child null or record
        if depth == 1:
            base_child = None
        else:
            base_child = draw(st.one_of(st.none(), record_json(depth=1)))

        # Decide which fields to mutate (0, 1 or 2 fields)
        mutate_count = draw(st.integers(min_value=1, max_value=2))
        mutate_fields = draw(st.sampled_from([
            ["id"], ["amount"], ["name"], ["status"], ["tags"], ["child"],
            ["id", "amount"], ["id", "name"], ["id", "status"], ["id", "tags"], ["id", "child"],
            ["amount", "name"], ["amount", "status"], ["amount", "tags"], ["amount", "child"],
            ["name", "status"], ["name", "tags"], ["name", "child"],
            ["status", "tags"], ["status", "child"],
            ["tags", "child"],
        ]))

        mutate_fields = mutate_fields[:mutate_count]

        # Mutators for each field to produce subtle divergence:

        def mutate_id(val):
            # id normally integer number
            # mutate to string number (e.g. "123"), or string with leading zeros, or negative number as string
            choice = draw(st.sampled_from(["int", "str_num", "str_leading_zeros", "str_negative"]))
            if choice == "int":
                return str(val)
            elif choice == "str_num":
                return json_string(str(val))
            elif choice == "str_leading_zeros":
                s = str(val)
                s = "000" + s
                return json_string(s)
            else:  # str_negative
                return json_string("-" + str(val))
        def mutate_amount(val):
            # amount normally string
            # mutate to empty string, string with spaces, string with unicode escapes, or number as string
            choice = draw(st.sampled_from(["empty", "spaces", "unicode_esc", "number_str"]))
            if choice == "empty":
                return json_string("")
            elif choice == "spaces":
                return json_string(" " + val + " ")
            elif choice == "unicode_esc":
                # replace some chars by \u escapes
                if len(val) == 0:
                    s = "\\u0030"  # '0'
                else:
                    s = ""
                    for c in val:
                        if draw(st.booleans()):
                            s += "\\u%04x" % ord(c)
                        else:
                            s += c
                return '"' + s + '"'
            else:  # number_str
                # try numeric string, e.g. "123.45"
                num_str = draw(st.one_of(
                    st.integers(min_value=0, max_value=1000).map(str),
                    st.floats(min_value=0, max_value=1000).map(lambda f: "%.2f" % f)
                ))
                return json_string(num_str)
        def mutate_name(val):
            # name nullable string
            # mutate to null (explicit), empty string, string with quotes, or string with unicode escapes
            choice = draw(st.sampled_from(["null", "empty", "quotes", "unicode_esc"]))
            if choice == "null":
                return "null"
            elif choice == "empty":
                return json_string("")
            elif choice == "quotes":
                # string with embedded quotes
                s = 'He said "hello"'
                return json_string(s)
            else:  # unicode_esc
                s = ""
                for c in val if val else "name":
                    if draw(st.booleans()):
                        s += "\\u%04x" % ord(c)
                    else:
                        s += c
                return '"' + s + '"'
        def mutate_status(val):
            # status enum string
            # mutate to null (known rejected by all except built_value),
            # or valid enum but with trailing space (likely rejected by all),
            # or valid enum uppercase (rejected by all),
            # or unknown enum (rejected by all),
            # or string with unicode escapes (should be accepted identically)
            choice = draw(st.sampled_from(["null", "trailing_space", "uppercase", "unknown", "unicode_esc", "valid"]))
            if choice == "null":
                return "null"
            elif choice == "trailing_space":
                return json_string(val + " ")
            elif choice == "uppercase":
                return json_string(val.upper())
            elif choice == "unknown":
                return json_string("invalid_status")
            elif choice == "unicode_esc":
                s = ""
                for c in val:
                    if draw(st.booleans()):
                        s += "\\u%04x" % ord(c)
                    else:
                        s += c
                return '"' + s + '"'
            else:  # valid exact
                return json_string(val)
        def mutate_tags(val):
            # tags array of strings
            # mutate to null (accepted only by built_value),
            # or array with empty strings,
            # or array with one non-string element (known rejected by all),
            # or array with unicode escaped strings,
            # or empty array
            choice = draw(st.sampled_from(["null", "empty_strings", "non_string_elem", "unicode_esc", "empty_array", "valid"]))
            if choice == "null":
                return "null"
            elif choice == "empty_strings":
                arr = ["\"\"" for _ in val]
                return "[" + ",".join(arr) + "]"
            elif choice == "non_string_elem":
                # Insert one integer element at random position
                if len(val) == 0:
                    arr = ["123"]
                else:
                    pos = draw(st.integers(min_value=0, max_value=len(val)-1))
                    arr = []
                    for i, s in enumerate(val):
                        if i == pos:
                            arr.append("123")
                        else:
                            arr.append(json_string(s))
                return "[" + ",".join(arr) + "]"
            elif choice == "unicode_esc":
                arr = []
                for s in val:
                    s2 = ""
                    for c in s:
                        if draw(st.booleans()):
                            s2 += "\\u%04x" % ord(c)
                        else:
                            s2 += c
                    arr.append('"' + s2 + '"')
                return "[" + ",".join(arr) + "]"
            elif choice == "empty_array":
                return "[]"
            else:  # valid exact
                arr = [json_string(s) for s in val]
                return "[" + ",".join(arr) + "]"
        def mutate_child(val):
            # child is null or record JSON string
            # mutate to null, empty object {}, empty array [], or malformed record (missing required field),
            # or valid record (no mutation)
            choice = draw(st.sampled_from(["null", "empty_object", "empty_array", "malformed_missing_id", "valid"]))
            if choice == "null":
                return "null"
            elif choice == "empty_object":
                return "{}"
            elif choice == "empty_array":
                return "[]"
            elif choice == "malformed_missing_id":
                # produce a record JSON string missing "id" field (known rejected by all except built_value for some fields)
                # but here we produce child with missing "id"
                # minimal record with all fields except id
                # id is integer required
                # amount string required
                # name string or null
                # status enum required
                # tags array required
                # child null or record
                # We produce minimal child with missing id
                # Use fixed values for simplicity
                child_fields = []
                child_fields.append('"amount":"100"')
                child_fields.append('"name":null')
                child_fields.append('"status":"active"')
                child_fields.append('"tags":["tag1"]')
                child_fields.append('"child":null')
                return "{" + ",".join(child_fields) + "}"
            else:  # valid exact
                return val if val is not None else "null"

        # Build fields with possible mutation
        # id
        if "id" in mutate_fields:
            id_json = mutate_id(base_id)
        else:
            id_json = str(base_id)

        # amount
        if "amount" in mutate_fields:
            amount_json = mutate_amount(base_amount)
        else:
            amount_json = json_string(base_amount)

        # name
        if "name" in mutate_fields:
            name_json = mutate_name(base_name)
        else:
            if base_name is None:
                name_json = "null"
            else:
                name_json = json_string(base_name)

        # status
        if "status" in mutate_fields:
            status_json = mutate_status(base_status)
        else:
            status_json = json_string(base_status)

        # tags
        if "tags" in mutate_fields:
            tags_json = mutate_tags(base_tags)
        else:
            tags_json = "[" + ",".join(json_string(s) for s in base_tags) + "]"

        # child
        if "child" in mutate_fields:
            child_json = mutate_child(base_child if base_child is not None else "null")
        else:
            if base_child is None:
                child_json = "null"
            else:
                child_json = base_child

        # Compose JSON object string
        # Field order fixed to avoid divergence on ordering
        json_obj = (
            "{" +
            f'"id":{id_json},' +
            f'"amount":{amount_json},' +
            f'"name":{name_json},' +
            f'"status":{status_json},' +
            f'"tags":{tags_json},' +
            f'"child":{child_json}' +
            "}"
        )

        return json_obj

    # Generate top-level record JSON string
    json_str = draw(record_json(depth=0))

    # Return bytes
    return json_str.encode("utf-8")