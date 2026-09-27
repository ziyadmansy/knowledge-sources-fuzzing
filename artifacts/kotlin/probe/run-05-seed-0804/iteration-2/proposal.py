from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslashes only (minimal)
def json_string_escape(s: str) -> str:
    # Minimal escaping for JSON strings: backslash and double quote
    return s.replace("\\", "\\\\").replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text (bytes) for the described record schema, with subtle
    variations to maximize divergence between Gson, Moshi, kotlinx.serialization,
    and Jackson Kotlin module, based on known behaviors.

    Strategy:
    - Produce mostly well-formed documents with one or two fields subtly off.
    - Use bounded recursion for "child" (max depth 1).
    - Vary "id" as int or string (both accepted).
    - Vary "amount" as string normally, sometimes number (kotlinx rejects number).
    - Vary "name" as string, null, or non-string (number/boolean) (kotlinx rejects non-string).
    - Vary "status" as valid enum string, invalid string, or null (Gson accepts null/invalid as null, others reject).
    - Vary "tags" as array of strings normally, sometimes with null or non-string elements (kotlinx rejects non-string/null elements).
    - Vary "child" as null or nested record (one level).
    - Occasionally add extra fields at top-level or in child (Gson/Moshi accept, kotlinx/Jackson reject).
    - Occasionally omit fields in child or make child empty (Gson accepts empty child with defaults, others reject).
    """

    # Constants
    STATUS_ENUMS = ["active", "inactive", "unknown"]
    EXTRA_FIELD_NAMES = ["extraField", "unexpected", "junk"]
    TAG_STRINGS = ["tag1", "tag2", "tag3", ""]

    # --- Field generators ---

    # id: integer or stringified integer (both accepted)
    id_int = st.integers(min_value=0, max_value=10**6)
    id_as_int_or_str = st.one_of(
        id_int.map(str),
        id_int,
    )

    # amount: string normally, sometimes number (kotlinx rejects number)
    # Use mostly string, sometimes number to trigger divergence
    amount_str = st.text(min_size=1, max_size=10).filter(lambda s: all(c not in s for c in '"\\'))
    amount_str_json = amount_str.map(lambda s: '"' + json_string_escape(s) + '"')
    amount_num = st.integers(min_value=0, max_value=10**6).map(str)
    amount_field = st.one_of(
        amount_str_json,
        amount_num,  # number without quotes
    )

    # name: string, null, or non-string (number or boolean)
    name_string = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(lambda s: '"' + json_string_escape(s) + '"'),
    )
    # non-string: number or boolean (kotlinx rejects)
    name_non_string = st.one_of(
        st.integers(min_value=-1000, max_value=1000).map(str),
        st.booleans().map(lambda b: "true" if b else "false"),
    )
    # Mix mostly string/null, sometimes non-string
    name_field = st.one_of(
        name_string,
        name_non_string,
    )

    # status: valid enum string, invalid string, or null
    status_valid = st.sampled_from(STATUS_ENUMS).map(lambda s: '"' + s + '"')
    status_invalid = st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_ENUMS and all(c not in s for c in '"\\')).map(lambda s: '"' + s + '"')
    status_null = st.just("null")
    status_field = st.one_of(
        status_valid,
        status_invalid,
        status_null,
    )

    # tags: array of strings normally, sometimes with null or non-string elements
    tag_string = st.text(min_size=0, max_size=10).map(lambda s: '"' + json_string_escape(s) + '"')
    tag_null = st.just("null")
    tag_non_string = st.one_of(
        st.integers(min_value=-1000, max_value=1000).map(str),
        st.booleans().map(lambda b: "true" if b else "false"),
    )
    # Compose tags array elements with some chance of null/non-string to trigger divergence
    def tags_array_elements():
        # 70% strings, 15% null, 15% non-string
        return st.lists(
            st.one_of(
                tag_string,
                tag_null,
                tag_non_string,
            ),
            min_size=0,
            max_size=5,
        )
    tags_field = tags_array_elements().map(lambda elems: "[" + ",".join(elems) + "]")

    # child: null or nested record (one level)
    # To avoid infinite recursion, child.child is always null or empty (empty child triggers divergence)
    # Compose child record as JSON text (string)
    # We will define a helper to generate child JSON text with no further recursion

    # Helper to generate a child record JSON text with no child or child=null
    @st.composite
    def child_record(draw):
        # id: int or string
        cid = draw(id_as_int_or_str)
        cid_json = str(cid) if isinstance(cid, int) else ('"' + json_string_escape(cid) + '"')

        # amount: string or number (same as parent)
        camount = draw(amount_field)

        # name: string, null, or non-string
        cname = draw(name_field)

        # status: valid enum, invalid, or null
        cstatus = draw(status_field)

        # tags: array with possible null/non-string elements
        ctags = draw(tags_field)

        # child: null or empty object or missing (to trigger divergence)
        child_choice = draw(st.sampled_from(["null", "empty_object", "missing"]))

        if child_choice == "null":
            cchild = "null"
        elif child_choice == "empty_object":
            cchild = "{}"
        else:  # missing
            cchild = None

        # Compose fields, omit child if missing
        fields = [
            '"id":' + cid_json,
            '"amount":' + camount,
            '"name":' + cname,
            '"status":' + cstatus,
            '"tags":' + ctags,
        ]
        if cchild is not None:
            fields.append('"child":' + cchild)

        return "{" + ",".join(fields) + "}"

    # child field: null or nested record
    child_field = st.one_of(
        st.just("null"),
        child_record(),
    )

    # Extra top-level fields: sometimes add one or two extra fields (Gson/Moshi accept, kotlinx/Jackson reject)
    extra_field_name = st.sampled_from(EXTRA_FIELD_NAMES)
    extra_field_value = st.one_of(
        st.integers(min_value=-1000, max_value=1000).map(str),
        st.text(min_size=0, max_size=10).map(lambda s: '"' + json_string_escape(s) + '"'),
        st.booleans().map(lambda b: "true" if b else "false"),
        st.just("null"),
        tags_field,
    )
    extra_fields = st.lists(st.tuples(extra_field_name, extra_field_value), max_size=2)

    # Compose top-level record JSON text
    id_val = draw(id_as_int_or_str)
    id_json = str(id_val) if isinstance(id_val, int) else ('"' + json_string_escape(id_val) + '"')

    amount_val = draw(amount_field)
    name_val = draw(name_field)
    status_val = draw(status_field)
    tags_val = draw(tags_field)
    child_val = draw(child_field)
    extras = draw(extra_fields)

    fields = [
        '"id":' + id_json,
        '"amount":' + amount_val,
        '"name":' + name_val,
        '"status":' + status_val,
        '"tags":' + tags_val,
        '"child":' + child_val,
    ]

    # Add extra fields sometimes (30% chance)
    add_extra = draw(st.booleans())
    if add_extra and extras:
        for k, v in extras:
            fields.append('"' + k + '":' + v)

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")