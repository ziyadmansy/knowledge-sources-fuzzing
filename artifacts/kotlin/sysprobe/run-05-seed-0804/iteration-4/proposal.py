from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping for test purposes
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings
def json_array_of_strings(lst):
    return '[' + ','.join(json_string(s) for s in lst) + ']'

# Helper: JSON enum "status" with known values or unknown variants
status_values = ["active", "inactive", "unknown"]
# Also allow unknown or case variants for testing (to trigger divergence)
status_known = st.sampled_from(status_values)
status_unknown = st.one_of(
    st.text(min_size=1, max_size=10).filter(lambda x: x.lower() not in status_values),
    st.sampled_from([v.upper() for v in status_values]),
    st.sampled_from([v.capitalize() for v in status_values]),
)

# Helper: JSON null or string "null"
def json_null_or_string_null(draw):
    # Sometimes produce null, sometimes produce "null" string
    return draw(st.one_of(st.just("null"), st.just("null")))

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate a JSON document as bytes, representing the record schema with
    subtle variations to maximize divergence between Gson, Moshi, kotlinx.serialization, and Jackson.
    """

    # Decide if top-level fields are missing or present
    # We bias towards present, but sometimes omit to trigger divergence on missing fields
    # According to known facts:
    # - Gson accepts missing non-nullable fields (id, amount, status, tags, child)
    # - Moshi and kotlinx reject missing required fields
    # - Jackson accepts missing child but rejects missing tags
    # So missing tags is a good divergence trigger.
    # Missing id or amount or status is also good but more likely to cause multiple rejections.
    # We'll vary missingness per field with low probability.

    def maybe_missing(field_name, base_prob=0.1):
        # 10% chance missing by default, except tags and child have different probs
        if field_name == "tags":
            return draw(st.booleans().map(lambda b: not b))  # ~50% missing tags to trigger divergence
        if field_name == "child":
            return draw(st.booleans().map(lambda b: not b))  # ~50% missing child to test Jackson acceptance
        return draw(st.booleans().map(lambda b: b if b else False))  # mostly present

    # id: integer, non-nullable, but Gson/Jackson accept null as 0, Moshi/kx reject null
    # We try: present integer, present null, missing
    id_missing = maybe_missing("id", 0.05)
    if id_missing:
        id_field = None
    else:
        id_null = draw(st.booleans())
        if id_null:
            id_field = "null"
        else:
            # integer id >=0
            id_field = str(draw(st.integers(min_value=0, max_value=1000)))

    # amount: string non-nullable
    # Gson accepts null, others reject null
    # Gson, Jackson, Moshi accept integer coercion, kx rejects
    amount_missing = maybe_missing("amount", 0.05)
    if amount_missing:
        amount_field = None
    else:
        amount_null = draw(st.booleans())
        if amount_null:
            amount_field = "null"
        else:
            # Choose string or integer coerced to string
            amount_type = draw(st.sampled_from(["string", "int"]))
            if amount_type == "string":
                # string amount, non-empty, ascii digits or letters
                amount_str = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Nd','Ll','Lu'))))
                amount_field = json_string(amount_str)
            else:
                # integer coerced to string
                amount_field = str(draw(st.integers(min_value=0, max_value=10000)))

    # name: string or null, nullable
    # Gson accepts missing as null, others reject missing? Not specified, but all fields always present in well-formed
    # We'll always present name (to reduce complexity)
    name_null = draw(st.booleans())
    if name_null:
        name_field = "null"
    else:
        # string or empty string
        name_str = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(whitelist_categories=('Ll','Lu','Zs'))))
        name_field = json_string(name_str)

    # status: enum, one of "active", "inactive", "unknown"
    # Gson accepts unknown enum as null, others reject unknown or case variants
    # We'll sometimes produce unknown or case variants to trigger divergence
    status_missing = maybe_missing("status", 0.05)
    if status_missing:
        status_field = None
    else:
        status_choice = draw(st.one_of(
            status_known,
            status_unknown,
        ))
        status_field = json_string(status_choice)

    # tags: array of strings, non-nullable
    # Gson and Jackson accept missing tags as null; Moshi and kx reject missing tags
    tags_missing = maybe_missing("tags", 0.5)
    if tags_missing:
        tags_field = None
    else:
        # array of 0 to 3 strings
        tags_list = draw(st.lists(st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=('Ll','Lu','Nd'))), max_size=3))
        tags_field = json_array_of_strings(tags_list)

    # child: recursive record or null or missing
    # Jackson accepts missing child, Gson accepts missing child, Moshi and kx reject missing child
    child_missing = maybe_missing("child", 0.5)
    if child_missing:
        child_field = None
    else:
        # child can be null or a record with one level recursion only
        child_null = draw(st.booleans())
        if child_null:
            child_field = "null"
        else:
            # Build child record with similar rules but no further recursion (child.child always null or missing)
            # For child fields, we apply known divergences too:
            # Gson accepts null or missing non-nullable fields inside child
            # Moshi and kx reject null or missing non-nullable fields inside child
            # Gson and Jackson accept integer amount inside child coercing to string; Moshi accepts it; kx rejects it
            # Gson accepts null amount inside child; Jackson rejects it

            # Child id: integer or null (Gson/Jackson accept null as 0)
            child_id_null = draw(st.booleans())
            if child_id_null:
                child_id_field = "null"
            else:
                child_id_field = str(draw(st.integers(min_value=0, max_value=1000)))

            # Child amount: string, integer coerced to string, or null (Gson accepts null, Jackson rejects null)
            child_amount_type = draw(st.sampled_from(["string", "int", "null"]))
            if child_amount_type == "string":
                child_amount_str = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Ll','Lu','Nd'))))
                child_amount_field = json_string(child_amount_str)
            elif child_amount_type == "int":
                child_amount_field = str(draw(st.integers(min_value=0, max_value=10000)))
            else:
                child_amount_field = "null"

            # Child name: string or null
            child_name_null = draw(st.booleans())
            if child_name_null:
                child_name_field = "null"
            else:
                child_name_str = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(whitelist_categories=('Ll','Lu','Zs'))))
                child_name_field = json_string(child_name_str)

            # Child status: enum known only (to reduce complexity)
            child_status_field = json_string(draw(status_known))

            # Child tags: array of strings or null (Gson/Jackson accept null or missing, Moshi/kx reject missing)
            child_tags_null = draw(st.booleans())
            if child_tags_null:
                child_tags_field = "null"
            else:
                child_tags_list = draw(st.lists(st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=('Ll','Lu','Nd'))), max_size=3))
                child_tags_field = json_array_of_strings(child_tags_list)

            # Child child: always null or missing (one level recursion)
            child_child_missing = draw(st.booleans())
            if child_child_missing:
                child_child_field = None
            else:
                child_child_field = "null"

            # Compose child JSON object fields, omitting missing fields
            child_fields = []
            child_fields.append('"id":' + child_id_field)
            child_fields.append('"amount":' + child_amount_field)
            child_fields.append('"name":' + child_name_field)
            child_fields.append('"status":' + child_status_field)
            if child_tags_field is not None:
                child_fields.append('"tags":' + child_tags_field)
            if child_child_field is not None:
                child_fields.append('"child":' + child_child_field)

            child_field = '{' + ','.join(child_fields) + '}'

    # Compose top-level JSON object fields, omitting missing fields
    fields = []
    if id_field is not None:
        fields.append('"id":' + id_field)
    if amount_field is not None:
        fields.append('"amount":' + amount_field)
    if name_field is not None:
        fields.append('"name":' + name_field)
    if status_field is not None:
        fields.append('"status":' + status_field)
    if tags_field is not None:
        fields.append('"tags":' + tags_field)
    if child_field is not None:
        fields.append('"child":' + child_field)

    json_text = '{' + ','.join(fields) + '}'
    return json_text.encode("utf-8")