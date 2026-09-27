from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and field names
    STATUS_VALUES = ["active", "inactive", "unknown"]
    FIELD_NAMES = ["id", "amount", "name", "status", "tags", "child"]

    # Strategy for "id": integer
    id_strat = st.integers(min_value=0, max_value=2**31-1)

    # Strategy for "amount": string representing a decimal number, allow edge cases
    # e.g. "0", "0.0", "123", "123.45", "1e10", "-0", "-123.45"
    # but always a string
    def amount_strings():
        # Compose decimal-like strings with optional sign and exponent
        sign = st.sampled_from(["", "-"])
        int_part = st.one_of(st.just("0"), st.from_regex(r"[1-9]\d*", fullmatch=True))
        frac_part = st.one_of(st.just(""), st.from_regex(r"\.\d+", fullmatch=True))
        exp_part = st.one_of(st.just(""), st.from_regex(r"[eE][+-]?\d+", fullmatch=True))
        return st.tuples(sign, int_part, frac_part, exp_part).map(lambda t: "".join(t))

    amount_strat = amount_strings()

    # Strategy for "name": nullable string or null
    # Use simple ASCII strings including empty string and some unicode
    name_strat = st.one_of(st.none(), st.text(min_size=0, max_size=20))

    # Strategy for "status": enum string from allowed values
    status_strat = st.sampled_from(STATUS_VALUES)

    # Strategy for "tags": array of strings (strings non-empty, ASCII printable)
    tags_strat = st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126)), min_size=0, max_size=5)

    # Forward declaration for child record (nullable)
    # We'll define a helper function for one-level recursion
    # To allow controlled recursion, we define a helper below

    # Helper to build a record JSON string (not bytes yet)
    # Accepts a dict of field values (already JSON strings)
    def build_record_json(fields_dict):
        # Compose JSON object string with fields in fixed order for determinism
        # Fields: id, amount, name, status, tags, child
        # All fields always present (name and child can be null)
        parts = []
        for key in FIELD_NAMES:
            parts.append(f'"{key}":{fields_dict[key]}')
        return "{" + ",".join(parts) + "}"

    # Strategy for JSON string encoding of a string value (with quotes and escapes)
    # We only allow simple ASCII printable chars for simplicity
    def json_string(s: str) -> str:
        # Escape backslash and quote
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Escape control chars (none expected in our generated strings)
        return f'"{s}"'

    # Strategy for JSON array of strings
    def json_array_of_strings(lst):
        # lst is a list of python strings
        # return JSON array string
        return "[" + ",".join(json_string(s) for s in lst) + "]"

    # Strategy for JSON null
    JSON_NULL = "null"

    # Compose a record JSON string with controlled recursion depth 0 or 1
    # depth=0 means child=null
    # depth=1 means child is a record with child=null (no deeper)
    def record_json_strategy(depth=0):
        # Compose fields as JSON strings
        # id: integer as number string
        id_val = id_strat.map(str)
        # amount: string JSON string
        amount_val = amount_strat.map(json_string)
        # name: nullable string JSON string or null
        name_val = name_strat.map(lambda v: JSON_NULL if v is None else json_string(v))
        # status: enum string JSON string
        status_val = status_strat.map(json_string)
        # tags: list of strings JSON array string
        tags_val = tags_strat.map(json_array_of_strings)

        if depth == 0:
            # child is null
            child_val = st.just(JSON_NULL)
        else:
            # child is a record with depth=0 (child=null)
            child_val = record_json_strategy(depth=0)

        # Combine all fields into a dict of JSON strings
        return st.tuples(id_val, amount_val, name_val, status_val, tags_val, child_val).map(
            lambda t: build_record_json({
                "id": t[0],
                "amount": t[1],
                "name": t[2],
                "status": t[3],
                "tags": t[4],
                "child": t[5]
            })
        )

    # We want to produce documents that are almost well-formed but with one or two small deviations
    # We will produce mostly well-formed documents (depth=1) and then with small probability introduce
    # one deviation in one field (e.g. type mismatch, missing field, invalid enum, duplicate keys with subtle differences)

    # Strategy for deviations:
    # 1) Type mismatch in one scalar field (id, amount, name, status)
    # 2) Invalid enum value for status
    # 3) Missing one non-nullable field (id, amount, status, tags) - but schema says all fields always present, so missing is deviation
    # 4) Duplicate keys with subtle differences (only in child object)
    # 5) Null in non-nullable fields (id, amount, status, tags) - deviation
    # 6) Type mismatch in child fields (one level only)
    # 7) Empty array for tags is allowed, so no deviation there

    # We will build a base record JSON string (well-formed) then apply one deviation

    base_record = record_json_strategy(depth=1)

    # Helper to produce a JSON string with one field replaced by a deviation string
    def replace_field(json_obj_str: str, field: str, new_value: str) -> str:
        # Replace the field's value in the JSON string
        # The field appears as "field":<value>
        # We replace the <value> part only
        # We assume no whitespace and fixed order of fields
        # So we can do a simple replace using string methods
        prefix = f'"{field}":'
        start = json_obj_str.find(prefix)
        if start == -1:
            # field not found, return original
            return json_obj_str
        start += len(prefix)
        # Find end of value: value can be number, string, null, array, or object
        # We parse until next comma or closing brace at same level
        # Since fields are fixed order and no whitespace, we can find next comma or }
        # starting from start
        end = start
        depth = 0
        in_string = False
        escape = False
        while end < len(json_obj_str):
            c = json_obj_str[end]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == '{' or c == '[':
                    depth += 1
                elif c == '}' or c == ']':
                    if depth == 0:
                        break
                    depth -= 1
                elif c == ',' and depth == 0:
                    break
            end += 1
        # Replace the substring json_obj_str[start:end] with new_value
        return json_obj_str[:start] + new_value + json_obj_str[end:]

    # Deviations generators

    # 1) Type mismatch for scalar fields:
    # id: integer expected, try string or null or boolean
    # amount: string expected, try number or null or boolean
    # name: string or null expected, try number or boolean
    # status: enum string expected, try number or boolean or null (invalid enum handled separately)
    # tags: array of strings expected, try string or array of numbers or null or boolean
    def type_mismatch_field(field):
        if field == "id":
            # produce JSON string for string, null, boolean
            val = draw(st.one_of(
                st.just(json_string("not-an-int")),
                st.just("null"),
                st.just("true"),
                st.just("false"),
            ))
            return val
        elif field == "amount":
            # produce JSON number, null, boolean
            val = draw(st.one_of(
                st.just("123.45"),
                st.just("null"),
                st.just("true"),
                st.just("false"),
            ))
            return val
        elif field == "name":
            # produce JSON number or boolean (invalid type)
            val = draw(st.one_of(
                st.just("123"),
                st.just("true"),
                st.just("false"),
            ))
            return val
        elif field == "status":
            # produce JSON number, boolean, null (invalid type)
            val = draw(st.one_of(
                st.just("123"),
                st.just("true"),
                st.just("false"),
                st.just("null"),
            ))
            return val
        elif field == "tags":
            # produce JSON string, array of numbers, null, boolean
            val = draw(st.one_of(
                json_string("not-an-array"),
                st.just("[1,2,3]"),
                st.just("null"),
                st.just("true"),
                st.just("false"),
            ))
            return val
        else:
            # unknown field, just null
            return "null"

    # 2) Invalid enum value for status (string not in enum)
    def invalid_enum_value():
        # string not in STATUS_VALUES
        invalids = ["enabled", "deactivated", "pending", "ACTIVE", "Inactive"]
        return json_string(draw(st.sampled_from(invalids)))

    # 3) Missing non-nullable field (id, amount, status, tags)
    # We remove the field entirely from JSON string
    def remove_field(json_obj_str: str, field: str) -> str:
        # Remove the field and its value including the comma if needed
        # Fields are in fixed order, so we can find the field and remove it carefully
        prefix = f'"{field}":'
        start = json_obj_str.find(prefix)
        if start == -1:
            return json_obj_str
        # Find end of value (same logic as replace_field)
        start_end = start + len(prefix)
        end = start_end
        depth = 0
        in_string = False
        escape = False
        while end < len(json_obj_str):
            c = json_obj_str[end]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == '{' or c == '[':
                    depth += 1
                elif c == '}' or c == ']':
                    if depth == 0:
                        break
                    depth -= 1
                elif c == ',' and depth == 0:
                    break
            end += 1
        # Remove trailing comma before or after field
        # If field is last, remove preceding comma
        # If field is not last, remove trailing comma
        # Check char before start and after end
        before = start - 1
        after = end
        if before >= 0 and json_obj_str[before] == ',':
            # Remove preceding comma
            remove_start = before
            remove_end = end
        elif after < len(json_obj_str) and json_obj_str[after] == ',':
            # Remove trailing comma
            remove_start = start
            remove_end = after + 1
        else:
            # No comma found, remove just field:value
            remove_start = start
            remove_end = end
        return json_obj_str[:remove_start] + json_obj_str[remove_end:]

    # 4) Duplicate keys with subtle differences in child object only
    # Duplicate a scalar field with conflicting type in child
    # For example, child has "id":123 and also "id":"string"
    # We produce JSON with child object having duplicate keys
    def duplicate_key_conflict(json_obj_str: str):
        # Find child object substring
        # child field is last field, so find '"child":{...}' or '"child":null'
        child_prefix = '"child":'
        start = json_obj_str.find(child_prefix)
        if start == -1:
            return json_obj_str
        start += len(child_prefix)
        if json_obj_str.startswith("null", start):
            # child is null, no duplicates possible, return original
            return json_obj_str
        if json_obj_str[start] != '{':
            return json_obj_str
        # Find end of child object (matching braces)
        pos = start
        depth = 0
        while pos < len(json_obj_str):
            c = json_obj_str[pos]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    break
            pos += 1
        child_obj_str = json_obj_str[start:pos+1]
        # Parse child_obj_str fields by splitting on commas at top level
        # We know fields order and no whitespace, so we can split by commas outside strings/brackets
        fields = []
        field_start = 1  # skip initial '{'
        depth = 0
        in_string = False
        escape = False
        for i in range(1, len(child_obj_str)-1):
            c = child_obj_str[i]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == '{' or c == '[':
                    depth += 1
                elif c == '}' or c == ']':
                    depth -= 1
                elif c == ',' and depth == 0:
                    fields.append(child_obj_str[field_start:i])
                    field_start = i+1
        fields.append(child_obj_str[field_start:-1])  # last field

        # Choose a scalar field to duplicate with conflicting type: id, amount, name, status
        scalar_fields = ["id", "amount", "name", "status"]
        # Find one present in child fields
        present_fields = []
        for f in scalar_fields:
            for fld in fields:
                if fld.startswith(f'"{f}":'):
                    present_fields.append(f)
                    break
        if not present_fields:
            # no scalar fields found, return original
            return json_obj_str
        # Pick one field to duplicate
        dup_field = draw(st.sampled_from(present_fields))
        # Find original field value
        orig_val = None
        for fld in fields:
            if fld.startswith(f'"{dup_field}":'):
                orig_val = fld[len(dup_field)+3:]
                break
        if orig_val is None:
            return json_obj_str
        # Produce conflicting value of different type
        # If original is number, produce string; if string produce number; if null produce string
        # We guess type by first char
        first_char = orig_val[0]
        if first_char == '"':
            # original string, produce number
            conflict_val = "12345"
        elif orig_val == "null":
            conflict_val = json_string("conflict")
        else:
            # number or boolean, produce string
            conflict_val = json_string("conflict")
        # Insert duplicate field after original
        # Insert before last } of child_obj_str
        new_child_obj_str = child_obj_str[:-1] + f',"{dup_field}":{conflict_val}' + '}'
        # Replace child object in json_obj_str
        new_json_obj_str = json_obj_str[:start] + new_child_obj_str + json_obj_str[pos+1:]
        return new_json_obj_str

    # 5) Null in non-nullable fields (id, amount, status, tags)
    def null_non_nullable_field(field):
        return "null"

    # 6) Type mismatch in child fields (one level only)
    # We produce a well-formed parent record with child object having one field type mismatch
    def child_type_mismatch(json_obj_str: str):
        # Find child object substring as in duplicate_key_conflict
        child_prefix = '"child":'
        start = json_obj_str.find(child_prefix)
        if start == -1:
            return json_obj_str
        start += len(child_prefix)
        if json_obj_str.startswith("null", start):
            # child is null, no mismatch possible, return original
            return json_obj_str
        if json_obj_str[start] != '{':
            return json_obj_str
        # Find end of child object (matching braces)
        pos = start
        depth = 0
        while pos < len(json_obj_str):
            c = json_obj_str[pos]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    break
            pos += 1
        child_obj_str = json_obj_str[start:pos+1]
        # Parse child fields as before
        fields = []
        field_start = 1  # skip initial '{'
        depth = 0
        in_string = False
        escape = False
        for i in range(1, len(child_obj_str)-1):
            c = child_obj_str[i]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == '{' or c == '[':
                    depth += 1
                elif c == '}' or c == ']':
                    depth -= 1
                elif c == ',' and depth == 0:
                    fields.append(child_obj_str[field_start:i])
                    field_start = i+1
        fields.append(child_obj_str[field_start:-1])  # last field

        # Pick a scalar field to mismatch
        scalar_fields = ["id", "amount", "name", "status", "tags"]
        present_fields = []
        for f in scalar_fields:
            for fld in fields:
                if fld.startswith(f'"{f}":'):
                    present_fields.append(f)
                    break
        if not present_fields:
            return json_obj_str
        mismatch_field = draw(st.sampled_from(present_fields))
        # Replace its value with a mismatched type
        mismatch_val = type_mismatch_field(mismatch_field)
        # Rebuild child object fields with replaced value
        new_fields = []
        replaced = False
        for fld in fields:
            if fld.startswith(f'"{mismatch_field}":') and not replaced:
                new_fields.append(f'"{mismatch_field}":{mismatch_val}')
                replaced = True
            else:
                new_fields.append(fld)
        new_child_obj_str = "{" + ",".join(new_fields) + "}"
        # Replace child object in json_obj_str
        new_json_obj_str = json_obj_str[:start] + new_child_obj_str + json_obj_str[pos+1:]
        return new_json_obj_str

    # Compose final strategy:
    # Draw a base well-formed record JSON string (depth=1)
    base = draw(base_record)

    # Decide which deviation to apply (or none)
    deviation_choices = [
        "none",
        "type_mismatch_top",
        "invalid_enum_status",
        "missing_field",
        "duplicate_key_child",
        "null_non_nullable",
        "type_mismatch_child",
    ]
    deviation = draw(st.sampled_from(deviation_choices))

    if deviation == "none":
        # Return base well-formed document as bytes
        return base.encode("utf-8")

    elif deviation == "type_mismatch_top":
        # Pick one top-level scalar field to mismatch type (id, amount, name, status, tags)
        field = draw(st.sampled_from(["id", "amount", "name", "status", "tags"]))
        val = type_mismatch_field(field)
        new_json = replace_field(base, field, val)
        return new_json.encode("utf-8")

    elif deviation == "invalid_enum_status":
        val = invalid_enum_value()
        new_json = replace_field(base, "status", val)
        return new_json.encode("utf-8")

    elif deviation == "missing_field":
        # Remove one non-nullable field (id, amount, status, tags)
        field = draw(st.sampled_from(["id", "amount", "status", "tags"]))
        new_json = remove_field(base, field)
        return new_json.encode("utf-8")

    elif deviation == "duplicate_key_child":
        new_json = duplicate_key_conflict(base)
        return new_json.encode("utf-8")

    elif deviation == "null_non_nullable":
        # Set one non-nullable field to null (id, amount, status, tags)
        field = draw(st.sampled_from(["id", "amount", "status", "tags"]))
        new_json = replace_field(base, field, "null")
        return new_json.encode("utf-8")

    elif deviation == "type_mismatch_child":
        new_json = child_type_mismatch(base)
        return new_json.encode("utf-8")

    else:
        # fallback, return base
        return base.encode("utf-8")