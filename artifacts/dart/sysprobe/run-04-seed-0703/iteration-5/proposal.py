from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum "status"
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote, and control chars minimally
        # We keep it simple: replace \ and " only, no unicode escapes
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Replace control chars with \u00XX escapes (for chars < 0x20)
        def esc_char(c):
            if ord(c) < 0x20:
                return "\\u%04x" % ord(c)
            return c
        s = "".join(esc_char(c) for c in s)
        return '"' + s + '"'

    # Strategy for "id": integer, always present, non-null
    # To test boundary values, include some edge cases near int32 boundaries
    id_val = draw(st.one_of(
        st.integers(min_value=-(2**31), max_value=2**31-1),
        st.integers(min_value=-(2**53), max_value=2**53),  # Dart int can be 64-bit but JSON number is double
    ))

    # Strategy for "amount": string, always present, non-null
    # Use decimal-like strings, but also try empty string and some weird strings
    amount_val = draw(st.one_of(
        st.decimals(min_value=0, max_value=1e9, places=2).map(lambda d: format(d, "f")),
        st.just("0"),
        st.just(""),
        st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),  # printable ascii
    ))

    # Strategy for "name": string or null
    # Include empty string, unicode, and null
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
    ))

    # Strategy for "status": one of the three valid strings, or invalid variants to test rejection
    # But since all reject invalid enums, mostly produce valid ones, sometimes invalid to test rejection
    # To maximize disagreement, produce mostly valid but sometimes invalid casing or unknown string
    status_val = draw(st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES),
        st.sampled_from([s.upper() for s in STATUS_VALUES]),
    ))

    # Strategy for "tags": array of strings, always present except built_value accepts null or missing
    # To test divergence, sometimes produce null (accepted only by built_value), sometimes missing (not allowed here),
    # sometimes empty array, sometimes array of strings
    # We produce always present field here, but value can be null or array
    tags_val = draw(st.one_of(
        st.none(),  # accepted only by built_value
        st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), max_size=3),
    ))

    # Recursive child record or null
    # Limit recursion depth to 1 (child can have no child)
    # To maximize disagreement, sometimes produce null, sometimes a full record
    # For child record, we reuse the same strategy but with depth=0 (no further child)
    def child_record(depth: int):
        if depth <= 0:
            # no further recursion, child is null or a record with child=null
            return st.one_of(
                st.none(),
                st.builds(
                    lambda id_, amount, name, status, tags: {
                        "id": id_,
                        "amount": amount,
                        "name": name,
                        "status": status,
                        "tags": tags,
                        "child": None,
                    },
                    st.integers(min_value=-(2**31), max_value=2**31-1),
                    st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
                    st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))),
                    st.sampled_from(STATUS_VALUES),
                    st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), max_size=3),
                )
            )
        else:
            # depth > 0: child can recurse with depth-1
            return st.one_of(
                st.none(),
                st.builds(
                    lambda id_, amount, name, status, tags, child: {
                        "id": id_,
                        "amount": amount,
                        "name": name,
                        "status": status,
                        "tags": tags,
                        "child": child,
                    },
                    st.integers(min_value=-(2**31), max_value=2**31-1),
                    st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
                    st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))),
                    st.sampled_from(STATUS_VALUES),
                    st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), max_size=3),
                    child_record(depth - 1),
                )
            )

    child_val = draw(child_record(1))

    # Compose the top-level record as a dict
    record = {
        "id": id_val,
        "amount": amount_val,
        "name": name_val,
        "status": status_val,
        "tags": tags_val,
        "child": child_val,
    }

    # Now serialize record to JSON text manually, with minimal formatting and correct JSON syntax
    # We produce a JSON object string, then encode to bytes

    # Helper to serialize JSON value (str, int, None, list, dict)
    def serialize_json(val):
        if val is None:
            return "null"
        elif isinstance(val, bool):
            return "true" if val else "false"
        elif isinstance(val, int):
            return str(val)
        elif isinstance(val, float):
            # JSON floats: use repr, but avoid scientific notation if possible
            s = repr(val)
            if "e" in s or "E" in s:
                s = format(val, "f")
            return s
        elif isinstance(val, str):
            return json_string(val)
        elif isinstance(val, list):
            return "[" + ",".join(serialize_json(v) for v in val) + "]"
        elif isinstance(val, dict):
            # keys are strings
            items = []
            for k, v in val.items():
                items.append(json_string(k) + ":" + serialize_json(v))
            return "{" + ",".join(items) + "}"
        else:
            # Should not happen
            return "null"

    json_text = serialize_json(record)
    return json_text.encode("utf-8")