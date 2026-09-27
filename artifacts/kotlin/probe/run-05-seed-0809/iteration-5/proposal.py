from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and tags
    STATUS_VALUES = ["active", "inactive", "unknown"]
    
    # Helper to produce a JSON string literal with proper escaping for simple ASCII subset
    # We only generate simple strings without control chars to keep it safe
    def json_string(s: str) -> str:
        # Escape backslash and double quote only for safety
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return '"' + s + '"'
    
    # Generate a JSON string or null for "name"
    # We allow null or string (including empty string)
    name_strategy = st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20).filter(lambda s: all(32 <= ord(c) <= 126 and c not in ['\\', '"'] for c in s))
    )
    
    # Generate "status" field variants:
    # - valid enum string
    # - null (Gson accepts, others reject)
    # - invalid string (Moshi, kotlinx, Jackson reject; Gson accepts with null)
    # - missing (not allowed by schema, but test missing to see if any accept)
    status_strategy = st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.none(),
        st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES and all(32 <= ord(c) <= 126 for c in s)),
        st.just(None)  # for missing, we handle separately
    )
    
    # Generate "id" field variants:
    # - integer (normal)
    # - string integer (e.g. "1")
    # - string non-integer (should cause rejection)
    # - number float (should cause rejection)
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=10**6),
        st.integers(min_value=0, max_value=10**6).map(lambda i: str(i)),
        st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()),
        st.floats(allow_infinity=False, allow_nan=False).map(lambda f: f if f == int(f) else f)
    )
    
    # Generate "amount" field variants:
    # - string (normal)
    # - number (Gson, Moshi, Jackson accept and coerce; kotlinx rejects)
    # - string number convertible
    # - string non-number (should be accepted as string)
    amount_strategy = st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in ['\\', '"'] for c in s)),
        st.floats(allow_infinity=False, allow_nan=False).map(lambda f: f if f == int(f) else f),
        st.integers(min_value=0, max_value=10**6).map(str)
    )
    
    # Generate "tags" array variants:
    # - array of strings (normal)
    # - array of mixed types (int, null, string) (Gson, Moshi, Jackson accept; kotlinx rejects)
    # - array of nulls (Gson, Moshi, Jackson accept; kotlinx rejects)
    # - string instead of array (all reject)
    # - empty array
    tag_element_str = st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 and c not in ['\\', '"'] for c in s))
    tag_element_mixed = st.one_of(
        tag_element_str,
        st.integers(min_value=0, max_value=1000),
        st.none()
    )
    tags_strategy = st.one_of(
        st.lists(tag_element_str, min_size=0, max_size=5),
        st.lists(tag_element_mixed, min_size=0, max_size=5),
        st.just("not_an_array")  # string instead of array
    )
    
    # Recursive child record generator with bounded depth (max 1 level)
    # We produce either null or a full record with no further child (child=null)
    # To avoid infinite recursion, child.child is always null
    def gen_child():
        # child is either null or a record with child=null
        # We reuse the same strategies but fix child=null to avoid recursion
        id_val = draw(id_strategy)
        amount_val = draw(amount_strategy)
        name_val = draw(name_strategy)
        status_val = draw(status_strategy)
        tags_val = draw(tags_strategy)
        
        # Compose child JSON text with child=null (no further recursion)
        # We will produce JSON text for child here
        def render_value(v):
            if v is None:
                return "null"
            elif isinstance(v, str):
                # If v is the special string "not_an_array" for tags, output as string
                if v == "not_an_array":
                    return json_string(v)
                else:
                    return json_string(v)
            elif isinstance(v, int):
                return str(v)
            elif isinstance(v, float):
                # JSON floats: use repr to avoid scientific notation if possible
                return repr(v)
            elif isinstance(v, list):
                # list of elements
                elems = [render_value(e) for e in v]
                return "[" + ",".join(elems) + "]"
            else:
                # fallback to string
                return json_string(str(v))
        
        # Compose child JSON with child=null
        child_json = (
            '{'
            + '"id":' + render_value(id_val) + ','
            + '"amount":' + render_value(amount_val) + ','
            + '"name":' + render_value(name_val) + ','
            + '"status":' + render_value(status_val) + ','
            + '"tags":' + render_value(tags_val) + ','
            + '"child":null'
            + '}'
        )
        return child_json
    
    # Compose top-level record
    # We vary one or two fields to produce divergence, mostly one at a time
    # We pick a "variation mode" to decide which field(s) to vary
    variation_mode = draw(st.sampled_from([
        "id_type",
        "amount_type",
        "name_type",
        "status_value",
        "tags_type",
        "child_null_or_empty",
        "extra_field",
        "missing_field",
        "child_variation",
        "tags_elements_nulls",
    ]))
    
    # Base valid values for fields (to use when not varying)
    base_id = 123
    base_amount = "42.50"
    base_name = "Alice"
    base_status = "active"
    base_tags = ["tag1", "tag2"]
    base_child = None  # null
    
    # Helper to render JSON values
    def render_value(v):
        if v is None:
            return "null"
        elif isinstance(v, str):
            return json_string(v)
        elif isinstance(v, int):
            return str(v)
        elif isinstance(v, float):
            return repr(v)
        elif isinstance(v, list):
            elems = [render_value(e) for e in v]
            return "[" + ",".join(elems) + "]"
        else:
            return json_string(str(v))
    
    # Compose fields depending on variation mode
    # We produce strings for each field, then join with commas
    # We keep all fields present except in "missing_field" mode
    # In "extra_field" mode, add an unknown extra field (Gson, Moshi, Jackson accept; kotlinx, Jackson reject)
    # In "child_null_or_empty" mode, child is either null or empty object (Gson accepts empty object, others reject)
    
    # Start with base values
    id_val = base_id
    amount_val = base_amount
    name_val = base_name
    status_val = base_status
    tags_val = base_tags
    child_val = None
    extra_field = None
    missing_field = None
    
    # Apply variation
    if variation_mode == "id_type":
        # id as int, string int, string non-int, float
        id_val = draw(id_strategy)
    elif variation_mode == "amount_type":
        amount_val = draw(amount_strategy)
    elif variation_mode == "name_type":
        name_val = draw(name_strategy)
        # Also try number for name (Gson, Moshi, Jackson accept; kotlinx rejects)
        # We do this by sometimes drawing int and converting to string or number literal
        if draw(st.booleans()):
            # 50% chance to produce number literal (int)
            n = draw(st.integers(min_value=0, max_value=1000))
            # Represent as number literal (no quotes)
            name_val = n
    elif variation_mode == "status_value":
        status_val = draw(status_strategy)
    elif variation_mode == "tags_type":
        tags_val = draw(tags_strategy)
    elif variation_mode == "child_null_or_empty":
        # child null or empty object {}
        if draw(st.booleans()):
            child_val = "null"
        else:
            child_val = "{}"  # Gson accepts, others reject
    elif variation_mode == "extra_field":
        extra_field = '"extra_field":123'
    elif variation_mode == "missing_field":
        # randomly omit one required field except child (which can be null)
        missing_field = draw(st.sampled_from(["id", "amount", "name", "status", "tags"]))
    elif variation_mode == "child_variation":
        # child is either null or a record with child=null, with some variation inside child
        child_val = gen_child()
    elif variation_mode == "tags_elements_nulls":
        # tags array with null elements or mixed types (Gson, Moshi, Jackson accept; kotlinx rejects)
        tags_val = draw(st.lists(st.one_of(st.none(), st.integers(min_value=0, max_value=10), st.text(min_size=1, max_size=5)), min_size=1, max_size=5))
    else:
        # fallback to base values
        pass
    
    # Compose JSON fields as strings
    fields = []
    
    def add_field(name, val):
        if val == "null":
            fields.append(f'"{name}":null')
        elif isinstance(val, str):
            # If val looks like JSON object or array or number literal, output as is
            # else output as JSON string literal
            val_strip = val.strip()
            if val_strip.startswith("{") or val_strip.startswith("[") or val_strip in ["null", "true", "false"]:
                fields.append(f'"{name}":{val_strip}')
            else:
                # Try to detect if val is a number literal (int or float)
                try:
                    float(val_strip)
                    fields.append(f'"{name}":{val_strip}')
                except Exception:
                    fields.append(f'"{name}":{json_string(val)}')
        elif isinstance(val, int) or isinstance(val, float):
            fields.append(f'"{name}":{val}')
        elif isinstance(val, list):
            # Compose array elements as JSON strings
            elems = []
            for e in val:
                if e is None:
                    elems.append("null")
                elif isinstance(e, int) or isinstance(e, float):
                    elems.append(str(e))
                else:
                    elems.append(json_string(str(e)))
            fields.append(f'"{name}":[{",".join(elems)}]')
        elif val is None:
            fields.append(f'"{name}":null')
        else:
            # fallback to string literal
            fields.append(f'"{name}":{json_string(str(val))}')
    
    # Add fields except missing_field
    if missing_field != "id":
        add_field("id", id_val)
    if missing_field != "amount":
        add_field("amount", amount_val)
    if missing_field != "name":
        add_field("name", name_val)
    if missing_field != "status":
        add_field("status", status_val)
    if missing_field != "tags":
        add_field("tags", tags_val)
    
    # Add child field
    if child_val is None:
        add_field("child", None)
    else:
        # child_val is either JSON string or "null"
        if isinstance(child_val, str):
            # child_val is JSON text or "null"
            if child_val == "null":
                fields.append('"child":null')
            else:
                fields.append(f'"child":{child_val}')
        else:
            add_field("child", child_val)
    
    # Add extra field if any
    if extra_field is not None:
        fields.append(extra_field)
    
    # Compose final JSON text
    json_text = "{" + ",".join(fields) + "}"
    
    return json_text.encode("utf-8")