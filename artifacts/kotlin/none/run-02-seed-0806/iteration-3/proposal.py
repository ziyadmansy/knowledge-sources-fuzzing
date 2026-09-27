from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Basic JSON string escaper for double quotes and backslash only (minimal)
    def json_str(s: str) -> str:
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # JSON null literal
    null = "null"

    # JSON boolean literals (not used here but could be extended)
    # true = "true"
    # false = "false"

    # Strategy for JSON integer (id)
    id_strat = st.integers(min_value=0, max_value=2**31 - 1).map(str)

    # Strategy for amount: normally string, but we will sometimes produce null or number as string to cause divergence
    # But per schema, amount is string (always present)
    # We'll mostly produce strings, sometimes empty, sometimes numeric strings, sometimes strings with spaces
    amount_strat = st.one_of(
        st.text(min_size=0, max_size=10).filter(lambda s: all(c not in '"\\' for c in s)),  # safe strings without quotes or backslash
        st.integers(min_value=-1000, max_value=1000).map(str),
        st.just("null"),  # literal string "null" (not JSON null)
    ).map(json_str)

    # Strategy for name: string or null
    name_strat = st.one_of(
        st.none().map(lambda _: null),
        st.text(min_size=0, max_size=10).filter(lambda s: all(c not in '"\\' for c in s)).map(json_str),
    )

    # status: one of "active", "inactive", "unknown"
    # We will sometimes produce a wrong type (e.g. number or null) to cause divergence
    status_valid = st.sampled_from(["active", "inactive", "unknown"]).map(json_str)
    status_invalid = st.one_of(
        st.none().map(lambda _: null),
        st.integers(min_value=0, max_value=10).map(str),
        st.text(min_size=1, max_size=10).filter(lambda s: s not in ["active", "inactive", "unknown"]).map(json_str),
    )
    # Mostly valid, sometimes invalid
    status_strat = st.one_of(
        status_valid,
        status_invalid,
    )

    # tags: array of strings (always present)
    # We'll produce arrays of 0 to 3 strings, strings are safe strings without quotes or backslash
    tags_strat = st.lists(
        st.text(min_size=0, max_size=10).filter(lambda s: all(c not in '"\\' for c in s)).map(json_str),
        min_size=0,
        max_size=3,
    ).map(lambda lst: "[" + ",".join(lst) + "]")

    # child: either null or a nested record (one level recursion max)
    # To avoid deep recursion, child can be null or a record with child=null
    # We'll produce child as null or a record with child=null (no deeper)
    # To produce child record, reuse all fields except child is null

    # Define a helper to produce a record JSON string with child=null
    def record_no_child():
        id_val = draw(id_strat)
        amount_val = draw(amount_strat)
        name_val = draw(name_strat)
        status_val = draw(status_strat)
        tags_val = draw(tags_strat)
        # child is null
        return (
            '{'
            + '"id":' + id_val + ','
            + '"amount":' + amount_val + ','
            + '"name":' + name_val + ','
            + '"status":' + status_val + ','
            + '"tags":' + tags_val + ','
            + '"child":null'
            + '}'
        )

    # child_strat: either null or record_no_child
    child_strat = st.one_of(
        st.just(null),
        st.deferred(lambda: st.builds(lambda: record_no_child())),
    )

    # Now build the top-level record with child from child_strat
    id_val = draw(id_strat)
    amount_val = draw(amount_strat)
    name_val = draw(name_strat)
    status_val = draw(status_strat)
    tags_val = draw(tags_strat)
    child_val = draw(child_strat)

    json_text = (
        '{'
        + '"id":' + id_val + ','
        + '"amount":' + amount_val + ','
        + '"name":' + name_val + ','
        + '"status":' + status_val + ','
        + '"tags":' + tags_val + ','
        + '"child":' + child_val
        + '}'
    )

    return json_text.encode("utf-8")