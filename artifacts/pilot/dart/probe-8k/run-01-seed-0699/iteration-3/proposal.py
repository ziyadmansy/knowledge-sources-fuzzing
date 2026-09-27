from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ['active', 'inactive', 'unknown']

    # Helper: produce a JSON string literal with proper escaping of " and \ only (minimal)
    def json_string(s: str) -> str:
        # minimal escaping for " and \ (enough for valid JSON strings)
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Recursive generator for a Record JSON object as string
    # Accepts parameters to tweak one or two fields to be "almost" valid but slightly off
    # to trigger divergences.
    # depth limits recursion to 1 level of child normally, but allow 2 levels max.
    def record_json(depth=0, tweak=None):
        # tweak is a dict with keys:
        #  - 'field': which field to tweak (id, amount, name, status, tags, child)
        #  - 'mode': what kind of tweak ('missing', 'wrong_type', 'wrong_enum', 'null_in_array', 'empty_object_child', 'extra_field', 'duplicate_key', 'null_name', 'null_child', 'empty_string_tag')
        #  - 'location': 'top' or 'child' (or 'child.child' for 2-level)
        #  - 'duplicate_key_field': if duplicate_key mode, which field to duplicate
        #  - 'duplicate_key_values': list of values for duplicates (last wins)
        #  - 'wrong_type_value': value to use for wrong type
        #  - 'wrong_enum_value': value to use for wrong enum
        #  - 'tags_array': array to use for tags (to test null in array, empty string, etc)
        #  - 'child_tweak': tweak dict for nested child

        # Base well-formed values:
        base_id = 123
        base_amount = "100.50"
        base_name = "example"
        base_status = "active"
        base_tags = ["tag1", "tag2"]
        base_child = None

        # Compose fields as strings (JSON text)
        # We will build a dict of field strings, then join with commas

        def field_json(field, val):
            # val is a JSON text string representing the value (including quotes for strings)
            return json_string(field) + ":" + val

        # id: integer
        id_val = str(base_id)
        # amount: string
        amount_val = json_string(base_amount)
        # name: string or null
        name_val = json_string(base_name)
        # status: enum string
        status_val = json_string(base_status)
        # tags: array of strings
        tags_val = "[" + ",".join(json_string(t) for t in base_tags) + "]"
        # child: null or nested record JSON
        child_val = "null"

        # Apply tweaks if any and if location matches
        def applies_to(loc):
            return tweak is not None and tweak.get('location', 'top') == loc

        # Helper to produce nested child JSON string with possible nested tweak
        def make_child(tweak_child=None):
            # limit recursion depth to 2
            if depth >= 2:
                return "null"
            return record_json(depth=depth+1, tweak=tweak_child)

        # Apply tweaks to top-level or child fields
        if applies_to('top'):
            f = tweak['field']
            mode = tweak.get('mode')
            if mode == 'missing':
                # omit the field entirely
                if f == 'id':
                    id_val = None
                elif f == 'amount':
                    amount_val = None
                elif f == 'name':
                    name_val = None
                elif f == 'status':
                    status_val = None
                elif f == 'tags':
                    tags_val = None
                elif f == 'child':
                    child_val = None
            elif mode == 'wrong_type':
                # replace with wrong type value (string for int, int for string, etc)
                wval = tweak.get('wrong_type_value')
                if f == 'id':
                    id_val = wval  # e.g. '"1"' (string) instead of int
                elif f == 'amount':
                    amount_val = wval  # e.g. 100 (int) instead of string
                elif f == 'name':
                    name_val = wval  # e.g. 123 (int) instead of string/null
                elif f == 'status':
                    status_val = wval  # e.g. 123 (int) instead of enum string
                elif f == 'tags':
                    tags_val = wval  # e.g. string instead of array
                elif f == 'child':
                    child_val = wval  # e.g. empty object or wrong type
            elif mode == 'wrong_enum':
                # status field with invalid enum string
                if f == 'status':
                    status_val = json_string(tweak.get('wrong_enum_value', 'invalid'))
            elif mode == 'null_in_array':
                # tags array with null inside
                if f == 'tags':
                    arr = tweak.get('tags_array', ['tag1', 'tag2'])
                    tags_val = "[" + ",".join(json_string(t) if t is not None else "null" for t in arr) + "]"
            elif mode == 'empty_object_child':
                # child is empty object {}
                if f == 'child':
                    child_val = "{}"
            elif mode == 'extra_field':
                # add an extra unknown field with fixed value
                # handled later by adding extra field after main fields
                pass
            elif mode == 'duplicate_key':
                # duplicate a key with given values, last wins
                # handled later by special construction
                pass
            elif mode == 'null_name':
                if f == 'name':
                    name_val = "null"
            elif mode == 'null_child':
                if f == 'child':
                    child_val = "null"
            elif mode == 'empty_string_tag':
                if f == 'tags':
                    arr = tweak.get('tags_array', [""])
                    tags_val = "[" + ",".join(json_string(t) for t in arr) + "]"

        if applies_to('child'):
            # tweak applies to child record
            # build child_val as nested record_json with tweak
            child_val = make_child(tweak_child=tweak)

        if applies_to('child.child'):
            # tweak applies to grandchild record
            # build child_val with nested tweak at depth+1
            # so child_val is record_json(depth=depth+1, tweak=...)
            # but tweak must be adjusted to location 'child'
            # We do this by passing tweak with location='child' to child record_json,
            # which will apply it there.
            child_val = make_child(tweak_child={'field': tweak['field'], 'mode': tweak.get('mode'), 'location': 'child', **{k:v for k,v in tweak.items() if k not in ('field','mode','location')}})

        # Compose fields list, skipping None (missing)
        fields = []
        if id_val is not None:
            fields.append(field_json("id", id_val))
        if amount_val is not None:
            fields.append(field_json("amount", amount_val))
        if name_val is not None:
            fields.append(field_json("name", name_val))
        if status_val is not None:
            fields.append(field_json("status", status_val))
        if tags_val is not None:
            fields.append(field_json("tags", tags_val))
        if child_val is not None:
            fields.append(field_json("child", child_val))

        # Handle extra_field mode (adds an extra unknown field)
        if tweak is not None and tweak.get('mode') == 'extra_field' and applies_to(tweak.get('location', 'top')):
            fields.append(field_json("extra_unknown_field", json_string("extra_value")))

        # Handle duplicate_key mode: duplicate one key with given values, last wins
        if tweak is not None and tweak.get('mode') == 'duplicate_key' and applies_to(tweak.get('location', 'top')):
            # We must produce JSON text with duplicate keys for the chosen field
            # The values are in tweak['duplicate_key_values'], a list of JSON text values
            # The other fields appear once normally.
            # We produce a string manually, not using fields list.
            key = tweak['duplicate_key_field']
            values = tweak['duplicate_key_values']
            # Compose all fields except the duplicated one
            other_fields = []
            for f, v in [("id", id_val), ("amount", amount_val), ("name", name_val), ("status", status_val), ("tags", tags_val), ("child", child_val)]:
                if f == key or v is None:
                    continue
                other_fields.append(field_json(f, v))
            # Compose duplicated keys with values in order
            dup_fields = [field_json(key, val) for val in values]
            # Join all fields: other fields + duplicated keys (duplicates last)
            all_fields = other_fields + dup_fields
            return ("{" + ",".join(all_fields) + "}").encode("utf-8")

        # Compose normal JSON object string
        json_text = "{" + ",".join(fields) + "}"
        return json_text.encode("utf-8")

    # Strategy to pick a tweak or None (mostly None to produce mostly well-formed)
    # We bias towards no tweak, but sometimes produce one tweak to trigger divergences.
    tweak_none = st.none()
    tweak_field = st.sampled_from(["id", "amount", "name", "status", "tags", "child"])
    tweak_location = st.sampled_from(["top", "child", "child.child"])
    tweak_mode = st.sampled_from([
        "missing",
        "wrong_type",
        "wrong_enum",
        "null_in_array",
        "empty_object_child",
        "extra_field",
        "duplicate_key",
        "null_name",
        "null_child",
        "empty_string_tag",
    ])

    # Values for wrong types per field
    wrong_type_values = {
        "id": json_string("1"),  # string instead of int
        "amount": "100",         # int instead of string
        "name": "123",           # int instead of string/null (as JSON text)
        "status": "123",         # int instead of enum string
        "tags": json_string("not_array"),  # string instead of array
        "child": "{}",           # empty object (invalid child)
    }

    # Values for wrong enum
    wrong_enum_value = "invalid_status"

    # Tags arrays for null_in_array and empty_string_tag
    tags_with_null = ["tag1", None, "tag2"]
    tags_with_empty_string = ["", "tag2"]

    # Duplicate key values examples (JSON text)
    duplicate_key_values_examples = {
        "id": ["1", "2", "3"],  # all strings (wrong type) to test last wins
        "name": [json_string("first"), json_string("second"), "null"],
        "status": [json_string("active"), json_string("inactive"), json_string("unknown")],
    }

    # Compose tweak dict strategy
    def tweak_strategy():
        # Pick a mode first
        mode = draw(tweak_mode)
        field = draw(tweak_field)
        location = draw(tweak_location)

        # Compose tweak dict depending on mode
        if mode == "wrong_type":
            wval = wrong_type_values.get(field)
            if wval is None:
                # fallback to string "wrong"
                wval = json_string("wrong")
            return {"field": field, "mode": mode, "location": location, "wrong_type_value": wval}
        elif mode == "wrong_enum":
            if field != "status":
                # invalid mode for non-status field, fallback to missing
                return {"field": field, "mode": "missing", "location": location}
            return {"field": field, "mode": mode, "location": location, "wrong_enum_value": wrong_enum_value}
        elif mode == "null_in_array":
            if field != "tags":
                # fallback to missing
                return {"field": field, "mode": "missing", "location": location}
            return {"field": field, "mode": mode, "location": location, "tags_array": tags_with_null}
        elif mode == "empty_string_tag":
            if field != "tags":
                return {"field": field, "mode": "missing", "location": location}
            return {"field": field, "mode": mode, "location": location, "tags_array": tags_with_empty_string}
        elif mode == "empty_object_child":
            if field != "child":
                return {"field": field, "mode": "missing", "location": location}
            return {"field": field, "mode": mode, "location": location}
        elif mode == "extra_field":
            # extra_field can apply anywhere
            return {"field": field, "mode": mode, "location": location}
        elif mode == "duplicate_key":
            # duplicate_key only for id, name, status (fields that appear once normally)
            key = draw(st.sampled_from(["id", "name", "status"]))
            vals = duplicate_key_values_examples[key]
            return {"field": field, "mode": mode, "location": location, "duplicate_key_field": key, "duplicate_key_values": vals}
        elif mode == "missing":
            return {"field": field, "mode": mode, "location": location}
        elif mode == "null_name":
            if field != "name":
                return {"field": field, "mode": "missing", "location": location}
            return {"field": field, "mode": mode, "location": location}
        elif mode == "null_child":
            if field != "child":
                return {"field": field, "mode": "missing", "location": location}
            return {"field": field, "mode": mode, "location": location}
        else:
            # fallback no tweak
            return None

    # Draw tweak or None (mostly None)
    tweak_or_none = draw(st.one_of(tweak_none, tweak_strategy()))

    # Generate JSON bytes with optional tweak
    return record_json(tweak=tweak_or_none)