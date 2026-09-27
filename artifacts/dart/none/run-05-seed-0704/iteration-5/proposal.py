from hypothesis import strategies as st

# Constants for the enum 'status'
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce a JSON string literal with quotes escaped properly
def json_string_literal(s: str) -> str:
    # Escape backslash and double quotes minimally for JSON string literal
    # Hypothesis strings can contain any unicode, but we keep it simple here
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects matching the record schema,
    but with one or two subtle deviations to provoke divergence among four Dart JSON deserializers.
    """

    # Recursive depth limit: only one level of recursion for "child"
    # We'll generate the child record or null

    # Base record fields:
    # "id": integer (normally)
    # "amount": string (normally)
    # "name": string or null
    # "status": one of "active", "inactive", "unknown"
    # "tags": array of strings
    # "child": record or null (one level recursion)

    # Strategy to produce a valid integer or a subtle deviation (e.g. float, string number)
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),  # valid integer as string
        st.floats(allow_infinity=False, allow_nan=False).map(lambda f: repr(f)),  # float as number string
        st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()).map(json_string_literal),  # string instead of int
    )

    # Strategy to produce amount field as string normally, or subtle deviation:
    # - valid string number
    # - number (int or float) instead of string
    # - empty string
    # - string with whitespace
    amount_strategy = st.one_of(
        st.text(min_size=1, max_size=10).map(json_string_literal),  # normal string
        st.integers(min_value=0, max_value=1000000).map(str),  # number instead of string
        st.floats(allow_infinity=False, allow_nan=False).map(lambda f: repr(f)),  # float number instead of string
        st.just('""'),  # empty string
        st.just('"   "'),  # whitespace string
    )

    # name: string or null normally
    # subtle deviations:
    # - number instead of string or null
    # - boolean instead of string or null
    # - empty string
    # - string with unicode or escape chars
    name_strategy = st.one_of(
        st.none().map(lambda _: 'null'),
        st.text(min_size=0, max_size=10).map(json_string_literal),
        st.integers(min_value=0, max_value=1000).map(str),  # number instead of string/null
        st.booleans().map(lambda b: "true" if b else "false"),  # boolean instead of string/null
        st.just('""'),  # empty string
    )

    # status: one of the three strings normally
    # subtle deviations:
    # - string not in enum
    # - null
    # - number
    # - uppercase variants
    status_strategy = st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.text(min_size=1, max_size=10).filter(lambda s: s.lower() not in ['active', 'inactive', 'unknown']).map(json_string_literal),
        st.none().map(lambda _: 'null'),
        st.integers(min_value=0, max_value=10).map(str),
        st.sampled_from(['"ACTIVE"', '"Inactive"', '"UnKnOwN"']),
    )

    # tags: array of strings normally
    # subtle deviations:
    # - array of numbers
    # - array of mixed types
    # - empty array
    # - null instead of array
    # - array with null elements
    # - array with empty strings
    def tags_elements():
        return st.one_of(
            st.text(min_size=1, max_size=5).map(json_string_literal),
            st.integers(min_value=0, max_value=1000).map(str),
            st.none().map(lambda _: 'null'),
            st.just('""'),
        )
    tags_strategy = st.one_of(
        st.lists(tags_elements(), min_size=0, max_size=5).map(lambda lst: '[' + ','.join(lst) + ']'),
        st.none().map(lambda _: 'null'),
    )

    # child: null or one record (one level recursion)
    # We'll produce either null or a record with all fields valid or subtly deviated
    # To avoid infinite recursion, child record will not have child (always null)
    def child_record():
        # child record fields, no further child recursion (child=null)
        child_id = draw(id_strategy)
        child_amount = draw(amount_strategy)
        child_name = draw(name_strategy)
        child_status = draw(status_strategy)
        child_tags = draw(tags_strategy)
        child_child = 'null'  # no further recursion

        return (
            '{'
            f'"id":{child_id},'
            f'"amount":{child_amount},'
            f'"name":{child_name},'
            f'"status":{child_status},'
            f'"tags":{child_tags},'
            f'"child":{child_child}'
            '}'
        )

    # Now draw all fields for the top-level record
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_strategy)
    status_val = draw(status_strategy)
    tags_val = draw(tags_strategy)
    # child: null or record
    child_val = draw(st.one_of(
        st.just('null'),
        st.deferred(child_record)
    ))

    # Compose the JSON object string
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

    return json_obj.encode('utf-8')