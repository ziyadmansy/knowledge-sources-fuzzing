from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and fields
    STATUS_VALUES = ["active", "inactive", "unknown"]
    
    # Helper: JSON string escaper for simple strings (no control chars, no unicode escapes)
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    # Strategy for "id": accept int or stringified int (both accepted by all)
    id_val = draw(st.one_of(
        st.integers(min_value=0, max_value=10**9),
        st.integers(min_value=0, max_value=10**9).map(lambda i: str(i))
    ))
    id_json = json_string(str(id_val)) if isinstance(id_val, str) else str(id_val)
    
    # Strategy for "amount": 
    # Known divergence: 
    # - Gson, Moshi, Jackson accept number or string for amount (string field)
    # - kotlinx.serialization rejects number for amount
    # So we try to produce number or string here to cause divergence.
    amount_val = draw(st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)),  # safe ascii string
        st.integers(min_value=0, max_value=10**9).map(str),  # stringified number
        st.integers(min_value=0, max_value=10**9),  # number (to cause divergence)
    ))
    if isinstance(amount_val, int):
        amount_json = str(amount_val)
    else:
        amount_json = json_string(amount_val)
    
    # Strategy for "name":
    # Known divergence:
    # - Gson, Moshi, Jackson accept non-string (number or bool) converting to string
    # - kotlinx.serialization rejects non-string
    # So produce string, null, number, or boolean
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
    ))
    if name_val is None:
        name_json = "null"
    elif isinstance(name_val, str):
        name_json = json_string(name_val)
    elif isinstance(name_val, bool):
        name_json = "true" if name_val else "false"
    else:
        # number
        name_json = str(name_val)
    
    # Strategy for "status":
    # Known divergence:
    # - Gson accepts invalid enum values and null as null
    # - Others reject invalid enum or null
    # So produce valid enum, invalid enum string, or null
    status_val = draw(st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES),
        st.none(),
    ))
    if status_val is None:
        status_json = "null"
    else:
        status_json = json_string(status_val)
    
    # Strategy for "tags":
    # Known divergence:
    # - All reject non-array tags
    # - Gson, Moshi, Jackson accept non-string elements converting to string
    # - kotlinx.serialization rejects non-string elements
    # So produce array of strings or array with some non-string elements
    # Also test empty array and small arrays
    def tag_element():
        return draw(st.one_of(
            st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)),
            st.integers(min_value=-10, max_value=10),
            st.booleans(),
            st.none(),
        ))
    tags_len = draw(st.integers(min_value=0, max_value=3))
    tags_vals = [draw(tag_element()) for _ in range(tags_len)]
    
    def json_val(v):
        if v is None:
            return "null"
        elif isinstance(v, str):
            return json_string(v)
        elif isinstance(v, bool):
            return "true" if v else "false"
        else:
            return str(v)
    tags_json = "[" + ",".join(json_val(v) for v in tags_vals) + "]"
    
    # Strategy for "child":
    # Known divergence:
    # - Gson accepts empty object for child, filling missing fields with defaults/nulls
    # - Others reject empty object child
    # - Gson and Moshi accept missing optional child in nested records (default null)
    # - kotlinx.serialization rejects missing fields in nested child
    # - Jackson accepts missing child
    # So child can be:
    # - null
    # - missing (we will handle missing by omitting the field)
    # - empty object {}
    # - well-formed child record (one level recursion)
    # Limit recursion depth to 1
    
    # We will produce child as either:
    # - null
    # - empty object {}
    # - well-formed child record with all fields present (id, amount, name, status, tags, child=null)
    # - missing (handled by omitting the field)
    
    child_option = draw(st.sampled_from(["null", "empty", "full", "missing"]))
    
    if child_option == "missing":
        child_json = None  # omit field
    elif child_option == "null":
        child_json = "null"
    elif child_option == "empty":
        child_json = "{}"
    else:
        # full child record with all fields present, child=null to avoid recursion
        # reuse strategies for fields but simpler (no recursion)
        child_id = draw(st.one_of(
            st.integers(min_value=0, max_value=10**9),
            st.integers(min_value=0, max_value=10**9).map(str)
        ))
        child_id_json = json_string(str(child_id)) if isinstance(child_id, str) else str(child_id)
        
        child_amount = draw(st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)),
            st.integers(min_value=0, max_value=10**9).map(str),
            st.integers(min_value=0, max_value=10**9),
        ))
        if isinstance(child_amount, int):
            child_amount_json = str(child_amount)
        else:
            child_amount_json = json_string(child_amount)
        
        child_name = draw(st.one_of(
            st.none(),
            st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)),
            st.integers(min_value=-1000, max_value=1000),
            st.booleans(),
        ))
        if child_name is None:
            child_name_json = "null"
        elif isinstance(child_name, str):
            child_name_json = json_string(child_name)
        elif isinstance(child_name, bool):
            child_name_json = "true" if child_name else "false"
        else:
            child_name_json = str(child_name)
        
        child_status = draw(st.sampled_from(STATUS_VALUES))
        child_status_json = json_string(child_status)
        
        child_tags_len = draw(st.integers(min_value=0, max_value=3))
        child_tags_vals = [draw(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s))) for _ in range(child_tags_len)]
        child_tags_json = "[" + ",".join(json_string(v) for v in child_tags_vals) + "]"
        
        # child.child is null (no recursion)
        child_child_json = "null"
        
        child_json = (
            "{" +
            f'"id":{child_id_json},' +
            f'"amount":{child_amount_json},' +
            f'"name":{child_name_json},' +
            f'"status":{child_status_json},' +
            f'"tags":{child_tags_json},' +
            f'"child":{child_child_json}' +
            "}"
        )
    
    # Compose root object fields
    # Known divergence:
    # - Gson and Moshi accept extra unknown fields, others reject
    # We add an optional unknown field sometimes to cause divergence
    add_unknown = draw(st.booleans())
    unknown_field_json = ''
    if add_unknown:
        # safe ascii key and value
        unknown_key = draw(st.text(min_size=1, max_size=5).filter(lambda s: all(c.isalpha() for c in s)))
        unknown_val = draw(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 and c not in '"\\' for c in s)))
        unknown_field_json = f',"{unknown_key}":{json_string(unknown_val)}'
    
    # Build fields list, omit child if missing
    fields = [
        f'"id":{id_json}',
        f'"amount":{amount_json}',
        f'"name":{name_json}',
        f'"status":{status_json}',
        f'"tags":{tags_json}',
    ]
    if child_json is not None:
        fields.append(f'"child":{child_json}')
    
    # Add unknown field if present
    if unknown_field_json:
        fields.append(unknown_field_json[1:])  # remove leading comma, add as separate field
    
    # Join fields with commas
    json_text = "{" + ",".join(fields) + "}"
    
    return json_text.encode("utf-8")