from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper to produce JSON string literal with proper escaping for double quotes and backslash
    def json_string_literal(s: str) -> str:
        # minimal escaping for " and \ and control chars
        # Hypothesis strings are unicode, so escape control chars as \uXXXX
        def escape_char(c):
            o = ord(c)
            if c == '"':
                return r'\"'
            elif c == '\\':
                return r'\\'
            elif 0 <= o <= 0x1F:
                return '\\u%04x' % o
            else:
                return c
        return '"' + ''.join(escape_char(c) for c in s) + '"'

    # Produce JSON array of strings
    def json_string_array(arr):
        return '[' + ','.join(json_string_literal(s) for s in arr) + ']'

    # Produce JSON null or string or integer coerced to string (for amount)
    # We want to produce values that trigger divergences:
    # - amount: string normally, but can be integer (accepted by Gson, Jackson, Moshi; rejected by kotlinx)
    # - amount can be null (accepted by Gson top-level, rejected by others)
    # - id: integer normally, but can be null (accepted by Gson, Jackson as 0; rejected by Moshi, kotlinx)
    # - name: string or null
    # - status: enum string, unknown string, or null (Gson accepts unknown as null, others reject)
    # - tags: array of strings, or missing, or null (some reject missing tags)
    # - child: nested record or null or missing (Jackson accepts missing child, others reject)
    # We want to produce mostly well-formed documents with one or two fields off.

    # Strategy for "id" field:
    # integer normally, or null (Gson, Jackson accept null as 0; Moshi, kotlinx reject)
    id_val = draw(
        st.one_of(
            st.integers(min_value=0, max_value=2**31-1),
            st.just(None),
        )
    )
    if id_val is None:
        id_json = "null"
    else:
        id_json = str(id_val)

    # Strategy for "amount" field:
    # string normally, but can be integer (accepted by Gson, Jackson, Moshi; rejected by kotlinx)
    # or null (accepted by Gson top-level only)
    amount_choice = draw(st.integers(min_value=0, max_value=2))
    # 0: string
    # 1: integer
    # 2: null
    if amount_choice == 0:
        # string, but sometimes empty or numeric string to test coercion edge
        amount_str = draw(st.text(min_size=0, max_size=10))
        amount_json = json_string_literal(amount_str)
    elif amount_choice == 1:
        amount_int = draw(st.integers(min_value=0, max_value=1000000))
        amount_json = str(amount_int)
    else:
        amount_json = "null"

    # Strategy for "name" field: string or null
    # Gson accepts missing non-nullable string as null, but we always produce present fields here
    name_choice = draw(st.integers(min_value=0, max_value=2))
    # 0: string
    # 1: null
    # 2: empty string
    if name_choice == 0:
        name_str = draw(st.text(min_size=0, max_size=15))
        name_json = json_string_literal(name_str)
    elif name_choice == 1:
        name_json = "null"
    else:
        name_json = '""'

    # Strategy for "status" field:
    # one of enum values normally, or unknown string (Gson accepts unknown as null, others reject)
    # or null (Gson accepts null enum as null, others reject)
    status_choice = draw(st.integers(min_value=0, max_value=3))
    if status_choice == 0:
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_json = json_string_literal(status_val)
    elif status_choice == 1:
        # unknown enum string (e.g. "Active" with capital A, or "invalid")
        unknown_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES))
        status_json = json_string_literal(unknown_status)
    elif status_choice == 2:
        # null enum
        status_json = "null"
    else:
        # missing enum not allowed by schema, but we always produce present fields

        # fallback to valid enum
        status_val = draw(st.sampled_from(STATUS_VALUES))
        status_json = json_string_literal(status_val)

    # Strategy for "tags" field:
    # array of strings normally
    # or missing (Gson, Jackson accept missing tags as null; Moshi, kotlinx reject missing tags)
    # or null (Gson, Jackson accept null for tags? Known: Gson and Jackson accept missing tags as null, no mention of null tags)
    # We'll produce present tags field always, but sometimes null to test
    tags_choice = draw(st.integers(min_value=0, max_value=2))
    # 0: array of strings
    # 1: null
    # 2: empty array
    if tags_choice == 0:
        tags_list = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=5))
        tags_json = json_string_array(tags_list)
    elif tags_choice == 1:
        tags_json = "null"
    else:
        tags_json = "[]"

    # Strategy for "child" field:
    # null, missing, or nested record
    # Jackson accepts missing child, others reject missing child
    # Gson and Jackson accept null child, Moshi and kotlinx reject null child
    # We'll produce present child field always, but sometimes null or nested record
    # To keep recursion bounded, max depth 1 (child.child always null)
    # We will produce child as null or nested record with all fields present and well-formed except maybe one field off

    # Helper to produce nested child JSON string (one level only)
    def child_record():
        # id for child: integer or null (same rules)
        c_id_val = draw(
            st.one_of(
                st.integers(min_value=0, max_value=2**31-1),
                st.just(None),
            )
        )
        c_id_json = "null" if c_id_val is None else str(c_id_val)

        # amount for child: string or integer or null (Gson accepts null in child amount, Jackson rejects null in child amount)
        c_amount_choice = draw(st.integers(min_value=0, max_value=2))
        if c_amount_choice == 0:
            c_amount_str = draw(st.text(min_size=0, max_size=10))
            c_amount_json = json_string_literal(c_amount_str)
        elif c_amount_choice == 1:
            c_amount_int = draw(st.integers(min_value=0, max_value=1000000))
            c_amount_json = str(c_amount_int)
        else:
            c_amount_json = "null"

        # name for child: string or null
        c_name_choice = draw(st.integers(min_value=0, max_value=1))
        if c_name_choice == 0:
            c_name_str = draw(st.text(min_size=0, max_size=15))
            c_name_json = json_string_literal(c_name_str)
        else:
            c_name_json = "null"

        # status for child: enum string only (to reduce complexity)
        c_status_val = draw(st.sampled_from(STATUS_VALUES))
        c_status_json = json_string_literal(c_status_val)

        # tags for child: array of strings or empty array (no null or missing to reduce complexity)
        c_tags_list = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=3))
        c_tags_json = json_string_array(c_tags_list)

        # child.child always null (no further recursion)
        c_child_json = "null"

        # Compose child record JSON
        child_fields = [
            '"id":' + c_id_json,
            '"amount":' + c_amount_json,
            '"name":' + c_name_json,
            '"status":' + c_status_json,
            '"tags":' + c_tags_json,
            '"child":' + c_child_json,
        ]
        return "{" + ",".join(child_fields) + "}"

    child_choice = draw(st.integers(min_value=0, max_value=2))
    # 0: null
    # 1: nested record
    # 2: missing (but we always produce present fields, so treat as null to keep scoring)
    if child_choice == 0:
        child_json = "null"
    elif child_choice == 1:
        child_json = child_record()
    else:
        # missing child not produced, but we produce null to simulate missing for Jackson acceptance
        child_json = "null"

    # Compose top-level JSON object
    # We always produce all fields present except "missing" child simulated as null
    # To simulate missing tags (which Moshi rejects), we produce null tags sometimes (no missing tags field)
    # To simulate missing fields that Gson accepts, we do not produce missing fields here (always present)
    # This matches the hint to produce mostly well-formed with one or two fields off

    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
        '"child":' + child_json,
    ]

    json_text = "{" + ",".join(fields) + "}"
    return json_text.encode("utf-8")