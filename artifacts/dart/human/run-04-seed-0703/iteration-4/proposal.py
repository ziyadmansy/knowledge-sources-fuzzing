from hypothesis import strategies as st

# Constants for fixed enums and limits
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce a JSON string literal with proper escaping of quotes and backslashes
def json_string_literal(s: str) -> str:
    # Minimal escaping for " and \ only, enough for Hypothesis-generated strings
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the described Record schema,
    with controlled variations to maximize behavioral divergence among four Dart JSON deserializers.
    """

    # Recursive generator for the "child" field, bounded to one level of recursion
    # child is either null or a Record object (no deeper recursion)
    def record_json(allow_missing_tags: bool):
        # id: integer or double (to exploit int vs num.toInt() difference)
        # Generate an integer in 64-bit range, or a float that jsonDecode will parse as double
        # We want to sometimes produce a float that is an integer value, sometimes a float with fraction
        # Also try out-of-range int as double to trigger saturation in json_serializable/freezed
        id_choice = draw(st.one_of(
            # true int in 64-bit range
            st.integers(min_value=-(2**63), max_value=2**63 - 1).map(str),
            # float with fractional part (should cause manual and built_value to reject)
            st.floats(allow_infinity=False, allow_nan=False, width=32).filter(lambda f: f != int(f)).map(lambda f: repr(f)),
            # float representing an integer but out of 64-bit range (to trigger saturation)
            st.one_of(
                st.just(str(float(2**63))),  # 2^63 as float (out of int64 range)
                st.just(str(float(-(2**63) - 1)))  # just below int64 min
            )
        ))

        # amount: string (always present, non-null)
        # Generate a non-empty string with some chance of special chars
        amount_str = draw(st.text(min_size=1, max_size=10))
        amount = json_string_literal(amount_str)

        # name: nullable string or null
        # Generate either null or a string (possibly empty)
        name_val = draw(st.one_of(
            st.none().map(lambda _: "null"),
            st.text(max_size=10).map(json_string_literal)
        ))

        # status: one of the three valid strings, or sometimes an invalid string to cause rejection
        # But invalid status causes all reject identically, so only use valid here
        status = draw(st.sampled_from(STATUS_VALUES))

        # tags: array of strings, or missing (to trigger built_value acceptance on missing)
        # We want to sometimes omit tags (only built_value accepts), sometimes present with correct type
        # Also try wrong type for tags (e.g. null or string) to cause all reject (no score)
        # So only omit or correct type here to maximize divergence
        tags_present = draw(st.booleans())
        if allow_missing_tags:
            # allow missing tags sometimes
            tags_present = draw(st.booleans())
        else:
            tags_present = True

        if tags_present:
            # tags: array of strings (possibly empty)
            tags_list = draw(st.lists(st.text(max_size=10), max_size=5))
            # encode as JSON array of strings
            tags_json = "[" + ",".join(json_string_literal(t) for t in tags_list) + "]"
        else:
            tags_json = None  # omit field

        # child: either null or a nested record (one level only)
        child_present = draw(st.booleans())
        if child_present:
            # nested record, but do NOT allow missing tags in child to avoid double complexity
            child_json_str = record_json(allow_missing_tags=False)
            child_json = child_json_str.decode("utf-8")
        else:
            child_json = "null"

        # Compose fields, omitting tags if tags_json is None
        fields = []
        fields.append('"id":' + id_choice)
        fields.append('"amount":' + amount)
        fields.append('"name":' + name_val)
        fields.append('"status":' + status)
        if tags_json is not None:
            fields.append('"tags":' + tags_json)
        # else omit tags field
        fields.append('"child":' + child_json)

        obj = "{" + ",".join(fields) + "}"
        return obj.encode("utf-8")

    # Top-level record, allow missing tags to trigger built_value acceptance divergence
    return record_json(allow_missing_tags=True)