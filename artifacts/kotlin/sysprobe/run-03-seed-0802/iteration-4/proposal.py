from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and keys
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    FIELD_NAMES = ['"id"', '"amount"', '"name"', '"status"', '"tags"', '"child"']

    # Helper: produce a JSON string literal from a Python string (escape minimal)
    def json_str(s: str) -> str:
        # minimal escaping for quotes and backslash
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Strategy for "id": integer or null or string number or missing
    # id is integer, non-nullable, but Gson/Jackson accept null or missing
    # We vary: int, null, string number, missing
    id_variant = draw(st.integers(min_value=0, max_value=2**31-1))
    id_type = draw(st.sampled_from(['int', 'null', 'string', 'missing']))
    if id_type == 'int':
        id_json = str(id_variant)
        id_present = True
    elif id_type == 'null':
        id_json = 'null'
        id_present = True
    elif id_type == 'string':
        id_json = json_str(str(id_variant))
        id_present = True
    else:  # missing
        id_json = None
        id_present = False

    # Strategy for "amount": string, but can try int or null or missing
    # Known: Gson/Moshi accept number coercion to string; kotlinx rejects; Jackson accepts coercion except null
    amount_type = draw(st.sampled_from(['string', 'int', 'null', 'missing']))
    if amount_type == 'string':
        amount_val = draw(st.text(min_size=0, max_size=10))
        amount_json = json_str(amount_val)
        amount_present = True
    elif amount_type == 'int':
        amount_val = draw(st.integers(min_value=0, max_value=100000))
        amount_json = str(amount_val)
        amount_present = True
    elif amount_type == 'null':
        amount_json = 'null'
        amount_present = True
    else:
        amount_json = None
        amount_present = False

    # Strategy for "name": string or null or missing
    # name is nullable string, so null accepted by all; missing accepted by Gson/Jackson
    name_type = draw(st.sampled_from(['string', 'null', 'missing']))
    if name_type == 'string':
        name_val = draw(st.text(min_size=0, max_size=10))
        name_json = json_str(name_val)
        name_present = True
    elif name_type == 'null':
        name_json = 'null'
        name_present = True
    else:
        name_json = None
        name_present = False

    # Strategy for "status": enum string, or unknown string, or null, or missing
    # Known: Gson accepts unknown as null; others reject unknown or case variant; Gson accepts null as null; others reject null
    status_type = draw(st.sampled_from(['valid_enum', 'unknown_enum', 'case_variant', 'null', 'missing']))
    if status_type == 'valid_enum':
        status_json = draw(st.sampled_from(STATUS_VALUES))
        status_present = True
    elif status_type == 'unknown_enum':
        # unknown string not in enum, e.g. "pending"
        status_json = json_str('pending')
        status_present = True
    elif status_type == 'case_variant':
        # case variant of valid enum, e.g. "Active"
        status_json = json_str('Active')
        status_present = True
    elif status_type == 'null':
        status_json = 'null'
        status_present = True
    else:
        status_json = None
        status_present = False

    # Strategy for "tags": array of strings, or null, or missing
    # Known: Gson accepts null; Jackson rejects null; Moshi/kotlinx reject null; missing accepted by Gson/Jackson
    tags_type = draw(st.sampled_from(['array', 'null', 'missing']))
    if tags_type == 'array':
        # array of 0-3 strings
        tags_len = draw(st.integers(min_value=0, max_value=3))
        tags_elems = [json_str(draw(st.text(min_size=0, max_size=5))) for _ in range(tags_len)]
        tags_json = '[' + ','.join(tags_elems) + ']'
        tags_present = True
    elif tags_type == 'null':
        tags_json = 'null'
        tags_present = True
    else:
        tags_json = None
        tags_present = False

    # Recursive child: either null, missing, or a nested record with same schema but no further recursion (depth 1)
    # Known: nested fields behave like top-level; Gson/Jackson accept null/missing; Moshi/kotlinx reject null/missing
    child_type = draw(st.sampled_from(['null', 'missing', 'object']))
    if child_type == 'null':
        child_json = 'null'
        child_present = True
    elif child_type == 'missing':
        child_json = None
        child_present = False
    else:
        # nested object with all fields present and valid (to avoid broad rejection)
        # id int present
        nid = draw(st.integers(min_value=0, max_value=1000))
        namount = json_str(draw(st.text(min_size=1, max_size=5)))
        nname = json_str(draw(st.text(min_size=1, max_size=5)))
        nstatus = draw(st.sampled_from(STATUS_VALUES))
        ntags_len = draw(st.integers(min_value=0, max_value=2))
        ntags = [json_str(draw(st.text(min_size=0, max_size=5))) for _ in range(ntags_len)]
        ntags_json = '[' + ','.join(ntags) + ']'
        # child inside child is always null to avoid deep recursion
        nchild_json = 'null'
        child_json = (
            '{'
            + '"id":' + str(nid) + ','
            + '"amount":' + namount + ','
            + '"name":' + nname + ','
            + '"status":' + nstatus + ','
            + '"tags":' + ntags_json + ','
            + '"child":' + nchild_json
            + '}'
        )
        child_present = True

    # Compose fields in random order, including only present fields
    fields = []
    if id_present:
        fields.append('"id":' + id_json)
    if amount_present:
        fields.append('"amount":' + amount_json)
    if name_present:
        fields.append('"name":' + name_json)
    if status_present:
        fields.append('"status":' + status_json)
    if tags_present:
        fields.append('"tags":' + tags_json)
    if child_present:
        fields.append('"child":' + child_json)

    # Shuffle fields order to vary key order (all accept duplicate keys last wins, but we do not add duplicates here)
    draw(st.permutations(fields))  # just to consume draw, but we want to shuffle fields
    # Actually shuffle fields:
    import random
    random.shuffle(fields)

    json_text = '{' + ','.join(fields) + '}'
    return json_text.encode('utf-8')