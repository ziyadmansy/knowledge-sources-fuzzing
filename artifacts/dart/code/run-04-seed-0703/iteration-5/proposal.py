from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    valid_statuses = ["active", "inactive", "unknown"]
    # To provoke enum decoding differences, allow also invalid enum strings
    enum_strings = valid_statuses + ["Active", "INACTIVE", "unknown ", "invalid", ""]

    # Recursive limit: max depth 1 for child (one level of recursion)
    # We'll generate a record as a JSON object string, carefully controlling types

    # Helper to produce a JSON string literal from a Python string (no escapes needed for this task)
    def json_str(s: str) -> str:
        # Minimal escaping for quotes and backslashes
        esc = s.replace('\\', '\\\\').replace('"', '\\"')
        return '"' + esc + '"'

    # Helper to produce JSON array of strings
    def json_array_of_strings(lst):
        return "[" + ",".join(json_str(s) for s in lst) + "]"

    # Strategy for "id" field:
    # Manual requires int exactly (json['id'] as int)
    # json_serializable/freezed accept any num and convert via toInt()
    # built_value expects int and likely rejects non-int types
    # So to provoke divergence:
    # - sometimes produce int (all accept)
    # - sometimes produce float with integral value (e.g. 1.0) (json_serializable/freezed accept, manual and built_value reject)
    # - sometimes produce float non-integral (all reject, no divergence)
    id_int = st.integers(min_value=0, max_value=10)
    id_float_integral = st.floats(min_value=0, max_value=10, allow_infinity=False, allow_nan=False).filter(lambda f: f.is_integer())
    # We'll bias towards int and float integral to provoke divergence
    id_choice = st.one_of(id_int, id_float_integral)

    # Strategy for "amount": all require string exactly
    # We'll produce always string to avoid trivial rejection by all
    amount_str = st.text(min_size=1, max_size=10)

    # Strategy for "name": string or null
    name_str_or_null = st.one_of(st.none(), st.text(min_size=0, max_size=10))

    # Strategy for "status": string, mostly valid enum strings, sometimes invalid variants to provoke divergence
    status_str = st.one_of(
        st.sampled_from(valid_statuses).map(lambda s: s),  # valid exact
        st.sampled_from(enum_strings).filter(lambda s: s not in valid_statuses)  # invalid variants
    )

    # Strategy for "tags": array of strings
    # To provoke divergence, sometimes produce list with non-string elements (manual and json_serializable/freezed reject, built_value rejects)
    # But to provoke divergence, produce sometimes list of strings, sometimes list with one int element
    tags_strings = st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=3)
    tags_mixed = st.lists(st.one_of(st.text(min_size=0, max_size=5), st.integers(min_value=0, max_value=10)), min_size=0, max_size=3)
    tags_choice = st.one_of(tags_strings, tags_mixed)

    # Forward declaration for child record (one level recursion)
    # We'll produce either null or a nested record (no deeper nesting)
    # To avoid infinite recursion, child record will not have child itself (child=null)
    @st.composite
    def child_record(draw):
        # id for child: only int (to reduce complexity)
        cid = draw(id_int)
        camount = draw(amount_str)
        cname = draw(name_str_or_null)
        cstatus = draw(st.sampled_from(valid_statuses))  # child status always valid to reduce noise
        ctags = draw(tags_strings)  # child tags always strings to reduce noise
        cchild = "null"  # no deeper recursion

        # Compose JSON object string for child
        child_json = (
            '{'
            + f'"id":{cid},'
            + f'"amount":{json_str(camount)},'
            + f'"name":{json_str(cname) if cname is not None else "null"},'
            + f'"status":{json_str(cstatus)},'
            + f'"tags":{json_array_of_strings(ctags)},'
            + f'"child":{cchild}'
            + '}'
        )
        return child_json

    # Now draw all fields for top-level record
    id_val = draw(id_choice)
    amount_val = draw(amount_str)
    name_val = draw(name_str_or_null)
    status_val = draw(status_str)
    tags_val = draw(tags_choice)
    child_present = draw(st.booleans())

    # Compose child JSON or null
    if child_present:
        child_val = draw(child_record())
    else:
        child_val = "null"

    # Compose tags JSON array string
    # tags_val may contain ints, so produce JSON accordingly
    def json_value(v):
        if v is None:
            return "null"
        elif isinstance(v, str):
            return json_str(v)
        elif isinstance(v, int):
            return str(v)
        else:
            # fallback, treat as string
            return json_str(str(v))

    tags_json = "[" + ",".join(json_value(t) for t in tags_val) + "]"

    # Compose id JSON value: int or float
    if isinstance(id_val, int):
        id_json = str(id_val)
    else:
        # float integral, output as JSON number with decimal point
        id_json = format(id_val, '.1f')

    # Compose status JSON string (always string)
    status_json = json_str(status_val)

    # Compose name JSON string or null
    if name_val is None:
        name_json = "null"
    else:
        name_json = json_str(name_val)

    # Compose amount JSON string
    amount_json = json_str(amount_val)

    # Compose final JSON object string
    json_obj = (
        '{'
        + f'"id":{id_json},'
        + f'"amount":{amount_json},'
        + f'"name":{name_json},'
        + f'"status":{status_json},'
        + f'"tags":{tags_json},'
        + f'"child":{child_val}'
        + '}'
    )

    # Return bytes
    return json_obj.encode("utf-8")