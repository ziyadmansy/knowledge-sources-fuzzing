from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslashes only (minimal safe subset)
def json_escape(s: str) -> str:
    # minimal escaping for JSON string: backslash and double quote
    return s.replace("\\", "\\\\").replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects matching the schema with subtle
    variations designed to trigger behavioral divergence among four Dart JSON deserializers.

    Schema:
    {
      "id": <integer>,
      "amount": <string>,
      "name": <string or null>,
      "status": <"active"|"inactive"|"unknown">,
      "tags": <array of strings>,
      "child": <Record or null, one level recursion>
    }

    Variations:
    - id: sometimes int, sometimes float (to trigger manual/built_value strictness vs json_serializable/freezed leniency)
    - amount: always string (valid)
    - name: present always (manual requires present), sometimes null, sometimes string
    - status: mostly valid enum strings, sometimes invalid strings to trigger enum errors
    - tags: list of strings, sometimes empty, sometimes with empty strings
    - child: null or one nested record (depth=1 only)
    - Occasionally omit nullable fields (name, child) to trigger built_value tolerance vs manual/json_serializable/freezed rejection
    """

    # --- id field ---
    # Manual and built_value require int strictly.
    # json_serializable and freezed accept any num and convert to int.
    # So generate either int or float with fractional part to cause divergence.
    id_is_int = draw(st.booleans())
    if id_is_int:
        id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    else:
        # float with fractional part to cause manual/built_value rejection
        # but json_serializable/freezed accept and convert .toInt()
        # Use float with fractional part > 0
        id_val = draw(st.floats(min_value=0, max_value=2**31-1, allow_nan=False, allow_infinity=False)).__round__(3)
        # Ensure fractional part is nonzero
        if float(int(id_val)) == id_val:
            id_val += 0.1

    # --- amount field ---
    # Always string, non-empty
    amount_val = draw(st.text(min_size=1, max_size=10)).replace('"', '')  # avoid quotes inside string

    # --- name field ---
    # Manual requires present (nullable)
    # built_value tolerates missing (sets null)
    # json_serializable/freezed tolerate missing (nullable)
    # So sometimes omit name to cause divergence
    omit_name = draw(st.booleans())
    if not omit_name:
        # present: either null or string
        name_is_null = draw(st.booleans())
        if name_is_null:
            name_val = None
        else:
            # string without quotes
            name_val = draw(st.text(min_size=0, max_size=10)).replace('"', '')
    else:
        name_val = "##OMITTED##"

    # --- status field ---
    # Enum: "active", "inactive", "unknown"
    # Manual and built_value throw raw/wrapped ArgumentError on unknown strings
    # json_serializable/freezed throw CheckedFromJsonException on unknown strings
    # So generate mostly valid enum strings, but sometimes invalid strings to cause divergence
    valid_statuses = ["active", "inactive", "unknown"]
    # 80% valid, 20% invalid
    status_is_valid = draw(st.booleans().filter(lambda b: b or True))  # no bias, but we want 80% valid
    # To get ~80% valid, draw from weighted choice:
    status_val = draw(st.one_of(
        st.sampled_from(valid_statuses).filter(lambda _: True),  # valid
        st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_statuses)  # invalid
    ))
    # But above is 50/50, so manually bias:
    if draw(st.integers(min_value=1, max_value=100)) <= 80:
        status_val = draw(st.sampled_from(valid_statuses))
    else:
        # invalid string, avoid empty or quotes
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_statuses and '"' not in s and '\\' not in s))
        status_val = invalid_status

    # --- tags field ---
    # List of strings, possibly empty, strings possibly empty
    tags_len = draw(st.integers(min_value=0, max_value=5))
    tags_vals = []
    for _ in range(tags_len):
        tag = draw(st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
        tags_vals.append(tag)

    # --- child field ---
    # null or nested record (one level recursion)
    # built_value tolerates missing child (sets null)
    # manual/json_serializable/freezed require present (nullable)
    # So sometimes omit child to cause divergence
    omit_child = draw(st.booleans())
    if not omit_child:
        # present: null or nested record
        child_is_null = draw(st.booleans())
        if child_is_null:
            child_val = None
        else:
            # nested record with same schema but no further recursion (depth=1)
            # For nested record, keep it simpler: id int only, amount string, name present nullable,
            # status valid enum only (to avoid too many rejections), tags list of strings, child null
            nested_id = draw(st.integers(min_value=0, max_value=2**31-1))
            nested_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
            nested_name_is_null = draw(st.booleans())
            if nested_name_is_null:
                nested_name = None
            else:
                nested_name = draw(st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s))
            nested_status = draw(st.sampled_from(valid_statuses))
            nested_tags_len = draw(st.integers(min_value=0, max_value=3))
            nested_tags = [draw(st.text(min_size=0, max_size=10).filter(lambda s: '"' not in s and '\\' not in s)) for _ in range(nested_tags_len)]
            # child null (no further recursion)
            # Build nested JSON string for child
            nested_parts = []
            nested_parts.append('"id":'+str(nested_id))
            nested_parts.append('"amount":"'+json_escape(nested_amount)+'"')
            nested_parts.append('"name":'+("null" if nested_name is None else '"'+json_escape(nested_name)+'"'))
            nested_parts.append('"status":"'+nested_status+'"')
            nested_parts.append('"tags":['+','.join('"'+json_escape(t)+'"' for t in nested_tags)+']')
            nested_parts.append('"child":null')
            child_val = '{'+','.join(nested_parts)+'}'
    else:
        child_val = "##OMITTED##"

    # Build top-level JSON string
    parts = []

    # id
    if isinstance(id_val, int):
        parts.append('"id":'+str(id_val))
    else:
        # float with fractional part, output as JSON number
        # Use repr to avoid scientific notation
        parts.append('"id":'+repr(id_val))

    # amount
    parts.append('"amount":"'+json_escape(amount_val)+'"')

    # name
    if name_val == "##OMITTED##":
        # omit field
        pass
    else:
        if name_val is None:
            parts.append('"name":null')
        else:
            parts.append('"name":"'+json_escape(name_val)+'"')

    # status
    parts.append('"status":"'+json_escape(status_val)+'"')

    # tags
    parts.append('"tags":['+','.join('"'+json_escape(t)+'"' for t in tags_vals)+']')

    # child
    if child_val == "##OMITTED##":
        # omit field
        pass
    else:
        if child_val is None:
            parts.append('"child":null')
        else:
            # child_val is nested JSON string
            parts.append('"child":'+child_val)

    json_text = '{'+','.join(parts)+'}'

    return json_text.encode('utf-8')