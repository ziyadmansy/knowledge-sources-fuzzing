from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON documents as bytes, encoding a Record with the schema:
    {
      "id": <integer>,
      "amount": <string or number or null or missing>,
      "name": <string or null or missing>,
      "status": <enum string or invalid or null or missing>,
      "tags": <array of strings or null or missing>,
      "child": <Record or null or missing>
    }
    with bounded recursion (max depth 1 for child),
    and with controlled variations to trigger divergences between Gson, Moshi, kotlinx.serialization, and Jackson.
    """

    # Constants for status field
    valid_statuses = ["active", "inactive", "unknown"]
    # Include some invalid enum variants to trigger enum parsing divergence
    invalid_statuses = ["Active", "INACTIVE", "invalid", ""]

    # Helper to generate a valid or invalid status string or null or missing
    def status_strategy():
        # 70% valid enum, 10% invalid enum, 10% null, 10% missing
        choice = draw(st.integers(min_value=1, max_value=100))
        if choice <= 70:
            return draw(st.sampled_from(valid_statuses))
        elif choice <= 80:
            return draw(st.sampled_from(invalid_statuses))
        elif choice <= 90:
            return None  # null
        else:
            return st.missing  # special marker for missing

    # Helper to generate amount field variations:
    # string (normal), number (to string), null, missing
    def amount_strategy():
        choice = draw(st.integers(min_value=1, max_value=100))
        if choice <= 60:
            # string amount, including empty string and numeric strings
            return draw(st.text(min_size=0, max_size=10))
        elif choice <= 80:
            # number amount (int or float)
            # Use int or float as string, but output as number in JSON
            # We'll output raw JSON text, so we must distinguish string vs number
            # We'll return a tuple (type, value) to encode later
            n = draw(st.one_of(st.integers(min_value=0, max_value=10**6),
                               st.floats(min_value=0, max_value=10**6, allow_nan=False, allow_infinity=False)))
            return ("number", n)
        elif choice <= 90:
            return None  # null
        else:
            return st.missing  # missing field

    # Helper to generate name field variations:
    # string, null, missing
    def name_strategy():
        choice = draw(st.integers(min_value=1, max_value=100))
        if choice <= 70:
            return draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        elif choice <= 90:
            return None  # null
        else:
            return st.missing  # missing

    # Helper to generate tags field variations:
    # array of strings, empty array, null, missing
    def tags_strategy():
        choice = draw(st.integers(min_value=1, max_value=100))
        if choice <= 70:
            # array of 0 to 5 strings
            arr = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
            return arr
        elif choice <= 90:
            return None  # null
        else:
            return st.missing  # missing

    # Helper to generate id field variations:
    # integer, null, missing
    # id is non-nullable int, so null or missing triggers divergence
    def id_strategy():
        choice = draw(st.integers(min_value=1, max_value=100))
        if choice <= 80:
            return draw(st.integers(min_value=0, max_value=10**9))
        elif choice <= 90:
            return None  # null
        else:
            return st.missing  # missing

    # Helper to generate child field variations:
    # null, missing, or nested record (depth 1 only)
    def child_strategy(depth=0):
        # max depth 1
        choice = draw(st.integers(min_value=1, max_value=100))
        if choice <= 60:
            # nested record (depth 1 only)
            if depth >= 1:
                # At max depth, produce null or missing or empty object (to trigger Gson acceptance of empty child)
                choice2 = draw(st.integers(min_value=1, max_value=100))
                if choice2 <= 50:
                    return None
                elif choice2 <= 80:
                    return st.missing
                else:
                    # empty object with all fields missing/null/defaulted
                    # We'll encode this as a dict with all fields missing or null or zero
                    # but since we build JSON text manually, we return a special marker
                    return "empty_child"
            else:
                # produce a nested record with fields, but with one or two fields missing or null to trigger divergence
                # We'll reuse the main record generation but with depth+1
                return draw(record_strategy(depth=depth+1))
        elif choice <= 80:
            return None
        else:
            return st.missing

    # Main record strategy producing a dict or special markers
    @st.composite
    def record_strategy(draw, depth=0):
        # id field
        id_val = draw(id_strategy())
        # amount field
        amount_val = draw(amount_strategy())
        # name field
        name_val = draw(name_strategy())
        # status field
        status_val = draw(status_strategy())
        # tags field
        tags_val = draw(tags_strategy())
        # child field
        child_val = draw(child_strategy(depth=depth))

        # Build dict with possible missing fields
        d = {}

        # id is required, but may be missing or null to trigger divergence
        if id_val is not st.missing:
            d["id"] = id_val

        # amount field variations
        if amount_val is not st.missing:
            d["amount"] = amount_val

        # name field variations
        if name_val is not st.missing:
            d["name"] = name_val

        # status field variations
        if status_val is not st.missing:
            d["status"] = status_val

        # tags field variations
        if tags_val is not st.missing:
            d["tags"] = tags_val

        # child field variations
        if child_val is not st.missing:
            d["child"] = child_val

        return d

    # Compose the record
    record = draw(record_strategy())

    # Now encode the record dict to JSON text manually, recursively
    def encode_json_value(val):
        # val can be:
        # - int
        # - float
        # - str
        # - None
        # - list
        # - dict
        # - special ("empty_child")
        # - tuple ("number", number) for amount field number variant

        if val is None:
            return "null"
        if val is st.missing:
            # Should never be here, missing fields are omitted
            return ""
        if val == "empty_child":
            # empty object with all fields missing/null/defaulted
            # According to known facts, Gson accepts empty object for child.child with all fields missing/null/defaulted,
            # others reject.
            # We'll encode as {}
            return "{}"
        if isinstance(val, tuple):
            # ("number", n)
            # encode number as JSON number
            typ, n = val
            if typ == "number":
                # floats must be encoded carefully
                if isinstance(n, float):
                    # Use repr to avoid scientific notation if possible
                    s = repr(n)
                    # JSON requires dot for floats
                    if "e" in s or "E" in s:
                        # format with fixed decimal places to avoid exponent
                        s = format(n, "f")
                    return s
                else:
                    return str(n)
            else:
                raise ValueError("Unknown tuple type in encode_json_value")
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, int):
            return str(val)
        if isinstance(val, float):
            # encode float as JSON number
            s = repr(val)
            if "e" in s or "E" in s:
                s = format(val, "f")
            return s
        if isinstance(val, str):
            # encode string with JSON escaping minimal for ASCII control chars and quotes
            # We'll escape backslash and double quote and control chars
            esc = val.translate(str.maketrans({
                '\\': '\\\\',
                '"': '\\"',
                '\b': '\\b',
                '\f': '\\f',
                '\n': '\\n',
                '\r': '\\r',
                '\t': '\\t',
            }))
            # Also escape control chars < 0x20 as \u00XX
            def escape_control_chars(s):
                res = []
                for c in s:
                    if ord(c) < 0x20:
                        res.append("\\u%04x" % ord(c))
                    else:
                        res.append(c)
                return "".join(res)
            esc = escape_control_chars(esc)
            return '"' + esc + '"'
        if isinstance(val, list):
            return "[" + ",".join(encode_json_value(x) for x in val) + "]"
        if isinstance(val, dict):
            # encode dict keys sorted for determinism
            items = []
            for k in sorted(val.keys()):
                v = val[k]
                items.append(encode_json_value(k) + ":" + encode_json_value(v))
            return "{" + ",".join(items) + "}"
        raise TypeError(f"Unsupported type in encode_json_value: {type(val)}")

    json_text = encode_json_value(record)
    return json_text.encode("utf-8")