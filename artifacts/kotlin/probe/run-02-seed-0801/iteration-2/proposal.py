from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum status
    valid_statuses = ["active", "inactive", "unknown"]
    # We will produce a JSON text string, then encode to bytes at the end.

    # To control recursion depth for "child"
    max_depth = 1

    # Helper to produce a JSON string literal with proper escaping (minimal)
    def json_string(s: str) -> str:
        # Escape backslash and quote minimally for JSON string
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Helper to produce JSON text for a record at given recursion depth
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # id: integer or string convertible to integer
        # From known probes, all accept integer or string convertible to integer
        # We vary between int and string for id
        id_int = st.integers(min_value=0, max_value=10**9)
        id_str = id_int.map(str)
        id_val = draw(st.one_of(id_int, id_str))

        # amount: string or number (Gson, Moshi, Jackson accept number converted to string; kotlinx rejects number)
        # To maximize divergence, sometimes produce number, sometimes string
        # Also try some edge cases: number as int or float string
        amount_number = st.one_of(
            st.integers(min_value=0, max_value=10**9),
            st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)
        )
        amount_string = st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s)
        # We pick either a JSON string or a JSON number for amount
        amount_val = draw(st.one_of(
            amount_string.map(json_string),
            amount_number.map(lambda n: str(n) if (not isinstance(n, float) or n.is_integer()) else repr(n))
        ))

        # name: string or null normally
        # Gson and Jackson accept string, number, boolean converted to string
        # Moshi and kotlinx reject non-string non-null
        # We try to produce name as:
        # - null
        # - string
        # - number (int or float)
        # - boolean
        # - (not object or array, to avoid all rejecting)
        name_kind = draw(st.sampled_from(["null", "string", "number", "boolean"]))
        if name_kind == "null":
            name_val = "null"
        elif name_kind == "string":
            s = draw(st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
            name_val = json_string(s)
        elif name_kind == "number":
            n = draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False)))
            # JSON number formatting
            if isinstance(n, float) and not n.is_integer():
                name_val = repr(n)
            else:
                name_val = str(int(n))
        else:  # boolean
            b = draw(st.booleans())
            name_val = "true" if b else "false"

        # status: must be exact enum strings "active", "inactive", "unknown"
        # Invalid values cause Moshi, kotlinx, Jackson to reject; Gson accepts but sets null
        # To maximize divergence, sometimes produce valid, sometimes invalid string, sometimes null
        status_kind = draw(st.sampled_from(["valid", "invalid", "null"]))
        if status_kind == "valid":
            status_val = json_string(draw(st.sampled_from(valid_statuses)))
        elif status_kind == "invalid":
            # invalid string not in enum, e.g. "activ", "inactiv", "unknown2", or empty string
            invalid_statuses = ["activ", "inactiv", "unknown2", "", "ACTIVE", "Inactive"]
            status_val = json_string(draw(st.sampled_from(invalid_statuses)))
        else:
            # null status (known to be accepted only by Gson with null)
            status_val = "null"

        # tags: must be array
        # Non-array causes all to reject
        # Elements: strings normally
        # Gson, Moshi, Jackson accept non-string elements converted to strings; kotlinx rejects
        # Also null elements accepted by Gson, Moshi, Jackson; rejected by kotlinx
        # To maximize divergence, produce tags as array with elements of mixed types or nulls sometimes
        # Also try empty array and small arrays
        tags_len = draw(st.integers(min_value=0, max_value=3))
        tag_element_kind = draw(st.sampled_from(["string", "number", "boolean", "null"]))
        def tag_element():
            if tag_element_kind == "string":
                s = draw(st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
                return json_string(s)
            elif tag_element_kind == "number":
                n = draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False)))
                if isinstance(n, float) and not n.is_integer():
                    return repr(n)
                else:
                    return str(int(n))
            elif tag_element_kind == "boolean":
                b = draw(st.booleans())
                return "true" if b else "false"
            else:
                return "null"

        tags_elements = [tag_element() for _ in range(tags_len)]
        tags_val = "[" + ",".join(tags_elements) + "]"

        # child: null or nested record (one level of recursion normally)
        # We limit recursion depth to max_depth=1
        # Also try empty object for child (known to be accepted by Gson with defaults, rejected by others)
        # Also try null child
        if depth < max_depth:
            child_kind = draw(st.sampled_from(["null", "empty_object", "record"]))
        else:
            child_kind = "null"

        if child_kind == "null":
            child_val = "null"
        elif child_kind == "empty_object":
            child_val = "{}"
        else:
            # nested record at depth+1
            child_val = draw(record_json(depth + 1))

        # Compose JSON object text
        # Fields order fixed: id, amount, name, status, tags, child
        json_text = (
            '{'
            + '"id":' + (str(id_val) if isinstance(id_val, int) else json_string(str(id_val))) + ','
            + '"amount":' + amount_val + ','
            + '"name":' + name_val + ','
            + '"status":' + status_val + ','
            + '"tags":' + tags_val + ','
            + '"child":' + child_val
            + '}'
        )
        return st.just(json_text)

    # Draw top-level record JSON text
    result = draw(record_json(0))
    return result.encode("utf-8")