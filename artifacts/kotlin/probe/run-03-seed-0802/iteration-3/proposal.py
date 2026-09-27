from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum and known divergence points
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # We allow null for name and child, but status null accepted only by Gson
    # We will produce mostly well-formed documents with one or two subtle divergences
    
    # Helper: produce a JSON string literal with proper escaping for simple ASCII only
    def json_string(s: str) -> str:
        # Escape backslash and quote only for simplicity
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    # id: integer or string containing integer (all accept both)
    # Occasionally produce id as string with leading zeros or plus sign to test boundaries
    def id_strategy():
        # Mostly integer number, sometimes string number with subtle variants
        base_int = st.integers(min_value=0, max_value=10**6)
        id_as_num = base_int.map(str)
        id_as_str = base_int.flatmap(lambda i: st.sampled_from([
            str(i),
            f"{i:0>6}",  # zero padded
            f"+{i}",     # plus sign
        ])).map(lambda s: json_string(s))
        # Mix number or string number, mostly number
        return st.one_of(
            id_as_num,
            id_as_str,
        )
    
    # amount: string or number (kotlinx rejects number)
    # We produce mostly string, sometimes number to trigger divergence
    def amount_strategy():
        # Amount as decimal string or number
        # Use strings that look like numbers, or numbers directly
        amount_num = st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False).map(lambda f: ('%.2f' % f).rstrip('0').rstrip('.') if '.' in ('%.2f' % f) else str(int(f)))
        amount_num_json = amount_num
        amount_str_json = amount_num.map(json_string)
        # Mix string or number, with bias to string (to keep mostly accepted)
        return st.one_of(
            amount_str_json,
            amount_num_json,
        )
    
    # name: string, null, or number (kotlinx rejects number)
    # We produce mostly string or null, sometimes number to trigger divergence
    def name_strategy():
        # Simple ASCII strings or null or number
        name_str = st.text(min_size=1, max_size=20).map(json_string)
        name_null = st.just("null")
        name_num = st.integers(min_value=-1000, max_value=1000).map(str)
        # Mix with bias to string and null
        return st.one_of(
            name_str,
            name_null,
            name_num,
        )
    
    # status: must be one of three strings or null (Gson accepts null, others reject)
    # Also test unknown string (Gson accepts as null, others reject)
    def status_strategy():
        # Mostly valid enum strings
        valid = st.sampled_from(STATUS_VALUES)
        null_val = st.just("null")
        unknown_str = st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string)
        # Mix mostly valid, sometimes null, sometimes unknown string
        return st.one_of(
            valid,
            null_val,
            unknown_str,
        )
    
    # tags: array of strings normally, but test non-string elements (kotlinx rejects non-string)
    # Also test empty array, array with null, array with number, array with mixed types
    def tags_strategy():
        # String elements
        str_elem = st.text(min_size=1, max_size=10).map(json_string)
        # Non-string elements: null, number, boolean
        null_elem = st.just("null")
        num_elem = st.integers(min_value=-100, max_value=100).map(str)
        bool_elem = st.sampled_from(["true", "false"])
        # Build arrays with mostly strings, sometimes one non-string element
        # Also test empty array
        def array_with_nonstring():
            # Choose one non-string element type
            non_str = st.one_of(null_elem, num_elem, bool_elem)
            # Build array with 1 to 5 elements, one of which is non-string
            def build_array(nonstring_idx):
                def elems():
                    for i in range(5):
                        if i == nonstring_idx:
                            yield non_str
                        else:
                            yield str_elem
                return st.tuples(*elems()).map(lambda t: "[" + ",".join(t) + "]")
            return st.integers(min_value=0, max_value=4).flatmap(build_array)
        
        # Mostly string arrays or empty, sometimes with one non-string element
        return st.one_of(
            st.lists(str_elem, min_size=0, max_size=5).map(lambda l: "[" + ",".join(l) + "]"),
            array_with_nonstring(),
        )
    
    # child: null or nested record (one level recursion)
    # Nested record mostly well-formed, but occasionally missing fields or empty object (Gson accepts empty object as child)
    # We limit recursion depth to 1
    def child_strategy():
        # null or nested record
        # Nested record fields same as top-level but no further child (child=null)
        def nested_record():
            # id nested: integer or string number
            nested_id = id_strategy()
            # amount nested: string or number
            nested_amount = amount_strategy()
            # name nested: string, null, or number
            nested_name = name_strategy()
            # status nested: valid enum only (to reduce complexity)
            nested_status = st.sampled_from(STATUS_VALUES)
            # tags nested: array of strings only (to reduce complexity)
            nested_tags = st.lists(st.text(min_size=1, max_size=10).map(json_string), min_size=0, max_size=3).map(lambda l: "[" + ",".join(l) + "]")
            # child nested: always null (no deeper recursion)
            nested_child = st.just("null")
            
            # Compose nested record JSON text
            def make_nested(id_, amount_, name_, status_, tags_, child_):
                # Compose fields with commas
                fields = [
                    '"id":' + id_,
                    '"amount":' + amount_,
                    '"name":' + name_,
                    '"status":' + status_,
                    '"tags":' + tags_,
                    '"child":' + child_,
                ]
                return "{" + ",".join(fields) + "}"
            
            return st.tuples(nested_id, nested_amount, nested_name, nested_status, nested_tags, nested_child).map(
                lambda t: make_nested(*t)
            )
        
        # Also produce empty object {} occasionally (Gson accepts, others reject)
        empty_obj = st.just("{}")
        return st.one_of(
            st.just("null"),
            nested_record(),
            empty_obj,
        )
    
    # Compose top-level record JSON text
    id_ = draw(id_strategy())
    amount_ = draw(amount_strategy())
    name_ = draw(name_strategy())
    status_ = draw(status_strategy())
    tags_ = draw(tags_strategy())
    child_ = draw(child_strategy())
    
    # Compose fields with commas
    fields = [
        '"id":' + id_,
        '"amount":' + amount_,
        '"name":' + name_,
        '"status":' + status_,
        '"tags":' + tags_,
        '"child":' + child_,
    ]
    
    # Occasionally add one unknown extra field (Gson and Moshi accept, kotlinx and Jackson reject)
    add_unknown = draw(st.booleans())
    if add_unknown:
        # Add a simple unknown field with string value
        unknown_field = '"unknown_extra":' + json_string("extra")
        fields.append(unknown_field)
    
    # Occasionally duplicate a key once (last wins)
    add_duplicate = draw(st.booleans())
    if add_duplicate:
        # Pick a field to duplicate
        dup_field = draw(st.sampled_from(["id", "amount", "name", "status", "tags", "child"]))
        # Generate a second value for that field (different from first)
        if dup_field == "id":
            dup_value = draw(id_strategy())
        elif dup_field == "amount":
            dup_value = draw(amount_strategy())
        elif dup_field == "name":
            dup_value = draw(name_strategy())
        elif dup_field == "status":
            dup_value = draw(status_strategy())
        elif dup_field == "tags":
            dup_value = draw(tags_strategy())
        elif dup_field == "child":
            dup_value = draw(child_strategy())
        else:
            dup_value = '"dup"'
        # Append duplicate field at end
        fields.append(f'"{dup_field}":{dup_value}')
    
    json_text = "{" + ",".join(fields) + "}"
    return json_text.encode("utf-8")