from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars minimally
        # Hypothesis strings are unicode, but we keep it simple:
        esc = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars \b \f \n \r \t for safety
        esc = esc.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{esc}"'

    # Helper: produce a JSON array of strings
    def json_string_array(strs):
        return "[" + ",".join(json_string(s) for s in strs) + "]"

    # Helper: produce JSON for a Record or null
    # We allow one level of recursion only.
    # We produce a dict with all six fields always present.
    # We vary one or two fields to be "almost" correct but slightly off to trigger divergences.
    # We produce syntactically valid JSON always.

    # Strategy for "id" field: normally integer, but sometimes stringified integer or float to cause divergence
    id_base = st.integers(min_value=0, max_value=2**31-1)
    id_variant = st.one_of(
        id_base,
        id_base.map(str),  # string instead of int
        st.floats(min_value=0, max_value=2**9, allow_nan=False, allow_infinity=False).map(lambda f: int(f) if f.is_integer() else f),  # sometimes float
    )

    # Strategy for "amount" field: string normally representing a decimal number, but sometimes a number or null (wrong type)
    amount_base = st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789.-" for c in s))
    amount_variant = st.one_of(
        amount_base,
        st.integers(min_value=-10000, max_value=10000).map(str),
        st.floats(min_value=-10000, max_value=10000, allow_nan=False, allow_infinity=False).map(lambda f: f"{f:.2f}"),
        st.integers(min_value=-10000, max_value=10000),  # number instead of string
    )

    # Strategy for "name" field: string or null, but sometimes number or boolean to cause divergence
    name_base = st.one_of(st.none(), st.text(min_size=0, max_size=20))
    name_variant = st.one_of(
        name_base,
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
    )

    # Strategy for "status" field: one of the three strings, or sometimes a wrong string or null
    status_base = st.sampled_from(statuses)
    status_variant = st.one_of(
        status_base,
        st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses),
        st.none(),
    )

    # Strategy for "tags" field: array of strings, sometimes empty, sometimes with wrong element types
    tags_base = st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5)
    tags_variant = st.one_of(
        tags_base,
        st.lists(st.one_of(st.text(min_size=1, max_size=10), st.integers(), st.booleans()), min_size=0, max_size=5),
    )

    # Recursive child: either null or a record (one level only)
    # We will produce child with a smaller chance to be null or malformed
    # To avoid infinite recursion, child record uses only base fields (no further child)
    def record_json(allow_malformed=True):
        # Compose fields with possible variants
        id_val = draw(id_variant if allow_malformed else id_base)
        amount_val = draw(amount_variant if allow_malformed else amount_base)
        name_val = draw(name_variant if allow_malformed else name_base)
        status_val = draw(status_variant if allow_malformed else status_base)
        tags_val = draw(tags_variant if allow_malformed else tags_base)

        # child: either null or a record without child (to avoid deep recursion)
        child_null = draw(st.booleans())
        if child_null:
            child_json = "null"
        else:
            # child record with allow_malformed=False to limit complexity
            child_id = draw(id_base)
            child_amount = draw(amount_base)
            child_name = draw(name_base)
            child_status = draw(status_base)
            child_tags = draw(tags_base)
            # child.child is always null (no recursion)
            child_json = (
                '{'
                f'"id":{child_id},'
                f'"amount":{json_string(child_amount)},'
                f'"name":{json_string(child_name) if child_name is not None else "null"},'
                f'"status":{json_string(child_status)},'
                f'"tags":{json_string_array(child_tags)},'
                f'"child":null'
                '}'
            )

        # Format fields to JSON text
        # id: if int, output as number; if string, output as JSON string; if float, output as number
        if isinstance(id_val, int):
            id_json = str(id_val)
        elif isinstance(id_val, float):
            # format floats with minimal decimals
            id_json = repr(id_val)
        else:
            id_json = json_string(str(id_val))

        # amount: if string, output as JSON string; if number, output as number
        if isinstance(amount_val, str):
            amount_json = json_string(amount_val)
        elif isinstance(amount_val, (int, float)):
            amount_json = repr(amount_val)
        else:
            # fallback to string
            amount_json = json_string(str(amount_val))

        # name: null or string or number or boolean
        if name_val is None:
            name_json = "null"
        elif isinstance(name_val, str):
            name_json = json_string(name_val)
        elif isinstance(name_val, bool):
            name_json = "true" if name_val else "false"
        else:
            # number
            name_json = repr(name_val)

        # status: null or string
        if status_val is None:
            status_json = "null"
        else:
            status_json = json_string(status_val)

        # tags: array of strings or mixed
        # tags_val is a list, elements may be str/int/bool
        tags_elems = []
        for t in tags_val:
            if isinstance(t, str):
                tags_elems.append(json_string(t))
            elif isinstance(t, bool):
                tags_elems.append("true" if t else "false")
            elif isinstance(t, int):
                tags_elems.append(str(t))
            else:
                # fallback to string
                tags_elems.append(json_string(str(t)))
        tags_json = "[" + ",".join(tags_elems) + "]"

        # Compose full record JSON
        rec = (
            '{'
            f'"id":{id_json},'
            f'"amount":{amount_json},'
            f'"name":{name_json},'
            f'"status":{status_json},'
            f'"tags":{tags_json},'
            f'"child":{child_json}'
            '}'
        )
        return rec

    # Draw the top-level record with allow_malformed=True to maximize divergence chances
    top_json = record_json(allow_malformed=True)

    # Return bytes
    return top_json.encode("utf-8")