from hypothesis import strategies as st

# We build JSON text manually, carefully controlling types and structure.
# We produce documents that are almost well-formed but with one or two subtle divergences:
# - fields with wrong types (e.g. number instead of string)
# - null vs missing fields (we never omit fields here, but can produce null where string expected)
# - enum fields with wrong casing or wrong strings
# - arrays with mixed types or empty arrays
# - nested child record null or malformed (one level recursion only)
# We keep the overall structure stable to avoid all rejecting identically.

# Helper: JSON string escaper for Hypothesis strings (escape backslash and quote)
def json_string(s: str) -> str:
    # minimal escaping for JSON string: backslash and double quote
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    # Basic fields:
    # id: integer (sometimes string to cause divergence)
    # amount: string (sometimes number or null)
    # name: string or null (sometimes number or missing replaced by null)
    # status: enum "active", "inactive", "unknown" (sometimes wrong casing or invalid string)
    # tags: array of strings (sometimes empty, sometimes array with non-string)
    # child: null or one-level record (sometimes malformed child)

    # id: mostly integer, sometimes stringified number, sometimes float, sometimes null (invalid)
    id_val = draw(st.one_of(
        st.integers(min_value=0, max_value=10**9).map(str),
        st.integers(min_value=0, max_value=10**9),
        st.floats(allow_nan=False, allow_infinity=False).map(lambda f: str(f)),
        st.just("null"),
    ))

    # amount: mostly string, sometimes number, sometimes null
    amount_val = draw(st.one_of(
        st.text(min_size=1, max_size=10).map(json_string),
        st.integers(min_value=0, max_value=10**6).map(str),
        st.just("null"),
    ))

    # name: string or null, sometimes number or boolean as string to cause divergence
    name_val = draw(st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(json_string),
        st.integers(min_value=0, max_value=1000).map(str),
        st.booleans().map(lambda b: "true" if b else "false"),
    ))

    # status: enum with correct and incorrect casing, invalid strings
    status_val = draw(st.one_of(
        st.sampled_from(["\"active\"", "\"inactive\"", "\"unknown\""]),
        st.sampled_from(["\"Active\"", "\"Inactive\"", "\"Unknown\""]),
        st.sampled_from(["\"ACTIVE\"", "\"INACTIVE\"", "\"UNKNOWN\""]),
        st.sampled_from(["\"actve\"", "\"inactiv\"", "\"unknwn\""]),
        st.just("null"),
    ))

    # tags: array of strings, sometimes empty, sometimes with non-string elements
    # build array text manually
    def tags_array():
        # choose length 0 to 3
        length = draw(st.integers(min_value=0, max_value=3))
        elems = []
        for _ in range(length):
            # each element string or number or null or boolean
            elem = draw(st.one_of(
                st.text(min_size=0, max_size=10).map(json_string),
                st.integers(min_value=0, max_value=1000).map(str),
                st.just("null"),
                st.booleans().map(lambda b: "true" if b else "false"),
            ))
            elems.append(elem)
        return "[" + ",".join(elems) + "]"
    tags_val = tags_array()

    # child: null or one-level record, possibly malformed
    # To avoid infinite recursion, child is either null or a record with no child (child=null)
    # The child record fields can have similar divergences but no further recursion.
    def child_record():
        # child id
        cid = draw(st.one_of(
            st.integers(min_value=0, max_value=10**9).map(str),
            st.integers(min_value=0, max_value=10**9),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: str(f)),
            st.just("null"),
        ))
        # child amount
        camount = draw(st.one_of(
            st.text(min_size=1, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=10**6).map(str),
            st.just("null"),
        ))
        # child name
        cname = draw(st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=1000).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
        ))
        # child status
        cstatus = draw(st.one_of(
            st.sampled_from(["\"active\"", "\"inactive\"", "\"unknown\""]),
            st.sampled_from(["\"Active\"", "\"Inactive\"", "\"Unknown\""]),
            st.sampled_from(["\"ACTIVE\"", "\"INACTIVE\"", "\"UNKNOWN\""]),
            st.sampled_from(["\"actve\"", "\"inactiv\"", "\"unknwn\""]),
            st.just("null"),
        ))
        # child tags
        def child_tags_array():
            length = draw(st.integers(min_value=0, max_value=2))
            elems = []
            for _ in range(length):
                elem = draw(st.one_of(
                    st.text(min_size=0, max_size=10).map(json_string),
                    st.integers(min_value=0, max_value=1000).map(str),
                    st.just("null"),
                    st.booleans().map(lambda b: "true" if b else "false"),
                ))
                elems.append(elem)
            return "[" + ",".join(elems) + "]"
        ctags = child_tags_array()
        # child child is always null (no deeper recursion)
        cchild = "null"

        # Compose child record JSON text
        # Intentionally sometimes put fields in different order to test parsers (should not matter)
        # But keep consistent order here for simplicity
        child_json = (
            "{" +
            "\"id\":" + str(cid) + "," +
            "\"amount\":" + camount + "," +
            "\"name\":" + cname + "," +
            "\"status\":" + cstatus + "," +
            "\"tags\":" + ctags + "," +
            "\"child\":" + cchild +
            "}"
        )
        return child_json

    child_val = draw(st.one_of(
        st.just("null"),
        st.deferred(child_record),
    ))

    # Compose top-level JSON text
    # id field: if id_val is string type (already stringified), output as number or string accordingly
    # id_val can be string or int or float or "null" string
    def id_field_text(val):
        if val == "null":
            return "\"id\":null"
        try:
            # if val is int or float (number), output as number
            float_val = float(val)
            # if val is string representing int, output as number
            if isinstance(val, str) and val.isdigit():
                return f"\"id\":{val}"
            # if val is float string, output as number
            if isinstance(val, str):
                return f"\"id\":{val}"
            # else if int or float type
            return f"\"id\":{val}"
        except Exception:
            # fallback: output as JSON string
            return f"\"id\":{json_string(str(val))}"

    # id_val can be int, float string, or "null" string, or stringified int
    # We handle all as string and output raw (some may be invalid JSON numbers)
    # To maximize divergence, output id as raw text from id_val if it looks like number or null
    # else as JSON string
    if id_val == "null":
        id_text = "\"id\":null"
    else:
        try:
            # try parse float
            float(id_val)
            # looks like number, output raw
            id_text = f"\"id\":{id_val}"
        except Exception:
            # else output as JSON string
            id_text = f"\"id\":{json_string(str(id_val))}"

    # Compose full JSON text
    json_text = (
        "{" +
        id_text + "," +
        "\"amount\":" + amount_val + "," +
        "\"name\":" + name_val + "," +
        "\"status\":" + status_val + "," +
        "\"tags\":" + tags_val + "," +
        "\"child\":" + child_val +
        "}"
    )

    return json_text.encode("utf-8")