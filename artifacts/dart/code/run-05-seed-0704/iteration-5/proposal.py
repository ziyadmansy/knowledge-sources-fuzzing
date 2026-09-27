from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    valid_statuses = ["active", "inactive", "unknown"]
    # We will produce either a valid enum string or an invalid one to cause divergence
    # Manual and built_value throw raw ArgumentError on unknown enum strings (undocumented)
    # json_serializable and freezed throw documented CheckedFromJsonException on unknown enum strings

    # id: test int vs float with integral value (e.g. 1 vs 1.0) and also invalid types
    # manual requires int exactly (json number integral)
    # json_serializable/freezed accept num then toInt()
    # built_value likely requires integral number, may reject fractional

    # tags: array of strings normally, but test non-string elements to cause cast errors in manual/json_serializable/freezed

    # child: null or nested record (one level recursion max)
    # name: string or null, no divergence expected, keep simple

    # Strategy to produce a record as JSON text (string), then encode to bytes

    # Helper: produce JSON string literal from Python string (escape quotes and backslashes)
    def json_string_literal(s: str) -> str:
        # minimal escaping for JSON string: backslash and double quote
        # also escape control chars \b \f \n \r \t
        # Hypothesis strings are unicode, but we keep it simple and safe ASCII
        replacements = {
            '\\': '\\\\',
            '"': '\\"',
            '\b': '\\b',
            '\f': '\\f',
            '\n': '\\n',
            '\r': '\\r',
            '\t': '\\t',
        }
        res = []
        for c in s:
            if c in replacements:
                res.append(replacements[c])
            elif ord(c) < 0x20:
                # control chars escaped as \u00XX
                res.append('\\u%04x' % ord(c))
            else:
                res.append(c)
        return '"' + ''.join(res) + '"'

    # Compose JSON for a record, with recursion depth control
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # id field: choose among
        # - int (valid)
        # - float integral (e.g. 1.0) (accepted by json_serializable/freezed, maybe rejected by built_value)
        # - float non-integral (likely rejected by built_value and manual)
        # - string (invalid type, causes rejection)
        # - null (invalid type)
        id_strategy = st.one_of(
            st.integers(min_value=0, max_value=1000).map(str),
            st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)
              .filter(lambda f: f.is_integer())
              .map(lambda f: str(float(f))),
            st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)
              .filter(lambda f: not f.is_integer())
              .map(lambda f: str(f)),
            st.text(min_size=1, max_size=5).map(json_string_literal),
            st.just("null"),
        )

        # amount field: string, always present, produce valid JSON string
        amount_strategy = st.text(min_size=1, max_size=10).map(json_string_literal)

        # name field: string or null
        name_strategy = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).map(json_string_literal),
        )

        # status field: choose among valid enum strings or invalid strings to cause divergence
        # invalid strings include empty string, random strings, numbers as strings, etc.
        invalid_statuses = ["", "Active", "INACTIVE", "unknown ", "invalid", "null", "123"]
        status_strategy = st.one_of(
            st.sampled_from(valid_statuses).map(json_string_literal),
            st.sampled_from(invalid_statuses).map(json_string_literal),
        )

        # tags field: array of strings normally, but test non-string elements to cause cast errors
        # Elements can be:
        # - string (valid)
        # - int (invalid)
        # - null (invalid)
        # - bool (invalid)
        # - float (invalid)
        tag_element_strategy = st.one_of(
            st.text(min_size=0, max_size=5).map(json_string_literal),
            st.integers(min_value=0, max_value=10).map(str),
            st.none().map(lambda _: "null"),
            st.booleans().map(lambda b: "true" if b else "false"),
            st.floats(min_value=0, max_value=10, allow_nan=False, allow_infinity=False).map(str),
        )
        # tags array length 0 to 5
        tags_strategy = st.lists(tag_element_strategy, min_size=0, max_size=5).map(
            lambda elems: "[" + ",".join(elems) + "]"
        )

        # child field: null or nested record (depth limit 1)
        if depth >= 1:
            # only null to avoid deep recursion
            child_strategy = st.just("null")
        else:
            # 50% chance null, 50% chance nested record
            child_strategy = st.one_of(
                st.just("null"),
                record_json(depth + 1),
            )

        # Compose the JSON object string with all fields
        # Order fields exactly as in schema for consistency
        def compose_record(id_str, amount_str, name_str, status_str, tags_str, child_str) -> str:
            return (
                "{" +
                '"id":' + id_str + "," +
                '"amount":' + amount_str + "," +
                '"name":' + name_str + "," +
                '"status":' + status_str + "," +
                '"tags":' + tags_str + "," +
                '"child":' + child_str +
                "}"
            )

        return st.tuples(id_strategy, amount_strategy, name_strategy, status_strategy, tags_strategy, child_strategy).map(
            lambda t: compose_record(*t)
        )

    # Generate one top-level record JSON string, encode to bytes
    json_str = draw(record_json(depth=0))
    return json_str.encode("utf-8")