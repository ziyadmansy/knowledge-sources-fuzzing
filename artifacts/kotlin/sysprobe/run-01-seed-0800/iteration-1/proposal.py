from hypothesis import strategies as st

# Helper: JSON string escaping for simple strings (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only, keep others as-is for simplicity
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text bytes for the record schema, crafted to provoke
    behavioral divergence among Gson, Moshi, kotlinx.serialization, and Jackson.

    Strategy:
    - Generate a mostly valid record, then vary exactly one or two fields subtly:
      * missing required fields (id, amount, status, tags, child)
      * null in non-nullable fields (id, amount, status, tags)
      * unknown enum values for status
      * amount as number or string or null
      * name as string or null
      * child: present or missing or null, with one-level recursion
      * child.child: empty object or missing or null
      * tags: empty array or array of strings
    - Limit recursion depth to 1 for child.
    - Compose JSON text manually with string concatenation.
    """

    # Constants
    STATUS_ENUM = ["active", "inactive", "unknown"]
    STATUS_UNKNOWN = ["Active", "invalid", ""]  # invalid enum values to test enum rejection

    # Recursion depth control
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # Base fields with normal values
        # id: integer >=0
        id_val = st.integers(min_value=0, max_value=1000)
        # amount: string normally, but can be number or null to provoke divergence
        amount_str = st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '"\\'))  # simple safe string
        amount_num = st.integers(min_value=0, max_value=100000)
        amount_choice = st.one_of(
            amount_str.map(json_string),  # string
            amount_num.map(str),          # number as string
            st.just("null")               # null
        )
        # name: nullable string or null
        name_str = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in '"\\')).map(json_string)
        )
        # status: valid enum or invalid enum or null (null invalid for non-nullable)
        status_val = st.one_of(
            st.sampled_from(STATUS_ENUM).map(json_string),
            st.sampled_from(STATUS_UNKNOWN).map(json_string),
            st.just("null")
        )
        # tags: array of strings (empty or non-empty), or null
        tag_str = st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '"\\'))
        tags_arr = st.lists(tag_str, min_size=0, max_size=3).map(
            lambda lst: "[" + ",".join(json_string(s) for s in lst) + "]"
        )
        tags_choice = st.one_of(
            tags_arr,
            st.just("null")
        )
        # child: null, missing, or nested record (depth limited)
        # To provoke divergence:
        # Gson accepts missing child as null, Moshi and kotlinx reject missing child,
        # Jackson accepts missing child.
        # So sometimes omit child field.
        # Also child can be null or a nested record.
        if depth >= 1:
            # At depth 1, do not recurse further, just null or empty object or missing
            child_field = st.one_of(
                st.just(None),  # missing
                st.just("null"),
                st.just("{}"),  # empty object (all fields missing)
            )
        else:
            # depth 0: child can be missing, null, or nested record at depth+1
            nested = record_json(depth + 1)
            child_field = st.one_of(
                st.just(None),  # missing
                st.just("null"),
                nested
            )

        # id field: sometimes missing, sometimes null (Gson accepts null for non-nullable id?), or integer
        # From known: Gson accepts missing id → 0, null for non-nullable fields? (not stated explicitly for id)
        # Let's test null for id too.
        id_field = st.one_of(
            st.just(None),  # missing
            st.just("null"),
            id_val.map(str)
        )

        # Compose fields with controlled presence and values
        # We will generate a dict of fieldname -> JSON text or None (missing)
        def build_fields(id_v, amount_v, name_v, status_v, tags_v, child_v):
            fields = []
            if id_v is not None:
                fields.append('"id":' + id_v)
            if amount_v is not None:
                fields.append('"amount":' + amount_v)
            if name_v is not None:
                fields.append('"name":' + name_v)
            if status_v is not None:
                fields.append('"status":' + status_v)
            if tags_v is not None:
                fields.append('"tags":' + tags_v)
            if child_v is not None:
                fields.append('"child":' + child_v)
            return "{" + ",".join(fields) + "}"

        # Draw all fields
        id_v = draw(id_field)
        amount_v = draw(amount_choice)
        name_v = draw(name_str)
        status_v = draw(status_val)
        tags_v = draw(tags_choice)
        child_v = draw(child_field)

        # Build JSON text
        json_text = build_fields(id_v, amount_v, name_v, status_v, tags_v, child_v)
        return json_text

    # Generate top-level record JSON text
    json_text = draw(record_json(0))

    # Return as bytes
    return json_text.encode("utf-8")