from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and field names
    STATUS_VALUES = ["active", "inactive", "unknown"]
    FIELD_NAMES = ["id", "amount", "name", "status", "tags", "child"]

    # Helper: produce a JSON string literal from a Python string (escape minimal chars)
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally for JSON string
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars minimally (newline, tab)
        s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{s}"'

    # Helper: produce JSON array of strings
    def json_string_array(strs):
        return "[" + ",".join(json_string(s) for s in strs) + "]"

    # Generate a valid "id" integer as JSON number string
    id_val = draw(st.integers(min_value=0, max_value=2**31 - 1))
    id_json = str(id_val)

    # Generate "amount" as a string representing a decimal number (to keep valid)
    # But we will sometimes produce edge cases like "0", "0.0", "1e10", or negative zero "-0"
    # to test subtle parsing differences.
    def gen_amount_str():
        # Choose among normal decimal, scientific notation, or edge cases
        choice = draw(st.integers(min_value=0, max_value=4))
        if choice == 0:
            # Normal decimal string, possibly with leading zeros
            integral = draw(st.integers(min_value=0, max_value=9999999))
            frac = draw(st.one_of(st.none(), st.text(min_size=1, max_size=5, alphabet="0123456789")))
            if frac is None:
                return str(integral)
            else:
                return f"{integral}.{frac}"
        elif choice == 1:
            # Scientific notation
            base = draw(st.floats(min_value=0.1, max_value=1e6, allow_infinity=False, allow_nan=False))
            exp = draw(st.integers(min_value=-10, max_value=10))
            # Format as string with e notation
            s = f"{base:.5g}e{exp}"
            return s
        elif choice == 2:
            # Negative zero string "-0" or "-0.0"
            return draw(st.sampled_from(["-0", "-0.0"]))
        elif choice == 3:
            # Zero with leading zeros "0000"
            return draw(st.sampled_from(["0", "00", "0000", "000.0"]))
        else:
            # Simple integer string
            return str(draw(st.integers(min_value=0, max_value=1000000)))

    amount_val = gen_amount_str()
    amount_json = json_string(amount_val)

    # Generate "name" as either null or string (including empty string)
    # To provoke subtle differences, sometimes produce strings with unicode escapes or control chars
    def gen_name():
        # 80% chance string, 20% null
        if draw(st.booleans()):
            # string with possible control chars or unicode escapes
            # We'll produce normal printable ascii plus some control chars
            base = draw(st.text(min_size=0, max_size=10))
            # Insert some control chars rarely
            if draw(st.booleans()):
                base = base.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
            return json_string(base)
        else:
            return "null"

    name_json = gen_name()

    # Generate "status" with 90% valid enum, 10% invalid enum string (to test enum rejection)
    # But since all reject invalid enum identically, we mostly produce valid enums here.
    if draw(st.integers(min_value=1, max_value=10)) == 1:
        # invalid enum string, e.g. "enabled"
        status_val = "enabled"
    else:
        status_val = draw(st.sampled_from(STATUS_VALUES))
    status_json = json_string(status_val)

    # Generate "tags" as array of strings (possibly empty)
    # To provoke subtle differences, sometimes produce duplicates or empty strings
    def gen_tags():
        # length 0 to 5
        length = draw(st.integers(min_value=0, max_value=5))
        tags = []
        for _ in range(length):
            # strings with ascii letters, digits, or empty
            tag = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=0, max_size=8))
            tags.append(tag)
        # Possibly duplicate last tag to test overwriting in duplicates (but duplicates only matter in nested)
        return tags

    tags_val = gen_tags()
    tags_json = json_string_array(tags_val)

    # Generate "child" field: either null or a nested record (one level only)
    # To provoke subtle differences, child may have one field wrong type or missing
    # But mostly produce well-formed child, sometimes with one subtle error

    # Helper to generate a nested record JSON string (no further recursion)
    def gen_child_record():
        # Decide if child is null or object
        if draw(st.booleans()):
            return "null"
        else:
            # Build a nested record with all fields present
            # For subtlety, we vary one field to be wrong type or missing sometimes
            # Pick one field to corrupt or omit or duplicate keys
            corrupt_field = draw(st.sampled_from(FIELD_NAMES + [None]))
            duplicate_key = False
            duplicate_key_field = None
            # 10% chance to duplicate a key in child (only for array "tags" to be accepted)
            if draw(st.integers(min_value=1, max_value=10)) == 1:
                duplicate_key = True
                duplicate_key_field = "tags"

            # id: integer
            child_id = draw(st.integers(min_value=0, max_value=2**31 - 1))
            # amount: string decimal
            child_amount = gen_amount_str()
            # name: string or null
            child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            # status: enum string
            child_status = draw(st.sampled_from(STATUS_VALUES))
            # tags: array of strings
            child_tags = gen_tags()
            # child: null (no recursion beyond one level)
            child_child = None

            # Build fields as strings, possibly corrupt one field
            fields = {}

            def val_to_json(field, val):
                if val is None:
                    return "null"
                if field == "id":
                    return str(val)
                if field == "amount":
                    return json_string(val)
                if field == "name":
                    return json_string(val)
                if field == "status":
                    return json_string(val)
                if field == "tags":
                    return json_string_array(val)
                if field == "child":
                    return "null"
                raise RuntimeError("Unexpected field")

            # Insert fields, corrupt or omit one if chosen
            for f in FIELD_NAMES:
                if f == corrupt_field:
                    # Corrupt this field by type mismatch or missing
                    corrupt_type = draw(st.sampled_from(["missing", "wrong_type", "duplicate_conflict"]))
                    if corrupt_type == "missing":
                        # omit field entirely
                        continue
                    elif corrupt_type == "wrong_type":
                        # produce wrong type for this field
                        if f == "id":
                            # id as string (should be int)
                            fields[f] = json_string("not_an_int")
                        elif f == "amount":
                            # amount as number (should be string)
                            fields[f] = "123.45"
                        elif f == "name":
                            # name as number (should be string or null)
                            fields[f] = "123"
                        elif f == "status":
                            # invalid enum string
                            fields[f] = json_string("enabled")
                        elif f == "tags":
                            # tags as string (should be array)
                            fields[f] = json_string("not_an_array")
                        elif f == "child":
                            # child as string (should be object or null)
                            fields[f] = json_string("not_an_object")
                    elif corrupt_type == "duplicate_conflict":
                        # duplicate a scalar field with conflicting type to provoke rejection
                        # Only do this if duplicate_key is False to avoid confusion
                        if not duplicate_key:
                            # We'll do this after building fields
                            pass
                        else:
                            # fallback to missing
                            continue
                else:
                    # Normal field
                    if f == "id":
                        fields[f] = str(child_id)
                    elif f == "amount":
                        fields[f] = json_string(child_amount)
                    elif f == "name":
                        if child_name is None:
                            fields[f] = "null"
                        else:
                            fields[f] = json_string(child_name)
                    elif f == "status":
                        fields[f] = json_string(child_status)
                    elif f == "tags":
                        fields[f] = json_string_array(child_tags)
                    elif f == "child":
                        fields[f] = "null"

            # If duplicate_key and duplicate_key_field == "tags", add duplicate key with different array
            if duplicate_key and duplicate_key_field == "tags":
                # Add duplicate "tags" key with different array (last wins)
                # First tags key (normal)
                base = []
                for k,v in fields.items():
                    base.append(json_string(k) + ":" + v)
                # Insert duplicate tags key with different array
                dup_tags = gen_tags()
                base.append(json_string("tags") + ":" + json_string_array(dup_tags))
                return "{" + ",".join(base) + "}"

            # If corrupt_field is duplicate_conflict, add duplicate key with conflicting type
            if corrupt_field is not None:
                # Only do if corrupt_field is scalar (id, amount, name, status)
                if corrupt_field in ("id", "amount", "name", "status"):
                    # Build base fields without corrupt_field (already set)
                    base = []
                    for k,v in fields.items():
                        base.append(json_string(k) + ":" + v)
                    # Add duplicate key with conflicting type
                    if corrupt_field == "id":
                        # duplicate id as string (conflict with int)
                        base.append(json_string("id") + ":" + json_string("conflict"))
                    elif corrupt_field == "amount":
                        # duplicate amount as number (conflict with string)
                        base.append(json_string("amount") + ":" + "123.45")
                    elif corrupt_field == "name":
                        # duplicate name as number (conflict with string or null)
                        base.append(json_string("name") + ":" + "123")
                    elif corrupt_field == "status":
                        # duplicate status as invalid enum string (conflict)
                        base.append(json_string("status") + ":" + json_string("enabled"))
                    return "{" + ",".join(base) + "}"

            # Otherwise normal object
            base = []
            for k,v in fields.items():
                base.append(json_string(k) + ":" + v)
            return "{" + ",".join(base) + "}"

    child_json = gen_child_record()

    # Now build top-level JSON object string with all fields present
    # To provoke subtle differences, sometimes omit one top-level field (should cause rejection)
    # or duplicate a scalar key with conflicting type (should cause rejection)
    # or duplicate "tags" key (should be accepted, last wins)
    # or produce invalid enum in top-level status (mostly avoided, since all reject identically)
    # or produce type mismatch in one top-level field (mostly avoided, since all reject identically)
    # We do these with low probability to maximize chance of divergence

    # Decide top-level corruption
    top_corrupt = draw(st.sampled_from([None, "missing", "duplicate_conflict", "duplicate_tags"]))
    top_missing_field = None
    top_duplicate_field = None

    if top_corrupt == "missing":
        # omit one field at top-level (random)
        top_missing_field = draw(st.sampled_from(FIELD_NAMES))
    elif top_corrupt == "duplicate_conflict":
        # duplicate one scalar field with conflicting type
        top_duplicate_field = draw(st.sampled_from(["id", "amount", "name", "status"]))
    elif top_corrupt == "duplicate_tags":
        # duplicate "tags" key with different array (should be accepted)
        top_duplicate_field = "tags"

    # Build top-level fields dict
    top_fields = {}

    def top_val_to_json(field):
        if field == "id":
            return id_json
        elif field == "amount":
            return amount_json
        elif field == "name":
            return name_json
        elif field == "status":
            return status_json
        elif field == "tags":
            return tags_json
        elif field == "child":
            return child_json
        else:
            raise RuntimeError("Unexpected field")

    for f in FIELD_NAMES:
        if f == top_missing_field:
            continue
        top_fields[f] = top_val_to_json(f)

    # Compose base fields string list
    base_fields = []
    for k,v in top_fields.items():
        base_fields.append(json_string(k) + ":" + v)

    # Add duplicate key if requested
    if top_duplicate_field is not None:
        if top_duplicate_field == "id":
            # duplicate id as string (conflict with int)
            base_fields.append(json_string("id") + ":" + json_string("conflict"))
        elif top_duplicate_field == "amount":
            # duplicate amount as number (conflict with string)
            base_fields.append(json_string("amount") + ":" + "123.45")
        elif top_duplicate_field == "name":
            # duplicate name as number (conflict with string or null)
            base_fields.append(json_string("name") + ":" + "123")
        elif top_duplicate_field == "status":
            # duplicate status as invalid enum string (conflict)
            base_fields.append(json_string("status") + ":" + json_string("enabled"))
        elif top_duplicate_field == "tags":
            # duplicate tags key with different array (last wins)
            dup_tags = gen_tags()
            base_fields.append(json_string("tags") + ":" + json_string_array(dup_tags))

    # Compose final JSON string
    json_text = "{" + ",".join(base_fields) + "}"

    # Return as bytes
    return json_text.encode("utf-8")