from hypothesis import strategies as st

# Constants for fixed sets
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce JSON string literal with proper escaping of quotes and backslashes
# but since Hypothesis strings are arbitrary, we keep it simple and safe by restricting chars.
# We'll use Hypothesis to generate strings without quotes or backslashes to avoid escaping complexity.
safe_json_string = st.text(
    alphabet=st.characters(
        blacklist_characters='"\\',
        blacklist_categories=('Cs',)  # Other control chars
    ),
    min_size=0,
    max_size=20,
).map(lambda s: '"' + s + '"')

# id: integer only, no floats or strings accepted by any
id_strategy = st.integers(min_value=0, max_value=2**31-1).map(str)

# amount: string only, any string accepted if string
amount_strategy = safe_json_string

# name: string or null, or missing (missing means null for all except built_value)
# We'll produce either null, string, or omit (omit only for name)
# But since all accept missing name as null, we can produce missing sometimes
# But missing fields are tricky to represent in JSON text, so we must build object text carefully.
# We'll handle missing fields by omitting them from the JSON text.
# So name_strategy returns either None (meaning omit) or a JSON value string.
name_strategy = st.one_of(
    st.just(None),  # omit field
    st.just("null"),
    safe_json_string,
)

# status: one of the three strings, no null or invalid allowed
status_strategy = st.sampled_from(STATUS_VALUES)

# tags: array of strings, or null (only built_value accepts null as []), or missing (only built_value accepts missing as [])
# We'll produce either:
# - present with array of strings (including empty array)
# - present with null (to trigger built_value acceptance only)
# - missing (omit field)
# We want to produce missing sometimes to trigger built_value defaulting
tags_array = st.lists(safe_json_string, max_size=5)
tags_strategy = st.one_of(
    tags_array.map(lambda arr: '[' + ','.join(arr) + ']'),
    st.just("null"),
    st.just(None),  # omit field
)

# child: null or a nested record (one level recursion)
# We'll limit recursion depth to 1 (child's child is always null)
# child_strategy returns either "null" or JSON object string
# We'll define a helper function to build child JSON text from fields dict

# We'll define a helper to build a record JSON text from fields dict (field -> JSON string or None to omit)
def build_record_json(fields):
    # fields: dict of field_name -> JSON string or None (omit)
    # produce JSON object text with fields present in order id,amount,name,status,tags,child if present
    parts = []
    for key in ['id', 'amount', 'name', 'status', 'tags', 'child']:
        v = fields.get(key, None)
        if v is not None:
            parts.append('"' + key + '":' + v)
    return '{' + ','.join(parts) + '}'

# We'll define a strategy for a record fields dict (no recursion here)
# We'll produce fields with one or two subtle divergences from well-formedness:
# - missing tags (accepted only by built_value)
# - tags null (accepted only by built_value)
# - missing name (accepted by all as null)
# - name null or string
# - child null or well-formed child record (depth 1)
# - status always valid (to avoid all rejecting)
# - id always integer
# - amount always string
# We'll also produce some cases with one field wrong type to cause divergence in rejection type

# To maximize divergence, we produce records that are almost well-formed but with one subtle difference:
# 1) tags missing vs present
# 2) tags null vs present array
# 3) child null vs child with missing required field (to cause rejection)
# 4) name missing vs present null or string
# 5) amount string always correct (to avoid all rejecting)
# 6) status always valid (to avoid all rejecting)
# 7) id integer always correct

# We'll define a strategy for child record fields with no recursion (child.child always null)
def child_fields_strategy():
    # child record must be well-formed or with one subtle error (missing required field or wrong type)
    # We'll produce either:
    # - well-formed child record (all fields present, correct types)
    # - child record missing "tags" (accepted only by built_value)
    # - child record with tags null (accepted only by built_value)
    # - child record with missing "name" (accepted by all)
    # - child record with child=null (no recursion)
    # - child record with child=null or missing (missing child means null)
    # - child record with one field wrong type (e.g. amount as number string)
    # We'll produce a weighted choice to maximize divergence

    # well-formed child record fields
    well_formed = st.fixed_dictionaries({
        'id': id_strategy,
        'amount': amount_strategy,
        'name': name_strategy.map(lambda v: v if v is not None else "null"),
        'status': status_strategy,
        'tags': tags_array.map(lambda arr: '[' + ','.join(arr) + ']'),
        'child': st.just("null"),
    })

    # missing tags
    missing_tags = st.fixed_dictionaries({
        'id': id_strategy,
        'amount': amount_strategy,
        'name': name_strategy.map(lambda v: v if v is not None else "null"),
        'status': status_strategy,
        # 'tags' omitted
        'child': st.just("null"),
    }, optional={'tags'})

    # tags null
    tags_null = st.fixed_dictionaries({
        'id': id_strategy,
        'amount': amount_strategy,
        'name': name_strategy.map(lambda v: v if v is not None else "null"),
        'status': status_strategy,
        'tags': st.just("null"),
        'child': st.just("null"),
    })

    # missing name (omit name)
    missing_name = st.fixed_dictionaries({
        'id': id_strategy,
        'amount': amount_strategy,
        # 'name' omitted
        'status': status_strategy,
        'tags': tags_array.map(lambda arr: '[' + ','.join(arr) + ']'),
        'child': st.just("null"),
    }, optional={'name'})

    # child with one field wrong type: amount as integer (should be string)
    wrong_amount_type = st.fixed_dictionaries({
        'id': id_strategy,
        'amount': id_strategy,  # int instead of string
        'name': name_strategy.map(lambda v: v if v is not None else "null"),
        'status': status_strategy,
        'tags': tags_array.map(lambda arr: '[' + ','.join(arr) + ']'),
        'child': st.just("null"),
    })

    # child missing required field id (should cause rejection)
    missing_id = st.fixed_dictionaries({
        # 'id' omitted
        'amount': amount_strategy,
        'name': name_strategy.map(lambda v: v if v is not None else "null"),
        'status': status_strategy,
        'tags': tags_array.map(lambda arr: '[' + ','.join(arr) + ']'),
        'child': st.just("null"),
    }, optional={'id'})

    # Compose weighted choice to maximize divergence
    return st.one_of(
        well_formed,
        missing_tags,
        tags_null,
        missing_name,
        wrong_amount_type,
        missing_id,
    )

@st.composite
def generated_json(draw) -> bytes:
    # Top-level record fields with subtle divergences

    # id always integer
    id_val = draw(id_strategy)

    # amount always string
    amount_val = draw(amount_strategy)

    # name: None (omit), null, or string
    name_val = draw(name_strategy)

    # status always valid string
    status_val = draw(status_strategy)

    # tags: present array, null, or missing (None)
    tags_val = draw(tags_strategy)

    # child: null or nested record
    # We'll produce child as null or a nested record with one subtle divergence
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_val = "null"
    else:
        child_fields = draw(child_fields_strategy())
        # child_fields is dict of field -> JSON string
        # For optional omitted fields, they are missing from dict
        # Build JSON text for child record
        child_val = build_record_json(child_fields)

    # Build top-level fields dict with possible omissions for name and tags
    fields = {
        'id': id_val,
        'amount': amount_val,
        'status': status_val,
        'child': child_val,
    }
    # name may be None (omit), or JSON string/null
    if name_val is not None:
        fields['name'] = name_val
    # tags may be None (omit), or JSON array or null
    if tags_val is not None:
        fields['tags'] = tags_val

    # Build JSON text for top-level record
    json_text = build_record_json(fields)

    # Return as bytes
    return json_text.encode('utf-8')