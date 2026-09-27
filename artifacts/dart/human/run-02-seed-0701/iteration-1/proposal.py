from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Helper: JSON string escape (minimal, only backslash and quote)
    def json_string(s: str) -> str:
        # Escape backslash and quote for JSON string
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Recursive record generator with depth limit
    def record(depth: int) -> st.SearchStrategy[str]:
        # id: int or double (to trigger divergence in id decoding)
        # We produce either an int literal or a double literal representing an int
        # or a double outside int64 range to test saturation behavior.
        # We produce numbers as JSON text, not Python numbers.
        def id_text():
            # Choose one of:
            # 1) int in 32-bit range (normal int)
            # 2) double with .0 fractional part (like 1234.0)
            # 3) double outside int64 range (e.g. 1e20)
            choice = draw(st.integers(min_value=1, max_value=3))
            if choice == 1:
                v = draw(st.integers(min_value=-(2**31), max_value=2**31 - 1))
                return str(v)
            elif choice == 2:
                v = draw(st.integers(min_value=-(2**31), max_value=2**31 - 1))
                return str(float(v))  # e.g. "1234.0"
            else:
                # large double outside int64 range
                # Use a large exponent double literal
                # Use positive or negative large double
                sign = draw(st.sampled_from(["", "-"]))
                exp = draw(st.integers(min_value=20, max_value=30))
                base = draw(st.floats(min_value=1.0, max_value=9.9))
                # Format as JSON number
                return f"{sign}{base}e{exp}"

        # amount: string (non-empty, printable ASCII)
        amount_str = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
        amount_json = json_string(amount_str)

        # name: string or null (nullable)
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126))))
        name_json = "null" if name_val is None else json_string(name_val)

        # status: one of known strings or deliberately unrecognized string (to test rejection)
        # But unrecognized status is rejected by all four, so no divergence there.
        # Instead, sometimes produce correct status, sometimes a wrong type (e.g. number or null)
        # Wrong type is rejected by all, so no divergence.
        # So always produce correct status string to keep document almost well-formed.
        status_val = draw(st.sampled_from(statuses))
        status_json = json_string(status_val)

        # tags: array of strings, or missing (to test built_value accepting missing tags)
        # We produce either present tags (empty or non-empty array) or missing tags.
        # Missing tags triggers divergence: built_value accepts, others reject.
        tags_present = draw(st.booleans())
        if tags_present:
            # array of strings (possibly empty)
            tags_list = draw(st.lists(st.text(min_size=0, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126)), max_size=5))
            # JSON array of strings
            tags_json = "[" + ",".join(json_string(t) for t in tags_list) + "]"
        else:
            tags_json = None  # missing field

        # child: null or nested record (one level recursion only)
        if depth == 0:
            child_json = "null"
        else:
            # 50% chance null, 50% chance nested record with depth-1
            if draw(st.booleans()):
                child_json = "null"
            else:
                child_json = draw(record(depth - 1))

        # id field JSON text
        id_json = id_text()

        # Compose fields in random order to test unknown keys acceptance
        # Add an extra unknown key sometimes (accepted by all)
        extra_key = draw(st.one_of(st.none(), st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=97, max_codepoint=122))))
        extra_value = None
        if extra_key is not None:
            # extra value: string or number or null
            extra_value = draw(st.one_of(
                st.text(min_size=0, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).map(json_string),
                st.integers(min_value=-1000, max_value=1000).map(str),
                st.just("null"),
            ))

        # Build list of (key,json_value) pairs
        fields = [
            ("id", id_json),
            ("amount", amount_json),
            ("name", name_json),
            ("status", status_json),
        ]
        if tags_json is not None:
            fields.append(("tags", tags_json))
        if child_json is not None:
            fields.append(("child", child_json))
        if extra_key is not None:
            fields.append((extra_key, extra_value))

        # Shuffle fields order
        from random import shuffle
        shuffle(fields)

        # Compose JSON object text
        obj_text = "{" + ",".join(f"{json_string(k)}:{v}" for k, v in fields) + "}"

        return obj_text

    # Draw top-level record with depth=1 (allow one nested child)
    json_text = draw(record(depth=1))
    return json_text.encode("utf-8")