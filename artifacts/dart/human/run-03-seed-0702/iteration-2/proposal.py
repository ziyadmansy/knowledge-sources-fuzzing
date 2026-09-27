from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal with proper escaping for " and \
    def json_string(s: str) -> str:
        # minimal escaping for " and \ and control chars
        # Hypothesis strings are unicode, but JSON strings must escape control chars
        # We'll just replace backslash and quote for safety, and replace control chars with \uXXXX
        def esc_char(c):
            o = ord(c)
            if c == '"':
                return '\\"'
            if c == '\\':
                return '\\\\'
            if 0 <= o <= 0x1F:
                return '\\u%04x' % o
            return c
        return '"' + ''.join(esc_char(c) for c in s) + '"'

    # id field: integer or double that represents an integer (to test int vs double)
    # manual and built_value require int, json_serializable and freezed accept double.toInt()
    # jsonDecode turns out-of-range int literals into double
    # So we generate either:
    # - an int in int64 range (safe)
    # - a float that is an integer but out of int64 range (to test saturation)
    # We'll generate either an int or a float string literal for id field.
    # JSON numbers are unquoted.
    # int64 range: -9223372036854775808 to 9223372036854775807
    # We'll pick a boundary value just outside int64 range to test saturation.
    int64_min = -9223372036854775808
    int64_max = 9223372036854775807
    # out of range values just outside int64 range
    out_of_range_values = [int64_min - 1, int64_max + 1]

    # Decide if id is int or float (that looks like an int)
    id_is_float = draw(st.booleans())
    if id_is_float:
        # pick out of range or in range float that is integral
        # in range integral float (e.g. 42.0) is accepted by all, no divergence
        # out of range integral float triggers saturation in json_serializable/freezed
        id_val = draw(st.sampled_from(out_of_range_values))
        # represent as float literal with .0 to force jsonDecode to parse as double
        id_json = str(float(id_val))
    else:
        # int in range
        id_val = draw(st.integers(min_value=int64_min, max_value=int64_max))
        id_json = str(id_val)

    # amount: string, always present, non-null
    # generate arbitrary non-empty string without control chars or quotes to keep JSON simple
    amount_str = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)))
    amount_json = json_string(amount_str)

    # name: nullable string or null
    # generate either null or a string (possibly empty)
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        name_str = draw(st.text(max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)))
        name_json = json_string(name_str)

    # status: one of the three valid strings, or an invalid string to test rejection
    # But all reject invalid status, so no divergence there.
    # We'll only generate valid status to keep documents mostly well-formed.
    status_val = draw(st.sampled_from(statuses))
    status_json = json_string(status_val)

    # tags: array of strings, always present or missing (missing triggers divergence)
    # We want to sometimes omit tags to trigger built_value accepting and others rejecting.
    tags_missing = draw(st.booleans())
    if not tags_missing:
        # tags present: array of 0 to 3 strings
        tags_list = draw(st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)), max_size=3))
        tags_json_items = [json_string(t) for t in tags_list]
        tags_json = "[" + ",".join(tags_json_items) + "]"
    else:
        tags_json = None  # omit field

    # child: nullable record or null
    # To keep recursion bounded, child is either null or a record with no child (child=null)
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json = "null"
    else:
        # child record with child=null (one level recursion)
        # id: int in range (no float here to keep complexity low)
        child_id = draw(st.integers(min_value=int64_min, max_value=int64_max))
        child_id_json = str(child_id)
        # amount: non-empty string
        child_amount_str = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)))
        child_amount_json = json_string(child_amount_str)
        # name: nullable string or null
        child_name_is_null = draw(st.booleans())
        if child_name_is_null:
            child_name_json = "null"
        else:
            child_name_str = draw(st.text(max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)))
            child_name_json = json_string(child_name_str)
        # status: valid status
        child_status_val = draw(st.sampled_from(statuses))
        child_status_json = json_string(child_status_val)
        # tags: present, empty array (to keep simple)
        child_tags_json = "[]"
        # child: null
        child_child_json = "null"
        child_json = (
            "{" +
            f'"id":{child_id_json},'
            f'"amount":{child_amount_json},'
            f'"name":{child_name_json},'
            f'"status":{child_status_json},'
            f'"tags":{child_tags_json},'
            f'"child":{child_child_json}'
            "}"
        )

    # Compose top-level JSON object fields as key:value strings
    fields = [
        f'"id":{id_json}',
        f'"amount":{amount_json}',
        f'"name":{name_json}',
        f'"status":{status_json}',
    ]
    if tags_json is not None:
        fields.append(f'"tags":{tags_json}')
    # else omit tags field to test divergence

    fields.append(f'"child":{child_json}')

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")