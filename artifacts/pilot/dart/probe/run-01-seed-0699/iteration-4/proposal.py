```python
from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ['active', 'inactive', 'unknown']

    # Helper: produce a JSON string literal with proper escaping of " and \
    def json_string(s: str) -> str:
        # Minimal escaping for " and \ only, enough for these tests
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Recursive record generator with bounded depth (max 1 level of recursion)
    def record(depth=0):
        # id: integer
        id_val = draw(st.integers(min_value=0, max_value=2**31-1))
        # amount: string (non-empty to avoid trivial edge)
        amount_val = draw(st.text(min_size=1, max_size=10))
        # name: string or null
        name_val = draw(st.one_of(st.none(), st.text(max_size=10)))
        # status: enum string
        status_val = draw(st.sampled_from(STATUS_VALUES))
        # tags: array of strings (empty strings allowed, no nulls)
        tags_len = draw(st.integers(min_value=0, max_value=3))
        tags_val = draw(st.lists(st.text(max_size=5), min_size=tags_len, max_size=tags_len))
        # child: null or record (only one level recursion)
        if depth == 0:
            child_val = draw(st.one_of(st.none(), record(depth=1)))
        else:
            child_val = None

        # Build JSON text for this record
        # Compose fields in fixed order for readability
        parts = []
        parts.append('"id":' + str(id_val))
        parts.append('"amount":' + json_string(amount_val))
        if name_val is None:
            parts.append('"name":null')
        else:
            parts.append('"name":' + json_string(name_val))
        parts.append('"status":' + json_string(status_val))
        # tags array
        tags_json = '[' + ','.join(json_string(t) for t in tags_val) + ']'
        parts.append('"tags":' + tags_json)
        # child
        if child_val is None:
            parts.append('"child":null')
        else:
            parts.append('"child":' + child_val)

        return '{' + ','.join(parts) + '}'

    # Strategy to produce a mostly valid record JSON string, then
    # apply a single targeted mutation to one field to try to induce divergence.

    base_record = record()

    # Mutations to try (one per generated document):
    # - id: replace integer with string integer (should reject all)
    # - id: replace integer with float (should reject all)
    # - amount: replace string with integer (reject all)
    # - amount: replace string with empty string (valid)
    # - name: replace string/null with integer (reject all)
    # - status: replace enum with invalid string (reject all)
    # - status: replace enum with valid enum but uppercase (reject all)
    # - tags: replace one string with integer (reject all)
    # - tags: replace one string with null (reject all)
    # - tags: empty array (accept all)
    # - child: null (accept all)
    # - child: missing (not allowed, always present)
    # - child: empty object (reject all)
    # - child: valid record (accept all)
    # - child: invalid status (reject all)
    # - duplicate keys in child (last wins, accept all)
    # - extra unknown fields (accept all)
    # - subtle type boundary: id as float with .0 (reject all)
    # - subtle type boundary: amount as string "0" (accept all)
    # - subtle type boundary: tags array with empty string (accept all)
    # - subtle type boundary: name as empty string (accept all)

    # To maximize chance of divergence, try:
    # - Omit "child" field (not allowed, all reject)
    # - Replace "child" with null or valid record (both accepted)
    # - Replace "child" with empty object (reject all)
    # - Replace "status" with invalid enum string (reject all)
    # - Replace "status" with valid enum but uppercase (reject all)
    # - Replace "tags" with array containing null (reject all)
    # - Replace "tags" with array containing integer (reject all)
    # - Replace "id" with string integer (reject all)
    # - Replace "id" with float (reject all)
    # - Replace "amount" with integer (reject all)
    # - Replace "name" with integer (reject all)
    # - Duplicate keys in child (last wins, accept all)
    # - Extra unknown fields (accept all)

    # We want to produce syntactically valid JSON always.

    # We'll implement a small mutation function that takes the base JSON string,
    # parses it minimally by string ops (since no json import allowed),
    # and replaces one field's value with a chosen mutation.

    # Instead, build the JSON from scratch with one mutation applied.

    # Define a helper to build the record with a mutation on a single field at top level or in child.

    # Mutation types:
    MUTATION_TYPES = st.sampled_from([
        "id_string_int",       # id as string integer (e.g. "123")
        "id_float",            # id as float (e.g. 123.0)
        "amount_int",          # amount as integer
        "name_int",            # name as integer
        "status_invalid",      # status invalid string
        "status_uppercase",    # status uppercase valid enum
        "tags_with_int",       # tags array contains integer
        "tags_with_null",      # tags array contains null
        "child_empty_object",  # child is empty object
        "child_invalid_status",# child.status invalid
        "child_duplicate_keys",# child with duplicate keys, last wins
        "extra_unknown_field", # extra unknown field at top level
        "no_mutation"          # no mutation, fully valid
    ])

    mutation = draw(MUTATION_TYPES)

    # Generate base fields normally
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    amount_val = draw(st.text(min_size=1, max_size=10))
    name_val = draw(st.one_of(st.none(), st.text(max_size=10)))
    status_val = draw(st.sampled_from(STATUS_VALUES))
    tags_len = draw(st.integers(min_value=0, max_value=3))
    tags_val = draw(st.lists(st.text(max_size=5), min_size=tags_len, max_size=tags_len))
    child_present = draw(st.booleans())
    if child_present:
        # child record with valid fields
        child_id = draw(st.integers(min_value=0, max_value=2**31-1))
        child_amount = draw(st.text(min_size=1, max_size=10))
        child_name = draw(st.one_of(st.none(), st.text(max_size=10)))
        child_status = draw(st.sampled_from(STATUS_VALUES))
        child_tags_len = draw(st.integers(min_value=0, max_value=3))
        child_tags = draw(st.lists(st.text(max_size=5), min_size=child_tags_len, max_size=child_tags_len))
    else:
        child_id = None

    # Apply mutations:

    # id field
    if mutation == "id_string_int":
        id_json = json_string(str(id_val))
    elif mutation == "id_float":
        id_json = str(float(id_val))  # e.g. 123.0
    else:
        id_json = str(id_val)

    # amount field
    if mutation == "amount_int":
        amount_json = str(draw(st.integers(min_value=0, max_value=10000)))
    else:
        amount_json = json_string(amount_val)

    # name field
    if mutation == "name_int":
        name_json = str(draw(st.integers(min_value=0, max_value=10000)))
    else:
        if name_val is None:
            name_json = "null"
        else:
            name_json = json_string(name_val)

    # status field
    if mutation == "status_invalid":
        status_json = json_string("invalid_status")
    elif mutation == "status_uppercase":
        status_json = json_string(status_val.upper())
    else:
        status_json = json_string(status_val)

    # tags field
    if mutation == "tags_with_int":
        # Insert an integer in tags array
        if tags_len == 0:
            tags_json = '[0]'
        else:
            # Replace first element with integer 0
            tags_json = '[' + '0,' + ','.join(json_string(t) for t in tags_val[1:]) + ']'
    elif mutation == "tags_with_null":
        # Insert null in tags array
        if tags_len == 0:
            tags_json = '[null]'
        else:
            tags_json = '[null,' + ','.join(json_string(t) for t in tags_val[1:]) + ']'
    else:
        tags_json = '[' + ','.join(json_string(t) for t in tags_val) + ']'

    # child field
    if mutation == "child_empty_object":
        child_json = '{}'
    elif mutation == "child_invalid_status":
        # Build child with invalid status
        if child_present:
            c_id = child_id
            c_amount = child_amount
            c_name = child_name
            c_tags = child_tags
            # Compose child JSON with invalid status
            parts = []
            parts.append('"id":' + str(c_id))
            parts.append('"amount":' + json_string(c_amount))
            if c_name is None:
                parts.append('"name":null')
            else:
                parts.append('"name":' + json_string(c_name))
            parts.append('"status":' + json_string("invalid_status"))
            parts.append('"tags":[' + ','.join(json_string(t) for t in c_tags) + ']')
            parts.append('"child":null')
            child_json = '{' + ','.join(parts) + '}'
        else:
            # no child present, so just null
            child_json = 'null'
    elif mutation == "child_duplicate_keys":
        # Build child with duplicate keys, last wins
        if child_present:
            c_id = child_id
            c_amount = child_amount
            c_name = child_name
            c_status = child_status
            c_tags = child_tags
            # Compose child JSON with duplicate "id" and "name"
            parts = []
            parts.append('"id":' + str(c_id))
            parts.append('"id":' + str(c_id + 1))  # duplicate id, last wins
            parts.append('"amount":' + json_string(c_amount))
            if c_name is None:
                parts.append('"name":null')
                parts.append('"name":' + json_string("dup_name"))  # duplicate name, last wins
            else:
                parts.append('"name":' + json_string(c_name))
                parts.append('"name":' + json_string("dup_name"))  # duplicate name, last wins
            parts.append('"status":' + json_string(c_status))
            parts.append('"tags":[' + ','.join(json_string(t) for t in c_tags) + ']')
            parts.append('"child":null')
            child_json = '{' + ','.join(parts) + '}'
        else:
            child_json = 'null