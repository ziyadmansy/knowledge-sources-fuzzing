from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (escape quotes and backslashes)
    def json_string(s: str) -> str:
        # Minimal escaping for JSON string: backslash and double quote
        # Also escape control chars \b, \f, \n, \r, \t for safety
        esc_map = {
            '\\': '\\\\',
            '"': '\\"',
            '\b': '\\b',
            '\f': '\\f',
            '\n': '\\n',
            '\r': '\\r',
            '\t': '\\t',
        }
        return '"' + ''.join(esc_map.get(c, c) for c in s) + '"'

    # id: integer, always present, test boundary values and some invalid types (null rejected by all)
    # We'll mostly produce valid int, but sometimes a stringified int (should be rejected)
    # or a float (should be rejected)
    id_int = st.integers(min_value=-(2**31), max_value=2**31-1)
    id_wrong_type = st.one_of(
        st.floats(allow_nan=False, allow_infinity=False).filter(lambda x: x != int(x)),
        st.text(min_size=1).filter(lambda s: not s.isdigit()),
        st.just(None),
        st.booleans(),
    )
    # 90% valid int, 10% wrong type to provoke divergence
    id_field = st.one_of(id_int.map(str), id_wrong_type.map(lambda v: "null" if v is None else json_string(str(v)))).filter(lambda s: s != '')

    # amount: string, always present, never null
    # We'll produce valid strings, empty string, and sometimes a number (should be rejected)
    amount_valid = st.text(min_size=0, max_size=10).map(json_string)
    amount_wrong_type = st.one_of(
        st.integers().map(str),
        st.floats(allow_nan=False, allow_infinity=False).map(str),
        st.just("null"),
        st.booleans().map(lambda b: "true" if b else "false"),
    )
    amount_field = st.one_of(amount_valid, amount_wrong_type)

    # name: string or null, always present
    # We'll produce null or string (including empty)
    name_field = st.one_of(st.none().map(lambda _: "null"), st.text(min_size=0, max_size=10).map(json_string))

    # status: enum string, always present, must be exactly one of STATUS_VALUES
    # We'll produce valid enum values, and sometimes invalid casing or unknown strings (should be rejected by all)
    status_valid = st.sampled_from(STATUS_VALUES).map(json_string)
    status_invalid = st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: s.lower() not in STATUS_VALUES),
        st.sampled_from(STATUS_VALUES).map(lambda s: json_string(s.upper())),
        st.just("null"),
    )
    # 90% valid, 10% invalid to provoke rejection but no divergence expected here
    status_field = st.one_of(status_valid, status_invalid)

    # tags: array of strings, always present (but built_value accepts null tags as empty array)
    # We'll produce:
    # - valid array of strings (including empty array)
    # - null (only built_value accepts)
    # - wrong types (number, string, bool) to provoke rejection
    # Strings inside tags: simple ascii strings, empty allowed
    tag_string = st.text(min_size=0, max_size=5).map(json_string)
    tags_array = st.lists(tag_string, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_null = st.just("null")
    tags_wrong = st.one_of(
        st.integers().map(str),
        st.floats(allow_nan=False, allow_infinity=False).map(str),
        st.text(min_size=1).map(json_string),
        st.booleans().map(lambda b: "true" if b else "false"),
    )
    # 80% valid array, 10% null, 10% wrong type
    tags_field = st.one_of(tags_array, tags_null, tags_wrong)

    # child: either null or a nested record (one level recursion only)
    # To avoid infinite recursion, child record will have child=null always
    # We'll produce:
    # - null
    # - nested record with all fields valid except possibly one small divergence (e.g. tags null)
    # - nested record with one field wrong type to provoke divergence
    # We reuse the same strategy for nested record but with child=null always
    # To avoid infinite recursion, define a helper for nested record with child=null

    @st.composite
    def nested_record(draw):
        # id int only (no wrong type to keep nested mostly valid)
        nid = draw(id_int).map(str) if hasattr(id_int, "map") else str(draw(id_int))
        # amount string only valid
        namount = draw(st.text(min_size=0, max_size=10)).map(json_string) if hasattr(st.text(min_size=0, max_size=10), "map") else json_string(draw(st.text(min_size=0, max_size=10)))
        # name string or null
        nname = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10))).map(lambda v: "null" if v is None else json_string(v))
        # status valid only
        nstatus = draw(st.sampled_from(STATUS_VALUES)).map(json_string)
        # tags: valid array or null (to provoke divergence)
        ntags = draw(st.one_of(tags_array, tags_null))
        # child always null
        nchild = "null"
        # Compose JSON object string
        obj = (
            '{'
            f'"id":{nid},'
            f'"amount":{namount},'
            f'"name":{nname},'
            f'"status":{nstatus},'
            f'"tags":{ntags},'
            f'"child":{nchild}'
            '}'
        )
        return obj

    # child_field: 70% null, 30% nested record
    child_field = st.one_of(st.just("null"), nested_record())

    # Compose top-level JSON object string with all fields
    # We draw each field as a JSON fragment string (including quotes/brackets as needed)
    id_val = draw(id_field)
    amount_val = draw(amount_field)
    name_val = draw(name_field)
    status_val = draw(status_field)
    tags_val = draw(tags_field)
    child_val = draw(child_field)

    # Compose JSON object string
    json_obj = (
        '{'
        f'"id":{id_val},'
        f'"amount":{amount_val},'
        f'"name":{name_val},'
        f'"status":{status_val},'
        f'"tags":{tags_val},'
        f'"child":{child_val}'
        '}'
    )

    # Return bytes
    return json_obj.encode("utf-8")