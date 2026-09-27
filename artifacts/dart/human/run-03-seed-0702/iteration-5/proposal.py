from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python str (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars minimally
        # Only escape \ and " and control chars <0x20
        def esc_char(c):
            o = ord(c)
            if c == '"':
                return r'\"'
            if c == '\\':
                return r'\\'
            if o < 0x20:
                # Use \u00XX escape
                return '\\u%04x' % o
            return c
        return '"' + ''.join(esc_char(c) for c in s) + '"'

    # Helper: produce JSON array of strings
    def json_array_of_strings(lst):
        return "[" + ",".join(json_string(s) for s in lst) + "]"

    # id field: to maximize divergence, produce either:
    # - a true int within 64-bit range (accepted by all)
    # - a number outside 64-bit int range but integer literal (decoded by jsonDecode as double)
    # - a double with fractional part (rejected by manual and built_value, accepted by json_serializable/freezed)
    # We'll produce mostly valid int64-range ints, but sometimes out-of-range or fractional doubles
    id_choice = draw(st.integers(min_value=-2**63, max_value=2**63-1).map(lambda x: ("int", x)) |
                     st.floats(allow_infinity=False, allow_nan=False).filter(lambda f: abs(f) > 2**63 or (f != int(f))).map(lambda f: ("double", f)))

    # amount: string, always present, non-null
    # To keep it simple, produce decimal strings or empty string (empty string is valid string)
    amount_str = draw(st.text(min_size=0, max_size=10).map(lambda s: s.replace('"', '')))  # avoid quotes inside

    # name: nullable string, can be null or string
    # To test nullable acceptance, produce either null or string
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10).map(lambda s: s.replace('"', ''))))

    # status: one of the three valid strings, or sometimes an invalid string to test rejection
    # But invalid status is rejected by all four, so no divergence there
    # So produce only valid status strings
    status_val = draw(st.sampled_from(statuses))

    # tags: array of strings, always present (to avoid built_value silent default)
    # But to test divergence, sometimes produce empty list, sometimes list of strings
    # Also test type divergence by sometimes producing a wrong type (e.g. null or string) for tags
    # But wrong type is rejected by all four, no divergence
    # Instead, produce tags as array of strings, sometimes empty, sometimes with strings
    tags_list = draw(st.lists(st.text(min_size=0, max_size=10).map(lambda s: s.replace('"', '')), max_size=5))

    # child: nullable record or null
    # To keep recursion bounded, produce either null or a shallow record with child=null
    # We'll produce child as null or a record with no child (child=null)
    # To test divergence, sometimes produce child with a subtle difference in id or tags or name
    # But keep it simple: child is either null or a record with all fields valid and child=null
    def gen_child():
        # id for child: int in range
        child_id = draw(st.integers(min_value=-2**63, max_value=2**63-1))
        # amount string for child
        child_amount = draw(st.text(min_size=0, max_size=10).map(lambda s: s.replace('"', '')))
        # name nullable string for child
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10).map(lambda s: s.replace('"', ''))))
        # status for child
        child_status = draw(st.sampled_from(statuses))
        # tags for child
        child_tags = draw(st.lists(st.text(min_size=0, max_size=10).map(lambda s: s.replace('"', '')), max_size=3))
        # child child is always null (no deeper recursion)
        # Compose child JSON object string
        child_obj = (
            '{'
            + f'"id":{child_id},'
            + f'"amount":{json_string(child_amount)},'
            + f'"name":{"null" if child_name is None else json_string(child_name)},'
            + f'"status":{json_string(child_status)},'
            + f'"tags":{json_array_of_strings(child_tags)},'
            + f'"child":null'
            + '}'
        )
        return child_obj

    child_val = draw(st.one_of(st.just("null"), st.deferred(gen_child)))

    # Compose id field JSON value respecting the type choice
    if id_choice[0] == "int":
        id_json = str(id_choice[1])
    else:
        # double: produce JSON number with decimal point or exponent to ensure double
        f = id_choice[1]
        # Format float with decimal or exponent, avoid scientific notation that looks like int
        # Use repr to get full precision
        id_json = repr(f)
        # Ensure decimal point or exponent present
        if 'e' not in id_json and '.' not in id_json:
            id_json += ".0"

    # Compose full JSON object string
    # All six fields always present
    # name and child nullable
    # tags always present (never missing)
    # amount string always present
    # status always present and valid string
    # id as int or double per above
    json_obj = (
        '{'
        + f'"id":{id_json},'
        + f'"amount":{json_string(amount_str)},'
        + f'"name":{"null" if name_val is None else json_string(name_val)},'
        + f'"status":{json_string(status_val)},'
        + f'"tags":{json_array_of_strings(tags_list)},'
        + f'"child":{child_val}'
        + '}'
    )

    return json_obj.encode("utf-8")