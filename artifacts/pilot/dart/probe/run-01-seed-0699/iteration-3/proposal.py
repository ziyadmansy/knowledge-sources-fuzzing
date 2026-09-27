from hypothesis import strategies as st

# Constants for enum values and field names
STATUS_VALUES = ['active', 'inactive', 'unknown']

# Helper: produce a JSON string literal from a Python string (escape minimal set)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote minimally for JSON string literal
    # Also escape control chars \b \f \n \r \t for safety
    esc = s.replace('\\', '\\\\').replace('"', '\\"')
    esc = esc.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return '"' + esc + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, matching the record schema,
    with subtle variations to provoke divergence between four Dart JSON deserializers.
    """

    # --- Strategies for each field ---

    # id: integer (always integer, no divergence here)
    id_val = draw(st.integers(min_value=-(2**31), max_value=2**31-1))

    # amount: string, but try to provoke divergence by using numeric strings, empty strings, or unusual unicode
    # Always string type (no type errors), but content varies
    amount_val = draw(st.one_of(
        st.text(min_size=0, max_size=20),  # arbitrary string, possibly empty
        st.just("0"),                      # numeric string "0"
        st.just("-123.45"),                # numeric string negative float
        st.just("1e10"),                   # numeric string scientific notation
        st.just(" "),                     # single space
        st.just("null"),                  # string "null"
    ))

    # name: string or null
    # To provoke divergence, try empty string, unicode, or null
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=30),
    ))

    # status: enum string, always one of allowed values (no divergence on enum values)
    status_val = draw(st.sampled_from(STATUS_VALUES))

    # tags: array of strings, no nulls allowed
    # To provoke divergence, try empty array, array with empty strings, or array with unicode strings
    tags_len = draw(st.integers(min_value=0, max_value=5))
    tags_val = draw(st.lists(st.text(min_size=0, max_size=10), min_size=tags_len, max_size=tags_len))

    # child: either null or a nested record (one level recursion)
    # To provoke divergence, child can be null or a record with subtle variations
    # Limit recursion to one level only

    # We'll define a helper to produce the child JSON text recursively (one level only)
    def child_json():
        # id integer
        cid = draw(st.integers(min_value=-(2**31), max_value=2**31-1))
        # amount string
        camount = draw(st.one_of(
            st.text(min_size=0, max_size=20),
            st.just("0"),
            st.just("-123.45"),
            st.just("1e10"),
            st.just(" "),
            st.just("null"),
        ))
        # name string or null
        cname = draw(st.one_of(st.none(), st.text(min_size=0, max_size=30)))
        # status enum
        cstatus = draw(st.sampled_from(STATUS_VALUES))
        # tags array of strings
        clen = draw(st.integers(min_value=0, max_value=3))
        ctags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=clen, max_size=clen))
        # child null only (no deeper recursion)
        cchild = None

        # Compose child JSON text
        # Use last-key-wins trick: optionally duplicate keys with different values to provoke divergence
        # But since last key wins consistently, no divergence expected here, so keep simple

        parts = []
        parts.append('"id":' + str(cid))
        parts.append('"amount":' + json_string_literal(camount))
        if cname is None:
            parts.append('"name":null')
        else:
            parts.append('"name":' + json_string_literal(cname))
        parts.append('"status":' + json_string_literal(cstatus))
        # tags array
        tags_json = '[' + ','.join(json_string_literal(t) for t in ctags) + ']'
        parts.append('"tags":' + tags_json)
        parts.append('"child":null')

        # Compose as JSON object
        return '{' + ','.join(parts) + '}'

    # Decide if child is null or object
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json_text = 'null'
    else:
        child_json_text = child_json()

    # Compose top-level JSON object text

    parts = []
    parts.append('"id":' + str(id_val))
    parts.append('"amount":' + json_string_literal(amount_val))
    if name_val is None:
        parts.append('"name":null')
    else:
        parts.append('"name":' + json_string_literal(name_val))
    parts.append('"status":' + json_string_literal(status_val))
    tags_json = '[' + ','.join(json_string_literal(t) for t in tags_val) + ']'
    parts.append('"tags":' + tags_json)
    parts.append('"child":' + child_json_text)

    # To provoke subtle divergence, optionally add duplicate keys with different values for "name" or "id" at top level or in child
    # Since last key wins consistently, no divergence expected here, so skip duplicates to focus on type/enum subtleties

    json_text = '{' + ','.join(parts) + '}'

    return json_text.encode('utf-8')