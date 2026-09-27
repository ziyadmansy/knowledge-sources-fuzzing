from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON documents as bytes, encoding a Record with fields:
    {
      "id": <integer>,
      "amount": <string>,
      "name": <string or null>,
      "status": <one of "active", "inactive", "unknown">,
      "tags": <array of strings>,
      "child": <Record or null, one level of recursion normally>
    }
    
    Strategy:
    - Generate a mostly well-formed document.
    - Introduce exactly one or two subtle divergences from well-formedness:
      * missing fields (allowed only for nullable or non-nullable fields to test differences)
      * null for non-nullable fields (id, amount, status, tags)
      * wrong types for fields (e.g. number instead of string, string instead of enum)
      * unknown enum values or case variants
      * extra unknown keys or duplicate keys (only one duplicate key allowed)
      * missing or null nested objects (child)
    - Limit recursion depth to 1 (child can be null or a record with child=null)
    - Output JSON text as bytes
    
    This approach targets known divergence points from the problem statement.
    """
    # Constants
    STATUSES = ["active", "inactive", "unknown"]
    UNKNOWN_ENUMS = ["Active", "INACTIVE", "unknownx", "none", ""]  # case variants and unknowns
    MAX_TAGS = 3
    MAX_TAG_LENGTH = 8

    # Helpers to produce JSON text for values with minimal escaping (only quotes and backslash)
    def json_escape_str(s: str) -> str:
        # Escape backslash and double quote for JSON string
        return s.replace("\\", "\\\\").replace('"', '\\"')

    # Generate a JSON string value
    def json_str(draw, base=st.text(min_size=1, max_size=MAX_TAG_LENGTH)):
        s = draw(base)
        return '"' + json_escape_str(s) + '"'

    # Generate a JSON string or null (for nullable fields)
    def json_str_or_null(draw):
        if draw(st.booleans()):
            return "null"
        else:
            return json_str(draw)

    # Generate a JSON integer or null (for nullable fields)
    def json_int_or_null(draw):
        if draw(st.booleans()):
            return "null"
        else:
            # Use small integers for readability
            return str(draw(st.integers(min_value=0, max_value=1000)))

    # Generate JSON array of strings
    def json_array_of_strings(draw, allow_empty=True):
        length = draw(st.integers(min_value=0 if allow_empty else 1, max_value=MAX_TAGS))
        items = []
        for _ in range(length):
            items.append(json_str(draw))
        return "[" + ",".join(items) + "]"

    # Generate JSON array of strings or null (for nullable fields)
    def json_array_of_strings_or_null(draw):
        if draw(st.booleans()):
            return "null"
        else:
            return json_array_of_strings(draw)

    # Generate JSON enum value as string, or unknown variant, or null
    def json_enum(draw, allow_unknown=False, allow_null=False):
        choices = STATUSES[:]
        if allow_unknown:
            choices += UNKNOWN_ENUMS
        choice = draw(st.sampled_from(choices))
        if allow_null and draw(st.booleans()):
            return "null"
        return '"' + choice + '"'

    # Generate a child record JSON text or null
    # Limit recursion depth to 1: child.child is always null
    def json_child(draw):
        # 50% chance null
        if draw(st.booleans()):
            return "null"
        else:
            # child record with child=null
            child_obj = generate_record(draw, allow_child_null=True, recursion_depth=1)
            return child_obj

    # Generate a record JSON text with optional subtle malformations
    # recursion_depth: 0 = top-level, 1 = child level (no further recursion)
    # allow_child_null: if True, child can be null or record; else must be record
    def generate_record(draw, allow_child_null, recursion_depth=0):
        # Start with all fields present and well-formed
        # Then apply exactly one or two subtle divergences to cause divergence

        # Decide which divergences to apply (0,1 or 2)
        divergence_count = draw(st.integers(min_value=1, max_value=2))

        # Candidate divergences:
        # - missing field (only for nullable or non-nullable to test differences)
        # - null for non-nullable field
        # - wrong type for field (number instead of string, string instead of enum, etc)
        # - unknown enum value or case variant
        # - extra unknown key
        # - duplicate key (only one duplicate key allowed)
        # - missing nested object (child)
        # - null nested object (child)

        # Fields:
        # id: integer, non-nullable
        # amount: string, non-nullable
        # name: string or null, nullable
        # status: enum, non-nullable
        # tags: array of strings, non-nullable
        # child: record or null, nullable

        # Build a dict of fields with their JSON text values (strings)
        fields = {}

        # id: integer, non-nullable
        id_val = draw(st.integers(min_value=0, max_value=1000))
        fields["id"] = str(id_val)

        # amount: string, non-nullable
        amount_val = draw(st.text(min_size=1, max_size=10))
        fields["amount"] = '"' + json_escape_str(amount_val) + '"'

        # name: string or null, nullable
        if draw(st.booleans()):
            name_val = draw(st.text(min_size=1, max_size=10))
            fields["name"] = '"' + json_escape_str(name_val) + '"'
        else:
            fields["name"] = "null"

        # status: enum, non-nullable
        status_val = draw(st.sampled_from(STATUSES))
        fields["status"] = '"' + status_val + '"'

        # tags: array of strings, non-nullable
        tags_len = draw(st.integers(min_value=0, max_value=MAX_TAGS))
        tags_items = []
        for _ in range(tags_len):
            tag = draw(st.text(min_size=1, max_size=MAX_TAG_LENGTH))
            tags_items.append('"' + json_escape_str(tag) + '"')
        fields["tags"] = "[" + ",".join(tags_items) + "]"

        # child: record or null, nullable
        if recursion_depth == 0:
            # top-level: child can be null or record
            if draw(st.booleans()):
                fields["child"] = "null"
            else:
                # child record with recursion_depth=1, child=null
                child_obj = generate_record(draw, allow_child_null=True, recursion_depth=1)
                fields["child"] = child_obj
        else:
            # recursion_depth=1: child must be null (no further recursion)
            fields["child"] = "null"

        # Keep track of which fields are present
        present_fields = set(fields.keys())

        # Prepare list of possible divergences to apply
        divergences = []

        # 1) Missing field (only for nullable or non-nullable fields)
        # Missing id (non-nullable) triggers rejection by Moshi/kotlinx/Jackson, accepted by Gson
        # Missing amount (non-nullable)
        # Missing name (nullable)
        # Missing status (non-nullable enum)
        # Missing tags (non-nullable)
        # Missing child (nullable)
        for f in fields.keys():
            divergences.append(("missing_field", f))

        # 2) Null for non-nullable fields (id, amount, status, tags)
        for f in ["id", "amount", "status", "tags"]:
            divergences.append(("null_nonnullable", f))

        # 3) Wrong type for fields:
        # id: string or null (wrong type)
        divergences.append(("wrong_type", "id"))
        # amount: number (int or float), boolean, null
        divergences.append(("wrong_type", "amount"))
        # name: number (int), boolean (allowed?), null allowed
        divergences.append(("wrong_type", "name"))
        # status: unknown enum value, case variant, number, boolean, null
        divergences.append(("wrong_enum", "status"))
        divergences.append(("wrong_type", "status"))
        # tags: null, string instead of array, array with wrong types
        divergences.append(("wrong_type", "tags"))
        # child: null (allowed), wrong type (string, number, boolean)
        divergences.append(("wrong_type", "child"))
        divergences.append(("null_nonnullable", "child"))  # child is nullable, but test null for non-nullable child in recursion_depth=1

        # 4) Extra unknown key
        divergences.append(("extra_key", None))

        # 5) Duplicate key (only one duplicate key allowed)
        divergences.append(("duplicate_key", None))

        # Select divergences to apply (1 or 2)
        chosen_divergences = draw(st.lists(st.sampled_from(divergences), min_size=divergence_count, max_size=divergence_count, unique=True))

        # Apply divergences in order
        extra_keys = []
        duplicate_key = None
        for div_type, field in chosen_divergences:
            if div_type == "missing_field":
                # Remove the field if present
                if field in fields:
                    del fields[field]
                    present_fields.discard(field)
            elif div_type == "null_nonnullable":
                # Set field to null if non-nullable
                # Only apply if field present
                if field in fields:
                    fields[field] = "null"
            elif div_type == "wrong_type":
                # Replace field value with wrong type JSON
                if field not in fields:
                    continue
                if field == "id":
                    # id: string or null (string is wrong type)
                    # Use string number or random string
                    val = draw(st.one_of(
                        st.integers(min_value=0, max_value=1000).map(str),
                        st.text(min_size=1, max_size=5)
                    ))
                    fields[field] = '"' + json_escape_str(val) + '"'
                elif field == "amount":
                    # amount: number, boolean, null
                    choice = draw(st.sampled_from(["number", "boolean", "null"]))
                    if choice == "number":
                        val = draw(st.floats(allow_nan=False, allow_infinity=False)).__repr__()
                        fields[field] = val
                    elif choice == "boolean":
                        val = "true" if draw(st.booleans()) else "false"
                        fields[field] = val
                    else:
                        fields[field] = "null"
                elif field == "name":
                    # name: number, boolean, null
                    choice = draw(st.sampled_from(["number", "boolean", "string"]))
                    if choice == "number":
                        val = str(draw(st.integers(min_value=0, max_value=1000)))
                        fields[field] = val
                    elif choice == "boolean":
                        val = "true" if draw(st.booleans()) else "false"
                        fields[field] = val
                    else:
                        # string (valid)
                        val = draw(st.text(min_size=1, max_size=5))
                        fields[field] = '"' + json_escape_str(val) + '"'
                elif field == "status":
                    # status: number, boolean, null (wrong type)
                    choice = draw(st.sampled_from(["number", "boolean", "null"]))
                    if choice == "number":
                        val = str(draw(st.integers(min_value=0, max_value=10)))
                        fields[field] = val
                    elif choice == "boolean":
                        val = "true" if draw(st.booleans()) else "false"
                        fields[field] = val
                    else:
                        fields[field] = "null"
                elif field == "tags":
                    # tags: string, number, boolean, null
                    choice = draw(st.sampled_from(["string", "number", "boolean", "null"]))
                    if choice == "string":
                        val = '"' + json_escape_str(draw(st.text(min_size=1, max_size=5))) + '"'
                        fields[field] = val
                    elif choice == "number":
                        val = str(draw(st.integers(min_value=0, max_value=10)))
                        fields[field] = val
                    elif choice == "boolean":
                        val = "true" if draw(st.booleans()) else "false"
                        fields[field] = val
                    else:
                        fields[field] = "null"
                elif field == "child":
                    # child: string, number, boolean
                    choice = draw(st.sampled_from(["string", "number", "boolean"]))
                    if choice == "string":
                        val = '"' + json_escape_str(draw(st.text(min_size=1, max_size=5))) + '"'
                        fields[field] = val
                    elif choice == "number":
                        val = str(draw(st.integers(min_value=0, max_value=10)))
                        fields[field] = val
                    else:
                        val = "true" if draw(st.booleans()) else "false"
                        fields[field] = val
            elif div_type == "wrong_enum":
                # status: unknown enum value or case variant
                if field in fields:
                    val = draw(st.sampled_from(UNKNOWN_ENUMS))
                    fields[field] = '"' + val + '"'
            elif div_type == "extra_key":
                # Add an extra unknown key with a random value
                key = draw(st.text(min_size=1, max_size=5).filter(lambda s: s not in fields))
                # Value can be string, number, boolean, null
                val_type = draw(st.sampled_from(["string", "number", "boolean", "null"]))
                if val_type == "string":
                    val = '"' + json_escape_str(draw(st.text(min_size=1, max_size=5))) + '"'
                elif val_type == "number":
                    val = str(draw(st.integers(min_value=0, max_value=10)))
                elif val_type == "boolean":
                    val = "true" if draw(st.booleans()) else "false"
                else:
                    val = "null"
                extra_keys.append((key, val))
            elif div_type == "duplicate_key":
                # Pick a field to duplicate (must be present)
                if len(fields) == 0:
                    continue
                dup_field = draw(st.sampled_from(list(fields.keys())))
                duplicate_key = dup_field

        # Build JSON text
        # Order fields alphabetically for determinism
        field_items = []
        for k in sorted(fields.keys()):
            field_items.append('"' + json_escape_str(k) + '":' + fields[k])

        # Add extra keys if any
        for k, v in extra_keys:
            field_items.append('"' + json_escape_str(k) + '":' + v)

        # If duplicate key requested, add it again at the end with a different value
        if duplicate_key is not None:
            # For duplicate key, produce a different value than original
            orig_val = fields[duplicate_key]
            # Generate a different value of same type if possible
            if orig_val == "null":
                dup_val = '"dup"'
            elif orig_val.startswith('"') and orig_val.endswith('"'):
                # string - add suffix
                dup_val = orig_val[:-1] + "_dup\""
            elif orig_val.startswith("["):
                # array - add one more element
                dup_val = orig_val[:-1] + ',"dup"]'
            elif orig_val in ("true", "false"):
                # boolean - flip
                dup_val = "false" if orig_val == "true" else "true"
            else:
                # number or unknown - just add 1 if int
                try:
                    n = int(orig_val)
                    dup_val = str(n + 1)
                except Exception:
                    dup_val = '"dup"'
            field_items.append('"' + json_escape_str(duplicate_key) + '":' + dup_val)

        json_text = "{" + ",".join(field_items) + "}"
        return json_text

    # Generate top-level record JSON text
    json_text = generate_record(draw, allow_child_null=True, recursion_depth=0)

    return json_text.encode("utf-8")