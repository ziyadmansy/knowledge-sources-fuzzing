from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings
def json_array_of_strings(strings):
    return '[' + ','.join(json_string(s) for s in strings) + ']'

# Helper: JSON enum for status, with option to produce invalid variants for divergence
status_values = ["active", "inactive", "unknown"]

@st.composite
def generated_json(draw) -> bytes:
    # We produce a JSON text string for the record, then encode as bytes at the end.

    # Strategy for "id": integer or null (to trigger divergence #4)
    # id normally integer, but can be null (Gson/Jackson accept as zero, others reject)
    id_val = draw(st.one_of(st.integers(min_value=0, max_value=10**9), st.just(None)))

    # Strategy for "amount": string normally, but can be number (to trigger #3)
    # Also can be null (to trigger #2)
    amount_val = draw(
        st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)),
            st.integers(min_value=0, max_value=1000),
            st.just(None),
        )
    )

    # Strategy for "name": string or null, but also can be missing (to trigger #1)
    # We do not omit fields here, but we can set null or string
    name_val = draw(st.one_of(st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)), st.just(None)))

    # Strategy for "status": enum normally, but also invalid variants (case variants, unknown) (to trigger #5)
    status_val = draw(
        st.one_of(
            st.sampled_from(status_values),
            # invalid enum variants: unknown string, case variants, null
            st.just("Active"),  # case variant
            st.just("invalid_status"),
            st.just(None),
        )
    )

    # Strategy for "tags": array of strings normally, but can be null (to trigger #9)
    # Also can be empty array
    tags_val = draw(
        st.one_of(
            st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)), max_size=3),
            st.just(None),
        )
    )

    # Strategy for "child": null or nested record (one level only)
    # To keep recursion bounded, child is either null or a record with no child (child=null)
    # We reuse the same strategies but force child=null in nested to avoid deep recursion
    # Also can test missing or null fields in child to trigger #8
    # We pick a "child" record with simpler constraints to keep size small

    # Nested child fields:
    child_id = draw(st.one_of(st.integers(min_value=0, max_value=10**9), st.just(None)))
    child_amount = draw(
        st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)),
            st.integers(min_value=0, max_value=1000),
            st.just(None),
        )
    )
    child_name = draw(st.one_of(st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)), st.just(None)))
    child_status = draw(st.sampled_from(status_values))
    child_tags = draw(st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)), max_size=3))
    child_child = None  # no recursion beyond one level

    # Compose child JSON text
    # We do not omit fields in child, but allow nulls to trigger #8
    child_json = (
        '{'
        + '"id":'
        + (str(child_id) if child_id is not None else 'null')
        + ',"amount":'
        + (
            (json_string(child_amount) if isinstance(child_amount, str) else str(child_amount))
            if child_amount is not None
            else 'null'
        )
        + ',"name":'
        + (json_string(child_name) if child_name is not None else 'null')
        + ',"status":'
        + json_string(child_status)
        + ',"tags":'
        + json_array_of_strings(child_tags)
        + ',"child":null'
        + '}'
    )

    # Compose top-level JSON text
    # We do not omit fields at top-level (to avoid #1 rejection by Moshi/kotlinx)
    # But we vary nulls, wrong types, etc.

    # id
    id_json = str(id_val) if id_val is not None else 'null'

    # amount
    if amount_val is None:
        amount_json = 'null'
    elif isinstance(amount_val, int):
        amount_json = str(amount_val)
    else:
        amount_json = json_string(amount_val)

    # name
    name_json = json_string(name_val) if name_val is not None else 'null'

    # status
    if status_val is None:
        status_json = 'null'
    else:
        status_json = json_string(status_val)

    # tags
    if tags_val is None:
        tags_json = 'null'
    else:
        tags_json = json_array_of_strings(tags_val)

    # child
    # We randomly choose null or the nested child_json
    child_json_val = draw(st.one_of(st.just('null'), st.just(child_json)))

    json_text = (
        '{'
        + '"id":' + id_json
        + ',"amount":' + amount_json
        + ',"name":' + name_json
        + ',"status":' + status_json
        + ',"tags":' + tags_json
        + ',"child":' + child_json_val
        + '}'
    )

    return json_text.encode('utf-8')