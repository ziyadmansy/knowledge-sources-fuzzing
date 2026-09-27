from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values and nullability
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # We will produce JSON text manually, carefully controlling formatting and spacing.

    # Helper: produce a JSON string literal from a Python string (escape minimal chars)
    def json_string(s: str) -> str:
        # Minimal escaping: backslash and double quote
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Helper: produce JSON array of strings
    def json_array_of_strings(lst):
        return '[' + ','.join(lst) + ']'

    # Helper: produce JSON object from dict of field_name -> json_text (already serialized)
    def json_object(d):
        # Insert fields in order for readability
        fields = []
        for k in ['id', 'amount', 'name', 'status', 'tags', 'child']:
            if k in d:
                fields.append(json_string(k) + ':' + d[k])
        return '{' + ','.join(fields) + '}'

    # Strategy for id field:
    # id is integer, non-nullable
    # Known: Gson accepts missing id (decodes as 0), Moshi/kx reject missing,
    # Gson accepts null (decodes as 0), others reject null.
    # Also try wrong types (string, float) to trigger divergence.
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),
        st.just('null'),
        st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()).map(json_string),
        st.floats(allow_infinity=False, allow_nan=False).map(lambda f: str(f)),
        st.none().map(lambda _: 'null'),
    )

    # Strategy for amount field:
    # amount is string, non-nullable
    # Gson accepts number for string fields, decoding number as string
    # Moshi accepts convertible types (number->string)
    # kotlinx rejects wrong types
    # Jackson accepts convertible types for strings
    # Also test null and missing
    amount_strategy = st.one_of(
        st.text(min_size=1, max_size=10).map(json_string),
        st.integers(min_value=0, max_value=100000).map(str),  # number as string
        st.floats(allow_infinity=False, allow_nan=False).map(str),
        st.just('null'),
    )

    # Strategy for name field:
    # string or null, nullable
    # Gson accepts null and missing (decodes null)
    # Moshi and kotlinx reject missing? (name nullable, so missing allowed?)
    # Jackson accepts missing nullable fields
    # Also test wrong types (number, bool)
    name_strategy = st.one_of(
        st.none().map(lambda _: 'null'),
        st.text(min_size=0, max_size=10).map(json_string),
        st.integers(min_value=0, max_value=1000).map(str),
        st.booleans().map(lambda b: 'true' if b else 'false'),
    )

    # Strategy for status field:
    # enum, non-nullable
    # Gson accepts missing enum (decodes null), unknown enum (decodes null)
    # Moshi/kx reject missing and unknown enums
    # Jackson accepts missing enum (decodes null), rejects unknown enum
    # Also test case variants (should be rejected by Moshi/kx/Jackson)
    # Also test null
    status_known = st.sampled_from(STATUS_VALUES)
    status_unknown = st.text(min_size=1, max_size=10).filter(
        lambda s: s.lower() not in ['"active"', '"inactive"', '"unknown"']
    ).map(json_string)
    status_case_variant = st.sampled_from(['"Active"', '"INACTIVE"', '"Unknown"'])
    status_strategy = st.one_of(
        status_known,
        status_unknown,
        status_case_variant,
        st.just('null'),
    )

    # Strategy for tags field:
    # array of strings, non-nullable
    # Gson accepts null (decodes null?), Moshi rejects null for non-nullable
    # Jackson rejects null for non-nullable
    # Also test missing
    # Also test empty array, array with numbers (wrong type)
    tag_string = st.text(min_size=1, max_size=5).map(json_string)
    tags_array_correct = st.lists(tag_string, min_size=0, max_size=3).map(json_array_of_strings)
    tags_array_wrong = st.lists(st.integers(min_value=0, max_value=10).map(str), min_size=1, max_size=3).map(lambda nums: '[' + ','.join(nums) + ']')
    tags_strategy = st.one_of(
        tags_array_correct,
        tags_array_wrong,
        st.just('null'),
    )

    # Recursive child field: either null or a nested record (one level only)
    # Known: Gson accepts missing or null nested objects
    # Moshi accepts missing nested objects, rejects duplicates
    # kotlinx rejects missing nested objects
    # Jackson accepts missing nested objects, rejects null nested objects if non-nullable
    # child is nullable, so null allowed
    # To avoid infinite recursion, limit depth to 1
    # We'll produce child as either null or a nested record with no child (child=null)
    # To avoid complexity, child nested record will have fixed valid fields except for one field varied similarly

    # Compose a minimal valid nested record with child=null
    def nested_record():
        # id int as string
        nid = draw(st.integers(min_value=1, max_value=1000).map(str))
        # amount string
        namount = draw(st.text(min_size=1, max_size=5).map(json_string))
        # name nullable string or null
        nname = draw(st.one_of(st.none().map(lambda _: 'null'), st.text(min_size=1, max_size=5).map(json_string)))
        # status enum known only
        nstatus = draw(st.sampled_from(STATUS_VALUES))
        # tags array correct only
        ntags = draw(st.lists(st.text(min_size=1, max_size=3).map(json_string), min_size=0, max_size=2).map(json_array_of_strings))
        # child null
        nchild = 'null'
        return json_object({
            'id': nid,
            'amount': namount,
            'name': nname,
            'status': nstatus,
            'tags': ntags,
            'child': nchild,
        })

    # child strategy: null or nested record
    child_strategy = st.one_of(
        st.just('null'),
        st.deferred(nested_record),
    )

    # Now build the top-level record dict with fields, allowing missing or null for some fields to trigger divergence
    # We vary presence of fields to trigger missing field acceptance/rejection
    # We vary nullability and type of fields to trigger acceptance/rejection differences

    # For each field, decide presence or absence (except id, amount, status, tags which are required)
    # But we want to vary missing for id, amount, status, tags to trigger divergence (Gson accepts missing, others reject)
    # So for each required field, randomly decide missing or present with value from strategy
    # For nullable fields (name, child), randomly decide missing or present

    # Decide presence flags
    id_present = draw(st.booleans())
    amount_present = draw(st.booleans())
    status_present = draw(st.booleans())
    tags_present = draw(st.booleans())
    name_present = draw(st.booleans())
    child_present = draw(st.booleans())

    # Compose fields dict
    fields = {}

    if id_present:
        fields['id'] = draw(id_strategy)
    # else missing

    if amount_present:
        fields['amount'] = draw(amount_strategy)

    if name_present:
        fields['name'] = draw(name_strategy)

    if status_present:
        fields['status'] = draw(status_strategy)

    if tags_present:
        fields['tags'] = draw(tags_strategy)

    if child_present:
        fields['child'] = draw(child_strategy)

    # To increase divergence, sometimes add duplicate keys (Gson accepts, Moshi rejects duplicates)
    # We'll do this rarely to not break too many documents
    add_duplicate = draw(st.booleans())

    json_text = json_object(fields)

    if add_duplicate and len(fields) > 0:
        # Pick a random field to duplicate
        dup_key = draw(st.sampled_from(list(fields.keys())))
        dup_value = fields[dup_key]
        # Insert duplicate key after first occurrence
        # Insert before last } to keep valid JSON object
        insert_pos = json_text.rfind('}')
        # Find first occurrence of key in json_text
        key_str = json_string(dup_key) + ':'
        first_pos = json_text.find(key_str)
        # Insert duplicate key:value after first occurrence's comma or just before last }
        # We'll insert before last } with a comma
        json_text = json_text[:insert_pos] + ',' + key_str + dup_value + json_text[insert_pos:]

    return json_text.encode('utf-8')