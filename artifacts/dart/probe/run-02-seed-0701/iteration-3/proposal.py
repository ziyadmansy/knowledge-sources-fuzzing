from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]
    MAX_RECURSION_DEPTH = 1

    # Helper to produce a JSON string literal with proper escaping for " and \
    def json_string_literal(s: str) -> str:
        # Minimal escaping for " and \ only, enough for valid JSON strings
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Strategy for "id" field: normally integer, but allow off-by-one type errors
    # to induce divergence: integer or stringified integer (Probe 2 showed string id rejected)
    # But since all reject string id, we won't do string id here.
    # Instead, keep id always int to keep document almost well-formed.
    id_strategy = st.integers(min_value=0, max_value=10**9)

    # Strategy for "amount" field: string normally, but also try number (Probe 3 shows number rejected)
    # To maximize divergence, mostly string, occasionally number (as JSON number)
    amount_strategy = st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '"\\')),  # safe string
        st.integers(min_value=0, max_value=10**6).map(str),  # stringified int as string
        st.integers(min_value=0, max_value=10**6),  # number (should cause rejection)
    )

    # Strategy for "name": nullable string, but also try number (Probe 4 shows number rejected)
    # Also try null
    name_strategy = st.one_of(
        st.none(),
        st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in '"\\')),
        st.integers(min_value=0, max_value=1000),  # number to cause rejection
    )

    # Strategy for "status": enum string, plus invalid strings to cause rejection
    status_strategy = st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES),
    )

    # Strategy for "tags": array of strings normally, but also null (Probe 17 shows built_value accepts null tags)
    # Also try array with non-string elements (Probe 7 shows rejection)
    # To maximize divergence, mostly array of strings, sometimes null, sometimes array with one int element
    tags_strategy = st.one_of(
        st.lists(st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '"\\')), min_size=0, max_size=5),
        st.none(),
        st.lists(st.one_of(st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '"\\')), st.integers()), min_size=0, max_size=5),
    )

    # Recursive strategy for "child" field: nullable Record or null
    # To avoid infinite recursion, limit depth to 1
    # Also allow "child" to be null or missing (but missing is rejected by all)
    # We want to vary child to cause divergence on nested fields
    def record_strategy(depth=0):
        if depth > MAX_RECURSION_DEPTH:
            # At max depth, child must be null or omitted (omit not allowed, so null)
            return st.just(None)
        else:
            # Compose record fields with some chance of type errors on nested fields
            # For nested "id" field, always int (Probe 9 shows string id rejected)
            nested_id = id_strategy
            nested_amount = amount_strategy
            nested_name = name_strategy
            nested_status = status_strategy
            nested_tags = tags_strategy
            nested_child = st.one_of(st.none(), record_strategy(depth + 1))

            # Build JSON object text for nested record
            @st.composite
            def nested_record(draw):
                nid = draw(nested_id)
                namt = draw(nested_amount)
                nname = draw(nested_name)
                nstatus = draw(nested_status)
                ntags = draw(nested_tags)
                nchild = draw(nested_child)

                # Serialize fields to JSON text
                # id: int only
                id_text = str(nid)

                # amount: string or number
                if isinstance(namt, int):
                    amount_text = str(namt)
                else:
                    amount_text = json_string_literal(namt)

                # name: null, string, or number
                if nname is None:
                    name_text = "null"
                elif isinstance(nname, int):
                    name_text = str(nname)
                else:
                    name_text = json_string_literal(nname)

                # status: string enum or invalid string
                status_text = json_string_literal(nstatus)

                # tags: null or array
                if ntags is None:
                    tags_text = "null"
                else:
                    # ntags is list of strings or mixed
                    elems = []
                    for e in ntags:
                        if isinstance(e, int):
                            elems.append(str(e))
                        else:
                            elems.append(json_string_literal(e))
                    tags_text = "[" + ",".join(elems) + "]"

                # child: null or nested record
                if nchild is None:
                    child_text = "null"
                else:
                    child_text = nchild

                # Compose JSON object text for nested record
                # Use fixed field order for consistency
                obj_text = (
                    '{'
                    + '"id":' + id_text + ','
                    + '"amount":' + amount_text + ','
                    + '"name":' + name_text + ','
                    + '"status":' + status_text + ','
                    + '"tags":' + tags_text + ','
                    + '"child":' + child_text
                    + '}'
                )
                return obj_text

            return nested_record()

    # Compose top-level record fields with controlled variation
    id_val = draw(id_strategy)

    amount_val = draw(amount_strategy)
    if isinstance(amount_val, int):
        amount_text = str(amount_val)
    else:
        amount_text = json_string_literal(amount_val)

    name_val = draw(name_strategy)
    if name_val is None:
        name_text = "null"
    elif isinstance(name_val, int):
        name_text = str(name_val)
    else:
        name_text = json_string_literal(name_val)

    status_val = draw(status_strategy)
    status_text = json_string_literal(status_val)

    tags_val = draw(tags_strategy)
    if tags_val is None:
        tags_text = "null"
    else:
        elems = []
        for e in tags_val:
            if isinstance(e, int):
                elems.append(str(e))
            else:
                elems.append(json_string_literal(e))
        tags_text = "[" + ",".join(elems) + "]"

    child_val = draw(st.one_of(st.none(), record_strategy(0)))
    if child_val is None:
        child_text = "null"
    else:
        child_text = child_val

    # Compose JSON object text for top-level record
    # Fixed field order for consistency
    json_text = (
        '{'
        + '"id":' + str(id_val) + ','
        + '"amount":' + amount_text + ','
        + '"name":' + name_text + ','
        + '"status":' + status_text + ','
        + '"tags":' + tags_text + ','
        + '"child":' + child_text
        + '}'
    )

    return json_text.encode("utf-8")