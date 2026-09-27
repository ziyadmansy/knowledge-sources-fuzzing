from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslash only (minimal safe subset)
def json_string_escape(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping for JSON strings
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.
    """

    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Recursive depth limit: only one level of recursion for "child"
    # We generate the child record or null

    # Strategy for "id": integer, but allow borderline cases as strings (to provoke rejection)
    # But since all reject wrong primitive types for required fields, mostly keep int here.
    # To provoke divergence, we can sometimes produce a stringified int (as JSON string) for "id"
    # but that will be rejected by all, so no divergence.
    # Instead, keep "id" always integer to keep document mostly valid.

    # Strategy for "amount": string, but try to provoke divergence by using numeric strings,
    # empty strings, or strings with unusual unicode or escape sequences.
    # All accept string for amount, so no rejection expected here.
    # But we can try empty string or strings with escape sequences.

    # Strategy for "name": string or null
    # Try to provoke divergence by using empty string, null, or string with unicode escapes.
    # All accept null or string, so no rejection expected here.

    # Strategy for "status": enum string, but try to provoke divergence by using valid enum,
    # or invalid enum (which all reject but built_value rejects differently).
    # To provoke divergence, sometimes produce invalid enum values.

    # Strategy for "tags": array of strings
    # To provoke divergence, sometimes produce null (accepted only by built_value),
    # or empty array, or array with empty strings.
    # Also try array with duplicate strings (should be accepted by all).

    # Strategy for "child": null or nested Record (one level)
    # To provoke divergence, sometimes produce null,
    # sometimes produce nested record with subtle errors (e.g. tags=null),
    # or nested record with invalid enum in status,
    # or nested record with missing fields (should be rejected by all),
    # or nested record with extra fields (ignored by all).

    # To maximize divergence, produce mostly well-formed documents with one subtle error.

    # Helper to produce a valid or subtly invalid "status" field
    def status_strategy():
        # 80% valid enum, 20% invalid enum string (random string not in enum)
        valid = st.sampled_from(STATUS_VALUES)
        invalid = st.text(min_size=1).filter(lambda s: s not in STATUS_VALUES)
        return st.one_of(
            valid,
            invalid
        )

    # Helper to produce a valid or null or subtly invalid "tags" field
    def tags_strategy():
        # 70% valid array of strings (including empty array)
        # 20% null (accepted only by built_value)
        # 10% array with one non-string element (rejected by all)
        valid_array = st.lists(st.text(min_size=0), min_size=0, max_size=5)
        null_val = st.just(None)
        invalid_array = st.lists(st.one_of(st.integers(), st.booleans()), min_size=1, max_size=3)
        return st.one_of(
            valid_array,
            null_val,
            invalid_array
        )

    # Helper to produce a valid or null or subtly invalid "name" field
    def name_strategy():
        # 80% string (including empty), 20% null
        return st.one_of(
            st.text(min_size=0, max_size=20),
            st.just(None)
        )

    # Helper to produce a valid or subtly invalid "amount" field
    def amount_strategy():
        # 90% string with digits and dots, 10% empty string or weird escapes
        normal = st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in ".," for c in s))
        weird = st.sampled_from(["", "\u0000", "\n", "\r", "\t", "\\", "\""])
        return st.one_of(normal, weird)

    # Helper to produce a valid "id" field (integer)
    def id_strategy():
        # Always integer to keep mostly valid
        return st.integers(min_value=0, max_value=2**31-1)

    # Compose a record JSON string (not bytes yet)
    # Accepts parameters for each field, including child as JSON string or "null"
    def record_json_str(id_val, amount_val, name_val, status_val, tags_val, child_val, extra_fields=None):
        # extra_fields: list of (key, json_value_str) to add extra fields (ignored by all)
        # Compose fields in random order to provoke any ordering issues (though all take last duplicate)
        # But to keep stable, order fields as per schema, then extras at end

        # Format each field as JSON key:value string
        def json_str_val(val):
            if val is None:
                return "null"
            elif isinstance(val, str):
                return '"' + json_string_escape(val) + '"'
            elif isinstance(val, list):
                # list of strings or None (should be list of strings or null)
                # If None, produce null
                if val is None:
                    return "null"
                else:
                    # val is list of strings
                    items = []
                    for e in val:
                        if e is None:
                            items.append("null")
                        else:
                            items.append('"' + json_string_escape(e) + '"')
                    return "[" + ",".join(items) + "]"
            elif isinstance(val, int):
                return str(val)
            else:
                # val is already JSON string (for child)
                return val

        fields = [
            ('id', json_str_val(id_val)),
            ('amount', json_str_val(amount_val)),
            ('name', json_str_val(name_val)),
            ('status', json_str_val(status_val)),
            ('tags', json_str_val(tags_val)),
            ('child', child_val if child_val is not None else "null"),
        ]
        if extra_fields:
            fields.extend(extra_fields)

        # Compose JSON object string
        # To provoke duplicate keys, sometimes duplicate one key with different value
        # 10% chance to duplicate a random key with a different value
        # Duplicate keys always take last occurrence by all implementations
        duplicate_key_chance = 0.1
        if draw(st.randoms()).random() < duplicate_key_chance:
            # Pick a key to duplicate
            dup_key, dup_val = draw(st.sampled_from(fields))
            # Generate a different value for that key
            if dup_key == 'id':
                # Different int value
                new_val = str(draw(st.integers(min_value=0, max_value=2**31-1)))
            elif dup_key == 'amount':
                new_val = '"' + json_string_escape(draw(st.text(min_size=1, max_size=10))) + '"'
            elif dup_key == 'name':
                new_val = '"' + json_string_escape(draw(st.text(min_size=0, max_size=20))) + '"'
            elif dup_key == 'status':
                new_val = '"' + draw(st.sampled_from(STATUS_VALUES)) + '"'
            elif dup_key == 'tags':
                new_val = '[]'
            elif dup_key == 'child':
                new_val = "null"
            else:
                new_val = dup_val
            fields.append((dup_key, new_val))

        # Shuffle fields order to provoke any ordering issues
        fields = draw(st.permutations(fields))

        json_fields = []
        for k, v in fields:
            json_fields.append('"' + k + '":' + v)
        return "{" + ",".join(json_fields) + "}"

    # Compose child record or null
    # To provoke divergence, child can be:
    # - null (accepted by all)
    # - valid nested record (accepted by all)
    # - nested record with tags=null (accepted only by built_value)
    # - nested record with invalid enum status (rejected by all, but built_value differently)
    # - nested record with missing fields (rejected by all)
    # - nested record with extra fields (ignored by all)
    # - nested record with duplicate keys (all take last)
    # - nested record with subtle invalid field type (e.g. id as string) (rejected by all)
    # We'll pick one of these cases randomly weighted to provoke divergence

    child_case = draw(st.sampled_from([
        "null",
        "valid",
        "tags_null",
        "invalid_enum",
        "missing_field",
        "extra_fields",
        "duplicate_keys",
        "id_string",
    ]))

    # Generate child JSON string accordingly
    if child_case == "null":
        child_json = "null"
    else:
        # Generate fields for child record
        child_id = draw(id_strategy())
        child_amount = draw(amount_strategy())
        child_name = draw(name_strategy())
        if child_case == "invalid_enum":
            # invalid enum string for status
            child_status = draw(st.text(min_size=1).filter(lambda s: s not in STATUS_VALUES))
        else:
            child_status = draw(st.sampled_from(STATUS_VALUES))
        if child_case == "tags_null":
            child_tags = None
        elif child_case == "id_string":
            # id as string (invalid)
            child_id_str = str(child_id)
            child_id = None  # will be replaced by string below
        else:
            child_tags = draw(tags_strategy())
            # If tags_strategy returns invalid array (non-string elements), keep as is

        child_name_val = child_name
        child_amount_val = child_amount

        # Compose extra fields if needed
        extra_fields = None
        if child_case == "extra_fields":
            extra_fields = [("extra1", '"extra_val"'), ("extra2", '123')]
        else:
            extra_fields = []

        # Compose child JSON string
        if child_case == "missing_field":
            # Omit one required field randomly: id, amount, status, tags
            omit_field = draw(st.sampled_from(["id", "amount", "status", "tags"]))
            fields = {
                "id": child_id,
                "amount": child_amount,
                "name": child_name_val,
                "status": child_status,
                "tags": child_tags,
            }
            # Remove omitted field
            fields.pop(omit_field)

            # Compose JSON string manually
            json_fields = []
            for k, v in fields.items():
                if v is None and k != "name":  # only name nullable
                    # For omitted field, skip
                    continue
                if k == "tags" and v is None:
                    json_val = "null"
                elif k == "id" and child_case == "id_string" and k == "id":
                    # id as string
                    json_val = '"' + child_id_str + '"'
                elif isinstance(v, str):
                    json_val = '"' + json_string_escape(v) + '"'
                elif isinstance(v, list):
                    if v is None:
                        json_val = "null"
                    else:
                        json_val = "[" + ",".join('"' + json_string_escape(e) + '"' for e in v) + "]"
                elif isinstance(v, int):
                    json_val = str(v)
                elif v is None:
                    json_val = "null"
                else:
                    json_val = v
                json_fields.append('"' + k + '":' + json_val)
            # Add extra fields if any
            for k, v in extra_fields:
                json_fields.append('"' + k + '":' + v)
            child_json = "{" + ",".join(json_fields) + "}"

        else:
            # Compose normally
            if child_case == "id_string":
                # id as string
                child_json = record_json_str(
                    id_val='"' + child_id_str + '"',  # pass string literal, will be quoted again below
                    amount_val=child_amount_val,
                    name_val=child_name_val,
                    status_val=child_status,
                    tags_val=child_tags,
                    child_val="null",
                    extra_fields=extra_fields,
                )
                # The above will quote id_val again, so fix by manual string replacement:
                # The id_val is '"123"' (including quotes), so it becomes "\"123\""
                # We want id: "123" (one pair of quotes)
                # So replace the id field value with the inner string without extra quotes
                # id field is first field, so replace first occurrence of id:"\"123\""
                # with id:"123"
                child_json = child_json.replace(':"\\"' + child_id_str + '\\""', ':"' + child_id_str + '"')
            else:
                child_json = record_json_str(
                    id_val=child_id,
                    amount_val=child_amount_val,
                    name_val=child_name_val,
                    status_val=child_status,
                    tags_val=child_tags,
                    child_val="null",
                    extra_fields=extra_fields,
                )

        if child_case == "duplicate_keys":
            # Add a duplicate key in child_json with different value
            # Pick a key to duplicate
            dup_key = draw(st.sampled_from(["id", "amount", "name", "status", "tags"]))
            # Generate a different value for that key
            if dup_key == "id":
                dup_val = str(draw(st.integers(min_value=0, max_value=2**31-1)))
            elif dup_key == "amount":
                dup_val = '"' + json_string_escape(draw(st.text(min_size=1, max_size=10))) + '"'
            elif dup_key == "name":
                dup_val = '"' + json_string_escape(draw(st.text(min_size=0, max_size=20))) + '"'
            elif dup_key == "status":
                dup_val = '"' + draw(st.sampled_from(STATUS_VALUES)) + '"'
            elif dup_key == "tags":
                dup_val = '[]'
            else:
                dup_val = 'null'
            # Insert duplicate key at end before closing }
            child_json = child_json[:-1] + ',' + '"' + dup_key + '":' + dup_val + '}'

    # Now generate root record fields

    root_id = draw(id_strategy())
    root_amount = draw(amount_strategy())
    root_name = draw(name_strategy())
    root_status = draw(status_strategy())
    root_tags = draw(tags_strategy())

    # Compose root JSON string
    root_json = record_json_str(
        id_val=root_id,
        amount_val=root_amount,
        name_val=root_name,
        status_val=root_status,
        tags_val=root_tags,
        child_val=child_json,
        extra_fields=None,
    )

    # Return bytes
    return root_json.encode("utf-8")