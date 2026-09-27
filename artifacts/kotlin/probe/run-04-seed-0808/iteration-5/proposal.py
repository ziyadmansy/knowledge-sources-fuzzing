from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars)
def json_string(s: str) -> str:
    # Escape backslash and double quote only for simplicity
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text for the record schema with controlled variations
    to maximize divergence among Gson, Moshi, kotlinx.serialization, and Jackson.

    Schema:
    {
      "id": <integer or string of integer>,
      "amount": <string or number (number rejected by kotlinx)>,
      "name": <string or null or number (number rejected by kotlinx)>,
      "status": <enum string or invalid enum or null (Gson accepts null, others reject)>,
      "tags": <array of strings or array with non-string elements (non-string rejected by kotlinx)>,
      "child": <record or null>
    }

    Variations:
    - "id": int or string int (all accept both)
    - "amount": string or number (kotlin rejects number)
    - "name": string, null, or number (kotlin rejects number)
    - "status": valid enum, invalid enum string, or null (Gson accepts null and invalid enum as null, others reject)
    - "tags": array of strings or array with some non-string elements (kotlin rejects non-string)
    - "child": null or nested record (one level recursion)
    - Extra unknown fields: present or absent (Gson/Moshi accept, kotlinx/Jackson reject)
    - Duplicate fields: last occurrence wins (all accept)
    """

    # Constants
    valid_statuses = ["active", "inactive", "unknown"]
    invalid_statuses = ["invalid", "none", "123", "ACTIVE"]  # invalid enum strings

    # --- id field ---
    # id as int or string int (both accepted by all)
    id_int = draw(st.integers(min_value=0, max_value=10000))
    id_as_string = draw(st.booleans())
    if id_as_string:
        id_val = json_string(str(id_int))
    else:
        id_val = str(id_int)

    # --- amount field ---
    # amount as string or number (kotlin rejects number)
    amount_is_number = draw(st.booleans())
    if amount_is_number:
        # number as int or float string convertible to string
        amount_num = draw(st.one_of(st.integers(min_value=0, max_value=1000000),
                                   st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False)))
        # Format floats with minimal decimal places
        if isinstance(amount_num, float):
            amount_val = str(amount_num) if '.' in str(amount_num) else str(float(amount_num))
        else:
            amount_val = str(amount_num)
    else:
        # amount as string (always accepted)
        amount_str = draw(st.text(min_size=1, max_size=10))
        amount_val = json_string(amount_str)

    # --- name field ---
    # name as string, null, or number (kotlin rejects number)
    name_choice = draw(st.sampled_from(["string", "null", "number"]))
    if name_choice == "string":
        name_val = json_string(draw(st.text(min_size=0, max_size=20)))
    elif name_choice == "null":
        name_val = "null"
    else:
        # number as int or float
        name_num = draw(st.one_of(st.integers(min_value=-1000, max_value=1000),
                                  st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
        if isinstance(name_num, float):
            name_val = str(name_num) if '.' in str(name_num) else str(float(name_num))
        else:
            name_val = str(name_num)

    # --- status field ---
    # status as valid enum, invalid enum string, or null
    status_choice = draw(st.sampled_from(["valid", "invalid", "null"]))
    if status_choice == "valid":
        status_val = json_string(draw(st.sampled_from(valid_statuses)))
    elif status_choice == "invalid":
        status_val = json_string(draw(st.sampled_from(invalid_statuses)))
    else:
        status_val = "null"

    # --- tags field ---
    # tags as array of strings or array with some non-string elements (kotlin rejects non-string)
    tags_type = draw(st.sampled_from(["all_strings", "mixed"]))
    if tags_type == "all_strings":
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        tags_val = "[" + ",".join(json_string(t) for t in tags_list) + "]"
    else:
        # mixed types: strings, numbers, booleans, nulls
        tag_elements = []
        n_tags = draw(st.integers(min_value=1, max_value=5))
        for _ in range(n_tags):
            elem_type = draw(st.sampled_from(["string", "number", "bool", "null"]))
            if elem_type == "string":
                tag_elements.append(json_string(draw(st.text(min_size=0, max_size=10))))
            elif elem_type == "number":
                num = draw(st.one_of(st.integers(min_value=-1000, max_value=1000),
                                     st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
                if isinstance(num, float):
                    tag_elements.append(str(num) if '.' in str(num) else str(float(num)))
                else:
                    tag_elements.append(str(num))
            elif elem_type == "bool":
                tag_elements.append("true" if draw(st.booleans()) else "false")
            else:
                tag_elements.append("null")
        tags_val = "[" + ",".join(tag_elements) + "]"

    # --- child field ---
    # Either null or nested record (one level recursion)
    has_child = draw(st.booleans())
    if has_child:
        # Nested record with simpler constraints to avoid deep recursion
        # id: int or string int
        child_id_int = draw(st.integers(min_value=0, max_value=10000))
        child_id_as_string = draw(st.booleans())
        if child_id_as_string:
            child_id_val = json_string(str(child_id_int))
        else:
            child_id_val = str(child_id_int)

        # amount: string only (to reduce complexity)
        child_amount_val = json_string(draw(st.text(min_size=1, max_size=10)))

        # name: string or null only
        child_name_val = draw(st.one_of(st.just("null"), st.text(min_size=0, max_size=20).map(json_string)))

        # status: valid enum only
        child_status_val = json_string(draw(st.sampled_from(valid_statuses)))

        # tags: array of strings only
        child_tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))
        child_tags_val = "[" + ",".join(json_string(t) for t in child_tags_list) + "]"

        # child: null only (no deeper recursion)
        child_child_val = "null"

        # Compose child JSON object with possible duplicate fields (simulate duplicates)
        # Duplicate fields: last occurrence wins
        # Randomly decide to duplicate one field
        duplicate_field = draw(st.sampled_from([None, "id", "amount", "name", "status", "tags"]))
        def field_with_dup(field_name, val):
            if duplicate_field == field_name:
                # Duplicate with different value
                if field_name == "id":
                    alt_val = json_string(str(child_id_int + 1))
                elif field_name == "amount":
                    alt_val = json_string("dup")
                elif field_name == "name":
                    alt_val = json_string("dupname")
                elif field_name == "status":
                    alt_val = json_string("inactive" if child_status_val != json_string("inactive") else "active")
                elif field_name == "tags":
                    alt_val = "[]"
                else:
                    alt_val = val
                return f'"{field_name}":{val},"{field_name}":{alt_val}'
            else:
                return f'"{field_name}":{val}'

        child_fields = [
            field_with_dup("id", child_id_val),
            field_with_dup("amount", child_amount_val),
            field_with_dup("name", child_name_val),
            field_with_dup("status", child_status_val),
            field_with_dup("tags", child_tags_val),
            f'"child":{child_child_val}'
        ]
        child_val = "{" + ",".join(child_fields) + "}"
    else:
        child_val = "null"

    # --- Extra unknown fields ---
    # Gson and Moshi accept unknown fields; kotlinx and Jackson reject them.
    # Add zero or one unknown field randomly
    add_unknown = draw(st.booleans())
    if add_unknown:
        unknown_field_name = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in {"id","amount","name","status","tags","child"}))
        # unknown field value: string or number or null
        unknown_val_type = draw(st.sampled_from(["string", "number", "null"]))
        if unknown_val_type == "string":
            unknown_val = json_string(draw(st.text(min_size=0, max_size=10)))
        elif unknown_val_type == "number":
            num = draw(st.one_of(st.integers(min_value=-1000, max_value=1000),
                                 st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)))
            if isinstance(num, float):
                unknown_val = str(num) if '.' in str(num) else str(float(num))
            else:
                unknown_val = str(num)
        else:
            unknown_val = "null"
        unknown_field = f'"{unknown_field_name}":{unknown_val}'
    else:
        unknown_field = None

    # --- Compose top-level JSON object ---
    # Duplicate fields at top-level: randomly duplicate one field with different value
    duplicate_field_top = draw(st.sampled_from([None, "id", "amount", "name", "status", "tags", "child"]))
    def top_field_with_dup(field_name, val):
        if duplicate_field_top == field_name:
            # Provide a different value for duplicate
            if field_name == "id":
                alt_val = json_string(str(id_int + 1)) if id_as_string else str(id_int + 1)
            elif field_name == "amount":
                alt_val = json_string("dup") if not amount_is_number else "12345"
            elif field_name == "name":
                alt_val = json_string("dupname") if name_choice != "null" else "null"
            elif field_name == "status":
                alt_val = json_string("inactive" if status_val != json_string("inactive") else "active")
            elif field_name == "tags":
                alt_val = "[]" if tags_type == "all_strings" else "[\"dup\"]"
            elif field_name == "child":
                alt_val = "null" if child_val != "null" else "{}"
            else:
                alt_val = val
            return f'"{field_name}":{val},"{field_name}":{alt_val}'
        else:
            return f'"{field_name}":{val}'

    fields = [
        top_field_with_dup("id", id_val),
        top_field_with_dup("amount", amount_val),
        top_field_with_dup("name", name_val),
        top_field_with_dup("status", status_val),
        top_field_with_dup("tags", tags_val),
        top_field_with_dup("child", child_val)
    ]
    if unknown_field is not None:
        fields.append(unknown_field)

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")