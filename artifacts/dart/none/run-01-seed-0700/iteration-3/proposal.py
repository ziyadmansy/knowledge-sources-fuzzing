from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal with proper escaping for minimal chars
    # Hypothesis strings can contain any unicode, but we restrict to safe ASCII subset for simplicity
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars (below 0x20)
        s_escaped = []
        for c in s:
            if ord(c) < 0x20:
                s_escaped.append(f"\\u{ord(c):04x}")
            else:
                s_escaped.append(c)
        return '"' + "".join(s_escaped) + '"'

    # id: integer, but we will sometimes produce a string to cause divergence
    # amount: string, but sometimes produce a number or null to cause divergence
    # name: string or null, sometimes produce number or boolean to cause divergence
    # status: one of the three strings, sometimes produce a wrong string or null
    # tags: array of strings, sometimes array of mixed types or empty, or null
    # child: either null or a nested record (one level recursion max)
    # We will produce mostly well-formed documents, but with 1 or 2 fields subtly off.

    # To control recursion depth, pass a parameter
    def record(draw, depth=0):
        # Decide if this record is null or object (child can be null)
        # For top-level record, always object
        # For child, allow null with some probability
        if depth > 1:
            # max 1 level recursion, so child is always null here
            child_json = "null"
        else:
            # child can be null or a record
            child_json = draw(st.one_of(
                st.just("null"),
                record(depth=depth+1)
            ))

        # id field: mostly integer, sometimes stringified integer, sometimes float, sometimes null
        id_choice = draw(st.integers(min_value=0, max_value=10**9))
        id_type = draw(st.sampled_from(["int", "str_int", "float", "null"]))
        if id_type == "int":
            id_json = str(id_choice)
        elif id_type == "str_int":
            id_json = json_string(str(id_choice))
        elif id_type == "float":
            # float with .0 to look like int but is float
            id_json = str(float(id_choice)) + ".0"
            # but .0 is invalid JSON number, so just float without trailing .0
            # Actually JSON allows floats with .0, so it's valid
            id_json = str(float(id_choice))
        else:
            id_json = "null"

        # amount field: normally string, but sometimes number, null, or boolean
        amount_str = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
        amount_type = draw(st.sampled_from(["str", "num", "null", "bool"]))
        if amount_type == "str":
            amount_json = json_string(amount_str)
        elif amount_type == "num":
            # number as int or float string
            amount_json = draw(st.one_of(
                st.integers(min_value=0, max_value=10**6).map(str),
                st.floats(min_value=0, max_value=10**6, allow_nan=False, allow_infinity=False).map(lambda f: format(f, '.2f'))
            ))
        elif amount_type == "null":
            amount_json = "null"
        else:
            amount_json = draw(st.sampled_from(["true", "false"]))

        # name field: string or null normally, sometimes number or boolean
        name_type = draw(st.sampled_from(["str", "null", "num", "bool"]))
        if name_type == "str":
            # allow empty string or normal string
            name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\']))))
            if name_val is None:
                name_json = "null"
            else:
                name_json = json_string(name_val)
        elif name_type == "null":
            name_json = "null"
        elif name_type == "num":
            name_json = draw(st.one_of(
                st.integers(min_value=-1000, max_value=1000).map(str),
                st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False).map(lambda f: format(f, '.3f'))
            ))
        else:
            name_json = draw(st.sampled_from(["true", "false"]))

        # status field: normally one of the three strings, sometimes null or wrong string
        status_type = draw(st.sampled_from(["valid", "null", "wrong_str"]))
        if status_type == "valid":
            status_json = json_string(draw(st.sampled_from(statuses)))
        elif status_type == "null":
            status_json = "null"
        else:
            # wrong string: random string not in statuses
            wrong_str = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
            # ensure not in statuses
            while wrong_str in statuses:
                wrong_str = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
            status_json = json_string(wrong_str)

        # tags field: normally array of strings, sometimes empty array, sometimes array with non-string, sometimes null
        tags_type = draw(st.sampled_from(["valid", "empty", "mixed", "null"]))
        if tags_type == "valid":
            tags_list = draw(st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])), min_size=1, max_size=5))
            tags_json = "[" + ",".join(json_string(t) for t in tags_list) + "]"
        elif tags_type == "empty":
            tags_json = "[]"
        elif tags_type == "mixed":
            # mix strings and numbers or booleans
            n = draw(st.integers(min_value=1, max_value=5))
            elems = []
            for _ in range(n):
                t = draw(st.sampled_from(["str", "num", "bool"]))
                if t == "str":
                    s = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
                    elems.append(json_string(s))
                elif t == "num":
                    elems.append(str(draw(st.integers(min_value=0, max_value=1000))))
                else:
                    elems.append(draw(st.sampled_from(["true", "false"])))
            tags_json = "[" + ",".join(elems) + "]"
        else:
            tags_json = "null"

        # Compose JSON object fields in random order to avoid bias
        fields = [
            ('"id"', id_json),
            ('"amount"', amount_json),
            ('"name"', name_json),
            ('"status"', status_json),
            ('"tags"', tags_json),
            ('"child"', child_json),
        ]
        draw.shuffle(fields)

        json_obj = "{" + ",".join(f"{k}:{v}" for k, v in fields) + "}"
        return json_obj

    # Generate top-level record (depth=0)
    json_text = record(draw, depth=0)
    return json_text.encode("utf-8")