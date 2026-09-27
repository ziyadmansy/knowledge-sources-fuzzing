from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Recursive record generator with bounded depth (max 1 level of recursion)
    def record_strat(depth: int):
        # id: integer (Dart int), but jsonDecode can produce double for large ints
        # To exploit difference in id decoding, sometimes produce a large int literal
        # outside 64-bit range, which jsonDecode parses as double.
        # We'll produce id as a string of digits (no quotes) to produce JSON number literals.
        # Hypothesis integers can be arbitrarily large, but we limit to 128-bit range for feasibility.
        # We'll produce id as int or as a large int that jsonDecode will parse as double.
        # To produce large int literals that jsonDecode parses as double, produce integers > 2**63 or < -2**63.
        # But JSON numbers have no quotes, so we produce them as stringified numbers in JSON text.

        # amount: string, non-nullable
        # name: string or null (nullable)
        # status: one of the three strings
        # tags: array of strings, always present (but can be empty)
        # child: record or null (nullable)

        # We want to produce syntactically valid JSON text, so we produce strings with quotes escaped properly.

        # Helper to produce JSON string literal from Python string (escaping quotes and backslashes)
        def json_string_literal(s: str) -> str:
            # Escape backslash and double quote
            s_escaped = s.replace('\\', '\\\\').replace('"', '\\"')
            # Also escape control chars (U+0000 to U+001F) as \uXXXX
            def escape_control_chars(ch):
                if ord(ch) < 0x20:
                    return '\\u%04x' % ord(ch)
                return ch
            s_escaped = ''.join(escape_control_chars(c) for c in s_escaped)
            return '"' + s_escaped + '"'

        # id number literal as string (no quotes)
        def id_number_literal(i: int) -> str:
            # Produce decimal literal, possibly negative
            return str(i)

        # amount string literal
        amount_str = draw(st.text(min_size=1, max_size=20))
        amount_json = json_string_literal(amount_str)

        # name: string or null
        name_val = draw(st.one_of(st.none(), st.text(max_size=20)))
        if name_val is None:
            name_json = "null"
        else:
            name_json = json_string_literal(name_val)

        # status: one of the three strings
        status_val = draw(st.sampled_from(statuses))
        status_json = json_string_literal(status_val)

        # tags: array of strings, always present
        # To test differences, produce empty or non-empty arrays
        tags_list = draw(st.lists(st.text(max_size=10), max_size=5))
        # Produce JSON array literal of strings
        tags_json = "[" + ",".join(json_string_literal(t) for t in tags_list) + "]"

        # id: integer, sometimes large to trigger double in jsonDecode
        # We produce either a normal 64-bit int or a large int outside 64-bit range
        id_choice = draw(st.booleans())
        if id_choice:
            # normal 64-bit int range
            id_val = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
        else:
            # large int outside 64-bit range, e.g. 2**63 to 2**70 or negative equivalent
            large_positive = draw(st.booleans())
            if large_positive:
                id_val = draw(st.integers(min_value=2**63, max_value=2**70))
            else:
                id_val = draw(st.integers(min_value=-(2**70), max_value=-(2**63 + 1)))
        id_json = id_number_literal(id_val)

        # child: record or null (nullable), only recurse if depth == 0 (max 1 level)
        if depth == 0:
            child_val = draw(st.one_of(st.none(), record_strat(depth + 1)))
            if child_val is None:
                child_json = "null"
            else:
                child_json = child_val
        else:
            # no further recursion, child must be null
            child_json = "null"

        # Compose JSON object fields as list of key:value strings
        # We always include all six fields (id, amount, name, status, tags, child)
        # To test missing tags behavior, sometimes omit tags field (built_value accepts, others reject)
        omit_tags = draw(st.booleans())
        fields = [
            '"id":' + id_json,
            '"amount":' + amount_json,
            '"name":' + name_json,
            '"status":' + status_json,
        ]
        if not omit_tags:
            fields.append('"tags":' + tags_json)
        fields.append('"child":' + child_json)

        # Compose JSON object text
        json_obj = "{" + ",".join(fields) + "}"

        return json_obj

    # Draw top-level record with depth 0
    json_text = draw(record_strat(0))
    # Return bytes (UTF-8 encoded)
    return json_text.encode("utf-8")