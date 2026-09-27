from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper to produce a JSON string literal from a Python string
    def json_string(s: str) -> str:
        # Escape backslash and double quote, and control chars minimally
        # For simplicity, only escape backslash and double quote here
        esc = s.replace('\\', '\\\\').replace('"', '\\"')
        return '"' + esc + '"'

    # Helper to produce JSON array of strings
    def json_array_of_strings(lst):
        return '[' + ','.join(json_string(e) for e in lst) + ']'

    # Helper to produce JSON null or nested record string
    # Use bounded recursion depth to avoid infinite recursion
    def json_record(depth: int) -> st.SearchStrategy[str]:
        if depth <= 0:
            # At max depth, child must be null
            child_strat = st.just("null")
        else:
            child_strat = json_record(depth - 1).map(lambda s: s)

        # id field:
        # Manual requires int exactly
        # json_serializable/freezed accept any num (int or float) and convert via toInt()
        # built_value expects int and likely rejects non-int
        # To maximize divergence, produce either int or float for id
        id_val = draw(st.one_of(
            st.integers(min_value=-2**31, max_value=2**31-1),
            st.floats(allow_infinity=False, allow_nan=False, width=32).filter(lambda f: f.is_integer())
        ))
        # id JSON: if int, emit as integer; if float, emit as float with .0
        if isinstance(id_val, int):
            id_json = str(id_val)
        else:
            # float with .0 suffix, e.g. 42.0
            id_json = str(float(id_val))

        # amount field: all require string exactly
        # To maximize divergence, produce string normally
        amount_val = draw(st.text(min_size=0, max_size=10))
        amount_json = json_string(amount_val)

        # name field: nullable string
        # To maximize divergence, produce either null or string
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        name_json = "null" if name_val is None else json_string(name_val)

        # status field: enum string, known values: "active", "inactive", "unknown"
        # Manual and built_value throw raw ArgumentError on unknown strings (undocumented)
        # json_serializable/freezed throw documented CheckedFromJsonException
        # To maximize divergence, produce either known enum or unknown string
        # Also produce known enum normally
        known_statuses = ["active", "inactive", "unknown"]
        # Also produce unknown strings that look like enum but are not exact
        # e.g. "Active" (capitalized), "inactive " (trailing space), "unknown1"
        # or totally unrelated strings
        unknown_statuses = ["Active", "inactive ", "unknown1", "pending", ""]

        status_val = draw(st.one_of(
            st.sampled_from(known_statuses),
            st.sampled_from(unknown_statuses)
        ))
        status_json = json_string(status_val)

        # tags field: array of strings
        # Manual casts to List then maps elements as String
        # json_serializable/freezed cast to List<dynamic> then map to String
        # built_value expects BuiltList<String> and rejects non-list or lists with non-string elements
        # To maximize divergence, produce either:
        # - empty list
        # - list of strings
        # - list with one non-string element (e.g. int)
        # - list with one null element
        # - list with one float element
        # - list with one boolean element
        # This can cause built_value to reject but others accept or fail differently
        tag_elem_str = st.text(min_size=0, max_size=5)
        tag_elem_non_str = st.one_of(
            st.integers(min_value=-10, max_value=10),
            st.floats(allow_infinity=False, allow_nan=False),
            st.none(),
            st.booleans()
        )
        tags_val = draw(st.one_of(
            st.lists(tag_elem_str, max_size=3),
            st.lists(tag_elem_non_str, min_size=1, max_size=1),
            st.just([]),
        ))
        # Serialize tags_val as JSON array
        def serialize_tag_elem(e):
            if e is None:
                return "null"
            elif isinstance(e, str):
                return json_string(e)
            elif isinstance(e, bool):
                return "true" if e else "false"
            elif isinstance(e, int):
                return str(e)
            elif isinstance(e, float):
                # Use repr to get decimal form
                return repr(e)
            else:
                # fallback to string
                return json_string(str(e))
        tags_json = '[' + ','.join(serialize_tag_elem(e) for e in tags_val) + ']'

        # child field: null or nested record
        child_val = draw(st.one_of(
            st.just("null"),
            json_record(depth - 1)
        ))
        child_json = child_val

        # Compose full JSON object string
        # Fields order fixed as per schema
        json_obj = (
            '{'
            + '"id":' + id_json + ','
            + '"amount":' + amount_json + ','
            + '"name":' + name_json + ','
            + '"status":' + status_json + ','
            + '"tags":' + tags_json + ','
            + '"child":' + child_json +
            '}'
        )
        return json_obj

    # Start recursion with depth 1 (one level of child)
    json_text = draw(json_record(1))
    return json_text.encode('utf-8')