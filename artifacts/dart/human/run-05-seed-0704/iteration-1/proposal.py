from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Recursive record generator, depth limited to 1 for "child" field
    # Returns a dict with all six fields present (or null for nullable ones)
    def record(depth=0):
        # id: integer or double (to trigger json_serializable/freezed difference)
        # We produce either a true int or a float representing an int (or out-of-range)
        # to exploit the known difference in id decoding.
        # Also produce some int64 out-of-range values as float to test saturation.
        id_choice = draw(st.one_of(
            st.integers(min_value=-(2**53), max_value=2**53),  # safe int range
            st.floats(min_value=-(2**63)*2, max_value=(2**63)*2, allow_infinity=False, allow_nan=False).filter(lambda f: f.is_integer())
        ))
        # amount: string, always present, non-null
        amount = draw(st.text(min_size=1, max_size=10))

        # name: nullable string or null
        name = draw(st.one_of(st.none(), st.text(max_size=10)))

        # status: one of the three valid strings, or sometimes an invalid string to test rejection
        # But invalid status rejected by all four, so no divergence there.
        # So always valid status to keep near well-formed.
        status = draw(st.sampled_from(statuses))

        # tags: array of strings, always present or sometimes missing (to test built_value behavior)
        # But missing tags accepted only by built_value, rejected by others.
        # To create divergence, sometimes omit tags field.
        # But we must produce syntactically valid JSON objects, so we must produce either
        # a tags field or omit it.
        # We'll produce a dict here, then later decide to omit tags or not.
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10), max_size=5))

        # child: nullable record or null, only one level recursion
        if depth == 0:
            child = draw(st.one_of(st.none(), record(depth=1)))
        else:
            child = None

        # Compose dict with all fields present
        base = {
            "id": id_choice,
            "amount": amount,
            "name": name,
            "status": status,
            "tags": tags_list,
            "child": child,
        }
        return base

    # Draw a record with all fields present
    base_record = draw(record())

    # Now decide whether to omit tags field or not (to trigger built_value acceptance divergence)
    omit_tags = draw(st.booleans())
    if omit_tags:
        # Remove tags field to test built_value acceptance vs others rejection
        base_record.pop("tags")

    # Now build JSON text by hand, carefully serializing each field

    def json_escape_str(s: str) -> str:
        # Minimal JSON string escaping for control chars and quotes/backslash
        # Hypothesis text can contain any Unicode, but JSON strings must escape
        # backslash, quote, and control chars (U+0000 to U+001F).
        # We'll replace backslash, quote, and control chars with escapes.
        res = []
        for c in s:
            o = ord(c)
            if c == '"':
                res.append('\\"')
            elif c == '\\':
                res.append('\\\\')
            elif 0 <= o <= 0x1F:
                res.append('\\u%04x' % o)
            else:
                res.append(c)
        return '"' + "".join(res) + '"'

    def json_serialize_value(v):
        # Serialize a JSON value (int, float, str, null, list, dict)
        if v is None:
            return "null"
        elif isinstance(v, bool):
            return "true" if v else "false"
        elif isinstance(v, int):
            return str(v)
        elif isinstance(v, float):
            # JSON floats must be finite and not NaN
            # Use repr to get shortest decimal representation
            # But repr(float) may produce scientific notation, which is valid JSON
            # We rely on Hypothesis floats filtered to be finite and integer-valued for id
            # For safety, format with repr
            return repr(v)
        elif isinstance(v, str):
            return json_escape_str(v)
        elif isinstance(v, list):
            return "[" + ",".join(json_serialize_value(x) for x in v) + "]"
        elif isinstance(v, dict):
            # keys must be strings
            items = []
            for k, val in v.items():
                items.append(json_escape_str(k) + ":" + json_serialize_value(val))
            return "{" + ",".join(items) + "}"
        else:
            # Should not happen
            raise ValueError("Unsupported type in json_serialize_value")

    # Serialize the base_record dict to JSON text
    json_text = json_serialize_value(base_record)

    # Return bytes
    return json_text.encode("utf-8")