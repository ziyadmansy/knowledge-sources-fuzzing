from hypothesis import strategies as st

# Helper: JSON string escaping minimal for ASCII control chars and quotes/backslash
def json_string_escape(s: str) -> str:
    # Escape backslash and quote, and control chars \b \f \n \r \t minimally
    # Hypothesis strings are unicode, but we restrict to ASCII printable for simplicity
    # We'll replace \ with \\, " with \", and control chars with \u00XX
    res = []
    for c in s:
        o = ord(c)
        if c == '\\':
            res.append('\\\\')
        elif c == '"':
            res.append('\\"')
        elif c == '\b':
            res.append('\\b')
        elif c == '\f':
            res.append('\\f')
        elif c == '\n':
            res.append('\\n')
        elif c == '\r':
            res.append('\\r')
        elif c == '\t':
            res.append('\\t')
        elif o < 0x20:
            res.append('\\u%04x' % o)
        else:
            res.append(c)
    return ''.join(res)

# JSON string literal from Python string
def json_string_literal(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers:
    manual, json_serializable, freezed, built_value.

    Strategy:
    - Always produce all six fields present (id, amount, name, status, tags, child),
      but vary types and values near boundaries.
    - id: integer or string (string should cause rejection by all, but test boundary)
    - amount: string normally, but sometimes empty string, or numeric string, or string "null"
    - name: string or null, sometimes empty string, sometimes unicode
    - status: one of "active", "inactive", "unknown" (correct case), or wrong case to provoke rejection
    - tags: array of strings, sometimes empty, sometimes with empty string, sometimes null (built_value accepts null tags)
    - child: null or nested record, one level only, with similar variations inside
    - Introduce subtle type errors in one field at a time to provoke divergence:
      e.g. null for tags (built_value accepts), missing status (built_value accepts),
      or status as null (all reject except built_value?), or amount as number (all reject),
      or child as null or object with one field wrong type.
    - Duplicate keys last wins (but all agree on last wins, so no divergence)
    - Extra keys ignored by all, so no divergence there.
    """

    # id: integer normally, but sometimes string (should reject all)
    id_val = draw(st.one_of(
        st.integers(min_value=0, max_value=2**31-1),
        st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()),  # string non-digit to provoke rejection
    ))

    # amount: string normally, but sometimes empty string, or numeric string, or "null" string
    amount_val = draw(st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: s != "null"),
        st.just(""),  # empty string
        st.integers(min_value=0, max_value=10000).map(str),  # numeric string
        st.just("null"),  # string "null"
    ))

    # name: string or null, sometimes empty string, sometimes unicode
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20),
    ))

    # status: mostly correct enum, sometimes wrong case, sometimes unknown string, sometimes null
    status_val = draw(st.one_of(
        st.sampled_from(["active", "inactive", "unknown"]),
        st.sampled_from(["ACTIVE", "Inactive", "unknown_status", ""]),  # wrong case or unknown
        st.none(),
    ))

    # tags: array of strings normally, sometimes empty array, sometimes null (built_value accepts null tags)
    # Also sometimes array with empty string, or strings with unicode
    tags_val = draw(st.one_of(
        st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5),
        st.none(),
    ))

    # child: null or nested record with one level recursion
    # Nested record fields follow same rules but simpler: id int only or string (to provoke rejection),
    # amount string normal or empty,
    # name string or null,
    # status correct enum only (to reduce complexity),
    # tags array of strings or null,
    # child null only (no deeper recursion)
    def nested_record():
        nid = draw(st.one_of(
            st.integers(min_value=0, max_value=2**31-1),
            st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()),
        ))
        namount = draw(st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: s != "null"),
            st.just(""),
        ))
        nname = draw(st.one_of(
            st.none(),
            st.text(min_size=0, max_size=20),
        ))
        nstatus = draw(st.sampled_from(["active", "inactive", "unknown"]))
        ntags = draw(st.one_of(
            st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=3),
            st.none(),
        ))
        # child null only
        return {
            "id": nid,
            "amount": namount,
            "name": nname,
            "status": nstatus,
            "tags": ntags,
            "child": None,
        }

    child_val = draw(st.one_of(
        st.none(),
        st.just(nested_record()),
    ))

    # Compose JSON text manually, carefully encoding each field

    def json_val(v):
        # Encode Python value v as JSON text (string)
        if v is None:
            return "null"
        elif isinstance(v, bool):
            return "true" if v else "false"
        elif isinstance(v, int):
            return str(v)
        elif isinstance(v, str):
            return json_string_literal(v)
        elif isinstance(v, list):
            return "[" + ",".join(json_val(x) for x in v) + "]"
        elif isinstance(v, dict):
            # keys always strings
            items = []
            for k, val in v.items():
                items.append(json_string_literal(k) + ":" + json_val(val))
            return "{" + ",".join(items) + "}"
        else:
            # fallback: encode as string
            return json_string_literal(str(v))

    # Build top-level dict
    top = {
        "id": id_val,
        "amount": amount_val,
        "name": name_val,
        "status": status_val,
        "tags": tags_val,
        "child": child_val,
    }

    # Serialize to JSON text
    json_text = json_val(top)

    # Return bytes UTF-8 encoded
    return json_text.encode("utf-8")