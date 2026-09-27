from hypothesis import strategies as st

# Helper: JSON string escape minimal (only backslash and quote)
def json_string_escape(s: str) -> str:
    # Minimal escaping for JSON string: backslash and quote
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text bytes for the described record schema, aiming to produce
    subtle divergences between Gson, Moshi, kotlinx.serialization, and Jackson.

    Strategy:
    - Mostly well-formed documents with one or two small "off" tweaks.
    - Control presence, nullability, type variants, enum casing, extra keys, null arrays.
    - Bounded recursion for "child" field (max depth 1).
    """

    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]
    STATUS_VARIANTS = (
        STATUS_VALUES
        + [v.upper() for v in STATUS_VALUES]  # case variants
        + ["invalid", "Active", "INACTIVE", "UNKNOWN"]  # invalid enums
    )

    # Primitive field generators with subtle variants to trigger divergences

    # id: integer or null or string number (to test coercion)
    id_base = st.integers(min_value=0, max_value=10000)
    id_null = st.just("null")
    id_string_number = id_base.map(lambda i: f'"{i}"')
    id_number = id_base.map(str)
    # id can be number, string number, or null (to test null acceptance)
    id_field = st.one_of(id_number, id_string_number, id_null)

    # amount: string normally, but also number or null (to test coercion and null)
    amount_str = st.text(min_size=1, max_size=10).map(json_string_escape).map(lambda s: f'"{s}"')
    amount_num = st.integers(min_value=0, max_value=100000).map(str)
    amount_null = st.just("null")
    amount_field = st.one_of(amount_str, amount_num, amount_null)

    # name: string or null or missing (missing triggers Moshi/kotlinx rejection)
    name_str = st.text(min_size=0, max_size=10).map(json_string_escape).map(lambda s: f'"{s}"')
    name_null = st.just("null")
    # We will handle missing by optionally omitting the field at top level or child level
    # But since missing is a strong divergence, we include it as an option
    name_field = st.one_of(name_str, name_null)

    # status: enum string, case variants, unknown, null (null triggers Gson null)
    status_valid = st.sampled_from(STATUS_VALUES).map(lambda s: f'"{s}"')
    status_case_variant = st.sampled_from([v.upper() for v in STATUS_VALUES]).map(lambda s: f'"{s}"')
    status_invalid = st.sampled_from(["invalid", "Active", "INACTIVE", "UNKNOWN"]).map(lambda s: f'"{s}"')
    status_null = st.just("null")
    # We want to test acceptance/rejection on enum variants and null
    status_field = st.one_of(status_valid, status_case_variant, status_invalid, status_null)

    # tags: array of strings normally, but also null or missing
    tag_str = st.text(min_size=1, max_size=8).map(json_string_escape).map(lambda s: f'"{s}"')
    tags_array = st.lists(tag_str, min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_null = st.just("null")
    # missing tags field also possible
    tags_field = st.one_of(tags_array, tags_null)

    # child: null or nested record (one level only)
    # To avoid infinite recursion, child depth max 1
    # We'll generate child record with no child inside (child=null)
    # child can be null or a nested record with no child field or child=null
    # We'll generate child record with same strategy but no further recursion

    # Compose child record fields (no further recursion)
    def child_record():
        # For child record, omit child field or set child=null only (no deeper nesting)
        # We allow missing fields in child to trigger divergences
        # Use same field strategies but no child recursion
        # id, amount, name, status, tags, child=null or missing
        id_c = id_field
        amount_c = amount_field
        name_c = st.one_of(name_field, st.just(None))  # None means missing
        status_c = status_field
        tags_c = st.one_of(tags_field, st.just(None))  # None means missing
        child_c = st.one_of(st.just("null"), st.just(None))  # None means missing

        @st.composite
        def build_child(draw):
            idv = draw(id_c)
            amountv = draw(amount_c)
            namev = draw(name_c)
            statusv = draw(status_c)
            tagsv = draw(tags_c)
            childv = draw(child_c)

            fields = []

            # id always present (required)
            fields.append(f'"id":{idv}')
            # amount always present (required)
            fields.append(f'"amount":{amountv}')
            # name optional
            if namev is not None:
                fields.append(f'"name":{namev}')
            # status always present
            fields.append(f'"status":{statusv}')
            # tags optional
            if tagsv is not None:
                fields.append(f'"tags":{tagsv}')
            # child optional
            if childv is not None:
                fields.append(f'"child":{childv}')

            return "{" + ",".join(fields) + "}"

        return build_child()

    # child field: null or nested record or missing
    child_field = st.one_of(
        st.just("null"),
        child_record(),
        st.just(None),  # missing child field
    )

    # Top-level name and tags can also be missing to test missing field divergence
    top_name = st.one_of(name_field, st.just(None))  # None means missing
    top_tags = st.one_of(tags_field, st.just(None))  # None means missing

    @st.composite
    def build_top(draw):
        idv = draw(id_field)
        amountv = draw(amount_field)
        namev = draw(top_name)
        statusv = draw(status_field)
        tagsv = draw(top_tags)
        childv = draw(child_field)

        fields = []

        # id always present (required)
        fields.append(f'"id":{idv}')
        # amount always present (required)
        fields.append(f'"amount":{amountv}')
        # name optional
        if namev is not None:
            fields.append(f'"name":{namev}')
        # status always present
        fields.append(f'"status":{statusv}')
        # tags optional
        if tagsv is not None:
            fields.append(f'"tags":{tagsv}')
        # child optional
        if childv is not None:
            fields.append(f'"child":{childv}')

        # Occasionally add one extra unknown key to test extra keys acceptance/rejection
        add_extra = draw(st.booleans())
        if add_extra:
            # Extra key with string value
            extra_key = "extraKey"
            extra_val = draw(st.text(min_size=1, max_size=5).map(json_string_escape))
            fields.append(f'"{extra_key}":"{extra_val}"')

        # Occasionally add duplicate keys for one field to test last key wins
        add_dup = draw(st.booleans())
        if add_dup:
            # Duplicate "status" key with a different value
            dup_status_val = draw(st.sampled_from(STATUS_VALUES)).map(lambda s: f'"{s}"')
            # Insert duplicate status key at random position
            pos = draw(st.integers(min_value=0, max_value=len(fields)))
            fields.insert(pos, f'"status":{dup_status_val}')

        json_text = "{" + ",".join(fields) + "}"
        return json_text.encode("utf-8")

    return draw(build_top())