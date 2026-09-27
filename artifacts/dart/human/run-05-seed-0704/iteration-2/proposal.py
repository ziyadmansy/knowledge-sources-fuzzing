from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for fields with limited domains
    STATUS_VALUES = ["active", "inactive", "unknown"]
    
    # Helper: produce a JSON string literal from a Python string (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars minimally
        # Only minimal escaping needed for ASCII printable strings from Hypothesis
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        # Also escape control chars (U+0000 to U+001F)
        s = ''.join(
            c if 0x20 <= ord(c) <= 0x10FFFF else '\\u%04x' % ord(c)
            for c in s
        )
        return '"' + s + '"'
    
    # Helper: produce JSON text for a string or null
    def json_string_or_null():
        # 80% chance string, 20% chance null
        return draw(
            st.one_of(
                st.none().map(lambda _: "null"),
                st.text(min_size=0, max_size=20).map(json_string),
            )
        )
    
    # Helper: produce JSON text for tags array (array of strings)
    def json_tags():
        # tags must be present (empty allowed)
        # strings can be empty or up to 10 chars
        strs = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
        # Compose JSON array text
        arr = "[" + ",".join(json_string(s) for s in strs) + "]"
        return arr
    
    # Helper: produce JSON text for child field (null or nested record)
    # Limit recursion depth to 1 level as per spec
    def json_child(depth=0):
        if depth >= 1:
            # Only null allowed at depth 1
            return "null"
        else:
            # 50% chance null, 50% chance nested record
            if draw(st.booleans()):
                return "null"
            else:
                # Nested record: reuse record strategy with depth+1
                return json_record(depth + 1)
    
    # Helper: produce JSON text for id field
    # To trigger divergence on id decoding:
    # manual and built_value require true int (no double)
    # json_serializable and freezed accept double and convert to int with toInt()
    # jsonDecode converts large int literals outside 64-bit range to double
    # So produce either:
    # - a normal int in 64-bit range (all accept)
    # - a large int outside 64-bit range (encoded as JSON number literal)
    # - a double that is integral (e.g. 1.0)
    # We'll produce either an int or a float number literal as string (no quotes)
    def json_id():
        choice = draw(st.integers(min_value=0, max_value=2))
        if choice == 0:
            # Normal int in 64-bit range
            val = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
            return str(val)
        elif choice == 1:
            # Large int outside 64-bit range, encoded as JSON number (will be double)
            # Use a number > 2**63 or < -2**63
            val = draw(
                st.one_of(
                    st.integers(min_value=2**63, max_value=2**65),
                    st.integers(min_value=-(2**65), max_value=-(2**63 + 1)),
                )
            )
            return str(val)
        else:
            # Integral double literal (e.g. 42.0)
            val = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
            return str(val) + ".0"
    
    # Helper: produce JSON text for amount field (string)
    # Use arbitrary string, non-empty to avoid trivial rejection
    def json_amount():
        s = draw(st.text(min_size=1, max_size=20))
        return json_string(s)
    
    # Helper: produce JSON text for status field
    # Use only valid values (to avoid universal rejection)
    def json_status():
        return json_string(draw(st.sampled_from(STATUS_VALUES)))
    
    # Helper: produce JSON text for name field (nullable string)
    def json_name():
        return json_string_or_null()
    
    # Compose a full record JSON text
    def json_record(depth=0):
        # Compose fields as key:value JSON text pairs
        # We will vary presence of tags field to trigger divergence:
        # built_value accepts missing tags as empty list,
        # others reject missing tags.
        # So sometimes omit tags field.
        # But only omit tags at top-level (depth=0), not nested child.
        omit_tags = False
        if depth == 0:
            omit_tags = draw(st.booleans())
        # Compose fields
        parts = []
        parts.append('"id":' + json_id())
        parts.append('"amount":' + json_amount())
        parts.append('"name":' + json_name())
        parts.append('"status":' + json_status())
        if not omit_tags:
            parts.append('"tags":' + json_tags())
        # child field always present (nullable)
        parts.append('"child":' + json_child(depth))
        # Compose JSON object text
        return "{" + ",".join(parts) + "}"
    
    # Generate top-level record JSON text
    json_text = json_record(depth=0)
    # Return as bytes (UTF-8)
    return json_text.encode("utf-8")