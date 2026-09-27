from hypothesis import strategies as st

# Constants for enum values and JSON literals
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
NULL = "null"

def json_str(s: str) -> str:
    # Escape backslash and double quote minimally for JSON strings
    # Hypothesis strings won't contain control chars by default, so minimal escaping
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text for the Record schema with bounded recursion depth 1 for "child".
    Vary one or two fields at a time around well-formedness to maximize divergence
    between Gson, Moshi, kotlinx.serialization, and Jackson Kotlin module.
    """

    # --- Helpers to produce JSON text for each field with controlled variations ---

    # id: integer, non-nullable
    # Known divergences:
    # - Gson, Jackson accept null as 0; Moshi, kotlinx reject null
    # - Gson accepts missing as 0; Moshi, kotlinx reject missing; Jackson accepts missing "child" only
    # We'll vary id as: present int, present null, missing
    id_present_int = st.integers(min_value=0, max_value=2**31-1).map(str)
    id_present_null = st.just(NULL)
    id_missing = st.just(None)

    id_choice = draw(st.one_of(id_present_int, id_present_null, id_missing))

    # amount: string, non-nullable
    # Known divergences:
    # - Gson accepts null; others reject null
    # - Gson, Jackson, Moshi accept integer coercion to string; kotlinx rejects integer
    # We'll vary amount as: string, integer, null, missing
    amount_str = st.text(min_size=1, max_size=10).map(json_str)
    amount_int = st.integers(min_value=0, max_value=10000).map(str)
    amount_null = st.just(NULL)
    amount_missing = st.just(None)

    amount_choice = draw(st.one_of(amount_str, amount_int, amount_null, amount_missing))

    # name: string or null (nullable)
    # Known: Gson accepts missing as null; Moshi, kotlinx reject missing; Jackson rejects missing
    # We'll vary name as: string, null, missing
    name_str = st.text(min_size=0, max_size=10).map(json_str)
    name_null = st.just(NULL)
    name_missing = st.just(None)

    name_choice = draw(st.one_of(name_str, name_null, name_missing))

    # status: enum with 3 values, non-nullable
    # Known divergences:
    # - Gson accepts unknown enum values as null
    # - Moshi, kotlinx, Jackson reject unknown or case-variant enum values
    # We'll vary status as: valid enum, unknown enum (string), case-variant enum, null, missing
    status_valid = st.sampled_from(STATUS_VALUES)
    status_unknown = st.text(min_size=3, max_size=10).filter(lambda s: s.lower() not in {"active", "inactive", "unknown"}).map(json_str)
    status_case_variant = st.sampled_from(['"Active"', '"Inactive"', '"Unknown"'])
    status_null = st.just(NULL)
    status_missing = st.just(None)

    status_choice = draw(st.one_of(status_valid, status_unknown, status_case_variant, status_null, status_missing))

    # tags: array of strings, non-nullable
    # Known divergences:
    # - Gson, Jackson accept missing as null
    # - Moshi rejects missing
    # - kotlinx rejects missing
    # We'll vary tags as: present array (possibly empty), null, missing
    tag_str = st.text(min_size=1, max_size=10).map(json_str)
    tags_array = st.lists(tag_str, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_null = st.just(NULL)
    tags_missing = st.just(None)

    tags_choice = draw(st.one_of(tags_array, tags_null, tags_missing))

    # child: nullable Record (one level recursion)
    # Known divergences:
    # - Gson, Jackson accept missing and null child
    # - Moshi rejects missing child
    # - kotlinx rejects missing child
    # - Nested fields behave like top-level for null/missing/coercion
    # We'll vary child as: null, missing, or a nested record with limited variation (only id and amount varied)
    # To avoid deep recursion, child record will have fixed fields except id and amount varied similarly

    # Child id: present int or null (to trigger divergences)
    child_id_present_int = st.integers(min_value=0, max_value=1000).map(str)
    child_id_null = st.just(NULL)
    child_id_missing = st.just(None)
    child_id_choice = draw(st.one_of(child_id_present_int, child_id_null, child_id_missing))

    # Child amount: string, int, null (Gson accepts null, Jackson rejects null)
    child_amount_str = st.text(min_size=1, max_size=10).map(json_str)
    child_amount_int = st.integers(min_value=0, max_value=1000).map(str)
    child_amount_null = st.just(NULL)
    child_amount_missing = st.just(None)
    child_amount_choice = draw(st.one_of(child_amount_str, child_amount_int, child_amount_null, child_amount_missing))

    # Child name: always null (to keep simple)
    child_name_choice = NULL

    # Child status: always valid enum (to keep simple)
    child_status_choice = '"active"'

    # Child tags: always present empty array (to keep simple)
    child_tags_choice = "[]"

    # Child child: always null (no deeper recursion)
    child_child_choice = NULL

    def field_json(name, val):
        if val is None:
            return None
        return json_str(name) + ":" + val

    # Compose child JSON object or null or missing
    if draw(st.booleans()):
        # child present as object
        child_fields = [
            field_json("id", child_id_choice),
            field_json("amount", child_amount_choice),
            field_json("name", child_name_choice),
            field_json("status", child_status_choice),
            field_json("tags", child_tags_choice),
            field_json("child", child_child_choice),
        ]
        child_fields = [f for f in child_fields if f is not None]
        child_json = "{" + ",".join(child_fields) + "}"
    else:
        # child null or missing
        child_json = draw(st.one_of(st.just(NULL), st.just(None)))

    # Compose top-level fields, omitting those set to None (missing)
    top_fields = [
        field_json("id", id_choice),
        field_json("amount", amount_choice),
        field_json("name", name_choice),
        field_json("status", status_choice),
        field_json("tags", tags_choice),
        field_json("child", child_json),
    ]
    top_fields = [f for f in top_fields if f is not None]

    json_text = "{" + ",".join(top_fields) + "}"

    return json_text.encode("utf-8")