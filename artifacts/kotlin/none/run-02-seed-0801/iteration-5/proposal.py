from hypothesis import strategies as st

# Helper: produce a JSON string literal from a Python string, escaping as needed.
# We cannot import json or use eval, so implement minimal escaping for JSON strings.
def json_string_literal(s: str) -> str:
    # Escape backslash, double quote, and control chars minimally.
    # Control chars: \b, \f, \n, \r, \t
    # We'll replace these with their escape sequences.
    # Other control chars (0x00-0x1F) are rare and not handled specially here.
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\b', '\\b')
    s = s.replace('\f', '\\f')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return '"' + s + '"'

# Strategy for JSON string literal text
json_string = st.text(min_size=0, max_size=20).map(json_string_literal)

# Strategy for JSON string or null (for "name")
json_string_or_null = st.one_of(
    st.just("null"),
    json_string,
)

# Strategy for "status" field: one of three strings, but sometimes inject wrong types or wrong strings
# to induce divergence.
# We'll produce mostly valid strings, but sometimes a wrong string or a number or null.
def status_strategy():
    valid = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
    # Introduce some invalid variants to cause divergence:
    invalid_string = st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string_literal)
    invalid_type = st.one_of(
        st.integers(min_value=0, max_value=10).map(str),
        st.just("null"),
        st.just("true"),
        st.just("false"),
        st.just("[]"),
        st.just("{}"),
    )
    # Weighted choice: mostly valid, sometimes invalid string, rarely invalid type
    return st.one_of(
        valid,
        invalid_string,
        invalid_type,
    )

# Strategy for "amount": string, but sometimes inject number or null or boolean as string or raw
# to cause divergence.
def amount_strategy():
    # valid amount strings: decimal numbers as strings, or arbitrary strings
    valid_amount = st.one_of(
        # numeric strings
        st.floats(allow_nan=False, allow_infinity=False, width=32).map(lambda f: json_string_literal(str(f))),
        # arbitrary strings
        st.text(min_size=0, max_size=10).map(json_string_literal),
    )
    # invalid types: number (not string), null, boolean, empty array, object
    invalid_types = st.one_of(
        st.integers(min_value=-1000, max_value=1000).map(str),
        st.floats(allow_nan=False, allow_infinity=False, width=32).map(str),
        st.just("null"),
        st.just("true"),
        st.just("false"),
        st.just("[]"),
        st.just("{}"),
    )
    # weighted: mostly valid, sometimes invalid
    return st.one_of(
        valid_amount,
        invalid_types,
    )

# Strategy for "id": integer, but sometimes inject string or float or null or boolean
def id_strategy():
    valid = st.integers(min_value=0, max_value=2**31-1).map(str)
    invalid = st.one_of(
        st.floats(allow_nan=False, allow_infinity=False, width=32).map(str),
        json_string,
        st.just("null"),
        st.just("true"),
        st.just("false"),
        st.just("[]"),
        st.just("{}"),
    )
    return st.one_of(
        valid,
        invalid,
    )

# Strategy for "tags": array of strings, but sometimes inject null, or array with non-string elements,
# or empty array, or missing (but missing is not allowed by schema, so skip missing)
def tags_strategy():
    # valid: array of 0-3 strings
    valid = st.lists(st.text(min_size=0, max_size=10).map(json_string_literal), min_size=0, max_size=3).map(
        lambda lst: "[" + ",".join(lst) + "]"
    )
    # invalid: null, array with non-string elements, empty object, boolean
    invalid = st.one_of(
        st.just("null"),
        # array with mixed types: string and number or boolean
        st.lists(st.one_of(
            st.text(min_size=0, max_size=10).map(json_string_literal),
            st.integers(min_value=0, max_value=10).map(str),
            st.just("true"),
            st.just("false"),
            st.just("null"),
        ), min_size=1, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]"),
        st.just("{}"),
        st.just("true"),
        st.just("false"),
    )
    return st.one_of(
        valid,
        invalid,
    )

# Recursive strategy for "child" field: either null or a nested record (one level only)
# To avoid deep recursion, only one level of child allowed.
# We'll produce either "null" or a nested record with no child (child=null).
def child_strategy():
    # child record with child=null (no further recursion)
    def child_record():
        # reuse all fields except child fixed to null
        return st.builds(
            lambda id_, amount, name, status, tags: (
                '{'
                + '"id":' + id_ + ','
                + '"amount":' + amount + ','
                + '"name":' + name + ','
                + '"status":' + status + ','
                + '"tags":' + tags + ','
                + '"child":null'
                + '}'
            ),
            id_strategy(),
            amount_strategy(),
            json_string_or_null,
            status_strategy(),
            tags_strategy(),
        )
    return st.one_of(
        st.just("null"),
        child_record(),
    )

@st.composite
def generated_json(draw) -> bytes:
    # Compose the top-level record as JSON text
    id_ = draw(id_strategy())
    amount = draw(amount_strategy())
    name = draw(json_string_or_null)
    status = draw(status_strategy())
    tags = draw(tags_strategy())
    child = draw(child_strategy())

    # Compose JSON text for the record
    json_text = (
        '{'
        + '"id":' + id_ + ','
        + '"amount":' + amount + ','
        + '"name":' + name + ','
        + '"status":' + status + ','
        + '"tags":' + tags + ','
        + '"child":' + child
        + '}'
    )
    return json_text.encode("utf-8")