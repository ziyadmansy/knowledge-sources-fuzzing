from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslash only (minimal)
def json_string_escape(s: str) -> str:
    # Minimal escaping for JSON strings: backslash and double quote
    return s.replace('\\', '\\\\').replace('"', '\\"')

# Compose a JSON string literal from a Python string
def json_string_literal(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

# Compose a JSON array literal from a list of JSON text elements
def json_array_literal(elements) -> str:
    return '[' + ','.join(elements) + ']'

# Compose a JSON object literal from a list of (key, value) JSON text pairs
def json_object_literal(pairs) -> str:
    # pairs: list of (key_json_string, value_json_text)
    return '{' + ','.join(k + ':' + v for k, v in pairs) + '}'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects (as bytes) that represent
    the described Record schema, with subtle variations to provoke
    divergence among four Dart JSON deserializers.
    """

    # Constants for "status" field
    valid_statuses = ["active", "inactive", "unknown"]

    # Strategy for "id": always integer (no floats or strings)
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))

    # Strategy for "amount": string, but try some edge cases (empty, numeric strings, etc)
    # Always string type, but content can vary
    amount_val = draw(st.one_of(
        st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in '"\\')),  # safe strings no quotes or backslash
        st.just("0"),
        st.just("123.45"),
        st.just("-0.01"),
        st.just(""),
    ))

    # Strategy for "name": string or null or missing (missing only for "name" allowed)
    # To provoke divergence, sometimes omit "name" (all accept), sometimes null, sometimes string
    # Also try empty string and strings with escaped chars
    name_choice = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in '"\\')),
        st.just(""),
    ))

    # Strategy for "status": mostly valid, but sometimes invalid to provoke divergence
    # built_value throws DeserializationError, others ArgumentError on invalid
    # We want mostly valid, but sometimes invalid string or null or empty string
    status_val = draw(st.one_of(
        st.sampled_from(valid_statuses),
        st.text(min_size=0, max_size=5).filter(lambda s: s not in valid_statuses),
        st.none(),
        st.just(""),
    ))

    # Strategy for "tags": array of strings, or null (only built_value accepts null)
    # Also try missing "tags" (only built_value accepts missing tags)
    # To provoke divergence, sometimes omit tags, sometimes null, sometimes empty array, sometimes array with strings
    tags_choice = draw(st.one_of(
        st.none(),  # null tags (only built_value accepts)
        st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(c not in s for c in '"\\')), max_size=3),
        st.just([]),
    ))

    # Strategy for "child": null or nested record (one level only)
    # To provoke divergence, child can be null, or a nested record with one field off (missing or wrong type)
    # We limit recursion to one level only
    # We build a nested record with same schema but simpler: all fields present and valid or one subtle error

    # Helper to build a nested child record JSON text with optional subtle error
    def build_child_record():
        # Decide if child is null or object
        child_is_null = draw(st.booleans())
        if child_is_null:
            return "null"

        # Nested child fields
        # id: integer
        child_id = draw(st.integers(min_value=0, max_value=2**31-1))
        # amount: string
        child_amount = draw(st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in '"\\')))
        # name: string or null
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: all(c not in s for c in '"\\'))))
        # status: valid only (to avoid double errors)
        child_status = draw(st.sampled_from(valid_statuses))
        # tags: non-null array of strings (to avoid double errors)
        child_tags = draw(st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(c not in s for c in '"\\')), max_size=3))
        # child: null (no further recursion)
        child_child = "null"

        # Introduce subtle error in child with low probability:
        # Either omit one required field (except name), or put wrong type in one field
        error_type = draw(st.one_of(st.just("none"), st.just("missing"), st.just("wrong_type")))

        # Build fields as list of (key_json_string, value_json_text)
        fields = []

        # id field
        if error_type == "missing" and draw(st.booleans()):
            # omit id field (required)
            pass
        elif error_type == "wrong_type" and draw(st.booleans()):
            # id as string (wrong type)
            fields.append((json_string_literal("id"), json_string_literal(str(child_id))))
        else:
            fields.append((json_string_literal("id"), str(child_id)))

        # amount field
        if error_type == "missing" and draw(st.booleans()):
            # omit amount field (required)
            pass
        elif error_type == "wrong_type" and draw(st.booleans()):
            # amount as number (wrong type)
            try:
                amt_num = float(child_amount) if child_amount else 0.0
            except Exception:
                amt_num = 0.0
            fields.append((json_string_literal("amount"), str(amt_num)))
        else:
            fields.append((json_string_literal("amount"), json_string_literal(child_amount)))

        # name field (optional, can be missing)
        if error_type == "missing" and draw(st.booleans()):
            # omit name field (allowed)
            pass
        else:
            if child_name is None:
                fields.append((json_string_literal("name"), "null"))
            else:
                fields.append((json_string_literal("name"), json_string_literal(child_name)))

        # status field
        if error_type == "missing" and draw(st.booleans()):
            # omit status (required)
            pass
        elif error_type == "wrong_type" and draw(st.booleans()):
            # status as invalid string
            fields.append((json_string_literal("status"), json_string_literal("invalid_status")))
        else:
            fields.append((json_string_literal("status"), json_string_literal(child_status)))

        # tags field
        if error_type == "missing" and draw(st.booleans()):
            # omit tags (required)
            pass
        elif error_type == "wrong_type" and draw(st.booleans()):
            # tags as null (only built_value accepts)
            fields.append((json_string_literal("tags"), "null"))
        else:
            fields.append((json_string_literal("tags"), json_array_literal([json_string_literal(t) for t in child_tags])))

        # child field (always null here)
        fields.append((json_string_literal("child"), child_child))

        # Possibly add an extra unknown field (ignored by all)
        if draw(st.booleans()):
            fields.append((json_string_literal("extra_field"), json_string_literal("ignored")))

        return json_object_literal(fields)

    # Build top-level fields list (key_json_string, value_json_text)
    fields = []

    # id field (required, integer only)
    fields.append((json_string_literal("id"), str(id_val)))

    # amount field (required, string)
    fields.append((json_string_literal("amount"), json_string_literal(amount_val)))

    # name field: sometimes omit (allowed), sometimes null, sometimes string
    # To provoke divergence, sometimes omit name (all accept)
    omit_name = draw(st.booleans())
    if not omit_name:
        if name_choice is None:
            fields.append((json_string_literal("name"), "null"))
        else:
            fields.append((json_string_literal("name"), json_string_literal(name_choice)))

    # status field (required)
    # To provoke divergence, sometimes invalid or null or empty string
    # built_value throws DeserializationError, others ArgumentError
    # We always include status field (never omit)
    if status_val is None:
        fields.append((json_string_literal("status"), "null"))
    else:
        fields.append((json_string_literal("status"), json_string_literal(status_val)))

    # tags field: sometimes omit (only built_value accepts), sometimes null (only built_value accepts), sometimes array
    omit_tags = draw(st.booleans())
    if not omit_tags:
        if tags_choice is None:
            # null tags
            fields.append((json_string_literal("tags"), "null"))
        else:
            # array of strings (possibly empty)
            fields.append((json_string_literal("tags"), json_array_literal([json_string_literal(t) for t in tags_choice])))

    # child field: null or nested record with subtle error
    child_json = build_child_record()
    fields.append((json_string_literal("child"), child_json))

    # Possibly add an extra unknown field (ignored by all)
    if draw(st.booleans()):
        fields.append((json_string_literal("extra_field"), json_string_literal("ignored")))

    # Compose final JSON object text
    json_text = json_object_literal(fields)

    # Return as bytes (UTF-8)
    return json_text.encode("utf-8")