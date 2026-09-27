from hypothesis import strategies as st

# Helper: JSON string escaping for a subset of ASCII (no control chars, no unicode escapes)
def json_string_escape(s: str) -> str:
    # Escape backslash and double quote, and control chars \b\f\n\r\t as \u escapes
    # For simplicity, only allow ASCII printable except backslash and quote
    # We'll generate strings from a safe charset to avoid complex escaping
    # So here just replace backslash and quote
    return s.replace('\\', '\\\\').replace('"', '\\"')

# Compose a JSON string literal from a Python string
def json_string_literal(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

# Compose JSON array from list of JSON elements (strings)
def json_array_literal(elements) -> str:
    return '[' + ','.join(elements) + ']'

# Compose JSON object from list of (key, value) pairs (both strings)
def json_object_literal(pairs) -> str:
    # pairs: list of (key, value) strings, keys are JSON strings (quoted)
    return '{' + ','.join(k + ':' + v for k, v in pairs) + '}'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text bytes for a document with the given schema,
    designed to produce behavioral divergence among Gson, Moshi, kotlinx.serialization, and Jackson.

    Strategy:
    - Start from a valid base document with all fields present and well-formed.
    - Introduce at most one or two subtle deviations likely to cause divergence:
      * id: number or string number (all accept)
      * amount: string or number (kotlinx rejects number)
      * name: string, null, or number (kotlinx rejects number)
      * status: one of allowed strings, unknown string (Gson accepts unknown as null, others reject),
                or null (Gson accepts null, others reject)
      * tags: array of strings normally, or array with non-string elements (kotlinx rejects non-string),
              or non-array (all reject)
      * child: null, valid nested record, or empty object {} (Gson accepts {}, others reject)
      * unknown extra fields: Gson and Moshi accept, others reject
    - Duplicate keys: last wins, all accept
    - Keep recursion depth bounded to 1 for child
    """

    # Basic valid values for fields
    valid_status = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
    valid_status_strs = ['"active"', '"inactive"', '"unknown"']

    # id: integer as number or string number
    id_num = draw(st.integers(min_value=0, max_value=10000))
    id_as_number = str(id_num)
    id_as_string = json_string_literal(str(id_num))
    id_val = draw(st.sampled_from([id_as_number, id_as_string]))

    # amount: string or number (kotlinx rejects number)
    # Use string numeric or numeric literal
    amount_num = draw(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False))
    # Format float as JSON number (no quotes)
    amount_num_str = repr(amount_num)
    # amount string (numeric string)
    amount_str = json_string_literal(f"{amount_num:.2f}")
    amount_val = draw(st.sampled_from([amount_str, amount_num_str]))

    # name: string, null, or number (kotlinx rejects number)
    # name string: simple ascii letters
    name_str = draw(st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E).filter(lambda c: c not in ['"', '\\']), min_size=1, max_size=10))
    name_json_str = json_string_literal(name_str)
    name_num = draw(st.integers(min_value=0, max_value=10000))
    name_num_str = str(name_num)
    name_val = draw(st.sampled_from([name_json_str, "null", name_num_str]))

    # status: one of allowed strings, unknown string, or null
    # unknown string: a string not in allowed set
    unknown_status_str = json_string_literal("invalid_status")
    status_val = draw(st.sampled_from(
        valid_status_strs + [unknown_status_str, "null"]
    ))

    # tags: array of strings normally, or array with non-string elements, or non-array
    # strings: simple ascii words
    tag_strs = draw(st.lists(st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E).filter(lambda c: c not in ['"', '\\']), min_size=1, max_size=10), min_size=0, max_size=5))
    tag_json_strs = [json_string_literal(t) for t in tag_strs]

    # Non-string elements for tags: numbers, null, booleans
    non_string_tag_elements = [
        "null",
        "true",
        "false",
        "123",
        "45.6"
    ]
    # Mix string and non-string elements
    tags_mixed = tag_json_strs + draw(st.lists(st.sampled_from(non_string_tag_elements), min_size=0, max_size=2))
    draw.shuffle(tags_mixed)

    # tags_val: choose among
    # 1) array of strings only (all accept)
    # 2) array with some non-string elements (kotlinx rejects)
    # 3) non-array (all reject)
    tags_choice = draw(st.sampled_from(["strings_array", "mixed_array", "non_array"]))
    if tags_choice == "strings_array":
        tags_val = json_array_literal(tag_json_strs)
    elif tags_choice == "mixed_array":
        tags_val = json_array_literal(tags_mixed)
    else:
        # non-array: null, string, number, object, boolean
        non_array_vals = [
            "null",
            json_string_literal("not an array"),
            "123",
            "{}",
            "true",
            "false"
        ]
        tags_val = draw(st.sampled_from(non_array_vals))

    # child: null, valid nested record, or empty object {}
    # Nested record: same schema but no further recursion (depth=1)
    # Compose nested record with all fields present and well-formed
    nested_id_num = draw(st.integers(min_value=0, max_value=10000))
    nested_id_val = draw(st.sampled_from([str(nested_id_num), json_string_literal(str(nested_id_num))]))
    nested_amount_num = draw(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False))
    nested_amount_val = draw(st.sampled_from([json_string_literal(f"{nested_amount_num:.2f}"), repr(nested_amount_num)]))
    nested_name_str = draw(st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E).filter(lambda c: c not in ['"', '\\']), min_size=1, max_size=10))
    nested_name_val = draw(st.sampled_from([json_string_literal(nested_name_str), "null"]))
    nested_status_val = draw(st.sampled_from(valid_status_strs))
    nested_tags_list = draw(st.lists(st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E).filter(lambda c: c not in ['"', '\\']), min_size=1, max_size=10), min_size=0, max_size=3))
    nested_tags_val = json_array_literal([json_string_literal(t) for t in nested_tags_list])
    nested_child_val = "null"

    nested_pairs = [
        (json_string_literal("id"), nested_id_val),
        (json_string_literal("amount"), nested_amount_val),
        (json_string_literal("name"), nested_name_val),
        (json_string_literal("status"), nested_status_val),
        (json_string_literal("tags"), nested_tags_val),
        (json_string_literal("child"), nested_child_val),
    ]
    nested_record_val = json_object_literal(nested_pairs)

    child_choice = draw(st.sampled_from(["null", "nested_record", "empty_object"]))
    if child_choice == "null":
        child_val = "null"
    elif child_choice == "nested_record":
        child_val = nested_record_val
    else:
        # empty object {}
        child_val = "{}"

    # Unknown extra fields: Gson and Moshi accept, kotlinx and Jackson reject
    # Add zero or one unknown field at top level or nested level
    unknown_field_key = json_string_literal("unknown_field")
    unknown_field_value = json_string_literal("extra_value")
    add_unknown_field = draw(st.booleans())
    unknown_field_at_top = draw(st.booleans())

    # Compose top-level fields
    top_level_pairs = [
        (json_string_literal("id"), id_val),
        (json_string_literal("amount"), amount_val),
        (json_string_literal("name"), name_val),
        (json_string_literal("status"), status_val),
        (json_string_literal("tags"), tags_val),
        (json_string_literal("child"), child_val),
    ]

    if add_unknown_field:
        if unknown_field_at_top:
            # Add unknown field at top level
            top_level_pairs.append((unknown_field_key, unknown_field_value))
        else:
            # Add unknown field inside child if child is nested_record
            if child_choice == "nested_record":
                # Add unknown field to nested record pairs
                nested_pairs.append((unknown_field_key, unknown_field_value))
                # Rebuild nested_record_val with the extra field
                nested_record_val = json_object_literal(nested_pairs)
                child_val = nested_record_val
                # Update top level child field
                for i, (k, v) in enumerate(top_level_pairs):
                    if k == json_string_literal("child"):
                        top_level_pairs[i] = (k, child_val)
                        break

    # Duplicate keys: last wins for all
    # Introduce zero or one duplicate key for one field
    duplicate_key = draw(st.booleans())
    if duplicate_key:
        # Pick a field to duplicate
        dup_field = draw(st.sampled_from(["id", "amount", "name", "status", "tags", "child"]))
        # Compose a second value for that field, different from first if possible
        if dup_field == "id":
            dup_val = json_string_literal(str(draw(st.integers(min_value=0, max_value=10000))))
        elif dup_field == "amount":
            dup_val = json_string_literal(f"{draw(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)):.2f}")
        elif dup_field == "name":
            dup_val = "null" if name_val != "null" else json_string_literal("dup")
        elif dup_field == "status":
            dup_val = draw(st.sampled_from(valid_status_strs))
        elif dup_field == "tags":
            dup_val = json_array_literal([json_string_literal("dup_tag")])
        else:  # child
            dup_val = "null" if child_val != "null" else nested_record_val

        # Insert duplicate key at random position (last wins)
        # Remove original field first
        top_level_pairs = [p for p in top_level_pairs if p[0] != json_string_literal(dup_field)]
        # Insert original and duplicate in random order
        if draw(st.booleans()):
            # original then duplicate
            top_level_pairs.append((json_string_literal(dup_field), dup_val))
            top_level_pairs.append((json_string_literal(dup_field), top_level_pairs[-1][1]))
        else:
            # duplicate then original
            top_level_pairs.append((json_string_literal(dup_field), top_level_pairs[-1][1]))
            top_level_pairs.append((json_string_literal(dup_field), dup_val))

        # But to keep last wins, just append duplicate after original
        # Actually above is inconsistent, fix to:
        # Append original then duplicate
        top_level_pairs.append((json_string_literal(dup_field), dup_val))
        top_level_pairs.append((json_string_literal(dup_field), dup_val))

    # Compose final JSON object text
    json_text = json_object_literal(top_level_pairs)

    return json_text.encode("utf-8")