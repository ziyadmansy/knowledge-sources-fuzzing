from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Recursive record generator with depth limit 1 for "child"
    # Returns a dict with all fields present (including child as dict or null)
    def record_strategy(depth=0):
        # id: integer (Dart int)
        # To trigger divergence on id decoding, generate ints and also large ints outside 64-bit range,
        # which json_serializable/freezed accept as double->toInt(), manual/built_value reject.
        # But since jsonDecode produces int or double, we generate integers as strings and parse them as numbers in JSON text.
        # We must produce valid JSON numbers, so generate integers in range -2**65..2**65 to cross 64-bit boundary.
        # But JSON numbers are limited in precision, so large integers will be parsed as doubles by jsonDecode.
        # We'll generate id as a JSON number literal (no quotes).
        id_int = draw(
            st.one_of(
                st.integers(min_value=-(2**63), max_value=2**63 - 1),  # in-range 64-bit int
                st.integers(min_value=-(2**65), max_value=-(2**63 + 1)),  # out-of-range negative
                st.integers(min_value=2**63, max_value=2**65),  # out-of-range positive
            )
        )
        # amount: string (non-null)
        # Use simple decimal strings, but also try empty string and strings with digits and dots
        amount_str = draw(
            st.one_of(
                st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s) and s.strip(".") != ""),
                st.just("0"),
                st.just("123.45"),
                st.just(""),
            )
        )
        # name: string or null
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))

        # status: one of the three valid strings
        status_val = draw(st.sampled_from(statuses))

        # tags: array of strings (always present)
        # To test missing tags (which built_value accepts but others reject), we will never omit tags here,
        # but we can test empty array and arrays with empty strings or normal strings.
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))

        # child: either null or a nested record (depth limited to 1)
        if depth == 0:
            child_val = draw(st.one_of(st.none(), record_strategy(depth=1)))
        else:
            child_val = None

        # Build JSON text for this record as a string (not a Python dict)
        # We must produce syntactically valid JSON text with all six fields present.
        # Fields: id (number), amount (string), name (string|null), status (string), tags (array of strings), child (object|null)

        # Helper to JSON-escape strings (minimal, only backslash and quote)
        def json_escape(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"')

        # Serialize id as JSON number literal (no quotes)
        id_json = str(id_int)

        # Serialize amount as JSON string
        amount_json = '"' + json_escape(amount_str) + '"'

        # Serialize name as JSON string or null
        name_json = "null" if name_val is None else '"' + json_escape(name_val) + '"'

        # Serialize status as JSON string
        status_json = '"' + status_val + '"'

        # Serialize tags as JSON array of strings
        tags_json = "[" + ",".join('"' + json_escape(t) + '"' for t in tags_list) + "]"

        # Serialize child as JSON object or null
        if child_val is None:
            child_json = "null"
        else:
            child_json = child_val

        # Compose JSON object string with all fields present
        json_obj = (
            '{'
            + '"id":' + id_json + ','
            + '"amount":' + amount_json + ','
            + '"name":' + name_json + ','
            + '"status":' + status_json + ','
            + '"tags":' + tags_json + ','
            + '"child":' + child_json
            + '}'
        )
        return json_obj

    # Draw top-level record JSON text string
    top_json = record_strategy(depth=0)

    # Return bytes (UTF-8 encoded)
    return top_json.encode("utf-8")