from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations designed to provoke divergence among four Dart JSON deserializers.
    """

    # Constants for "status" enum
    valid_statuses = ["active", "inactive", "unknown"]

    # Helper: JSON string escaping (minimal, for Hypothesis-generated strings)
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Generate a valid "id" integer as string (to be rendered as number)
    # We always produce an integer number here, but later we may mutate type.
    id_int = draw(st.integers(min_value=0, max_value=2**31 - 1))

    # Generate "amount" as string representing a decimal number (e.g. "123.45")
    # We generate a string that looks like a number, but may mutate type later.
    amount_str = draw(
        st.one_of(
            st.decimals(min_value=0, max_value=1e9, places=2).map(lambda d: format(d, 'f')),
            st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in ".-" for c in s)),
        )
    )

    # Generate "name" as either null or a string (possibly empty)
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))

    # Generate "status" as one of the valid strings
    status_val = draw(st.sampled_from(valid_statuses))

    # Generate "tags" as array of strings (0 to 5 elements)
    tags_list = draw(st.lists(st.text(min_size=1, max_size=10), max_size=5))

    # Recursive generation of "child" record or null, max depth 1
    # To avoid deep recursion, we only generate child at depth 0
    def gen_child(depth=0):
        if depth > 0:
            return st.none()
        else:
            # Generate a well-formed child record (no further recursion)
            return generated_json_child()

    @st.composite
    def generated_json_child(draw):
        # Child record must be a valid record or null
        # To provoke divergence, we allow subtle mutations here too
        # But limit recursion to one level
        id_c = draw(st.integers(min_value=0, max_value=2**31 - 1))
        amount_c = draw(
            st.one_of(
                st.decimals(min_value=0, max_value=1e9, places=2).map(lambda d: format(d, 'f')),
                st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in ".-" for c in s)),
            )
        )
        name_c = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        status_c = draw(st.sampled_from(valid_statuses))
        tags_c = draw(st.lists(st.text(min_size=1, max_size=10), max_size=5))
        # No further child recursion here
        child_c = None

        # Compose child JSON object string
        parts = [
            '"id":' + str(id_c),
            '"amount":' + json_string(amount_c),
            '"name":' + ("null" if name_c is None else json_string(name_c)),
            '"status":' + json_string(status_c),
            '"tags":[' + ",".join(json_string(t) for t in tags_c) + "]",
            '"child":null',
        ]
        return "{" + ",".join(parts) + "}"

    child_val = draw(st.one_of(st.none(), gen_child()))

    # Compose the base JSON object as dict of fields
    base_fields = {
        "id": id_int,
        "amount": amount_str,
        "name": name_val,
        "status": status_val,
        "tags": tags_list,
        "child": child_val,
    }

    # Now, to provoke divergence, we apply one or two subtle mutations:
    # 1) Possibly omit "status" or "tags" (only built_value accepts missing)
    # 2) Possibly omit "name" or "child" (all accept missing)
    # 3) Possibly replace a field's type subtly (e.g. "id" as string, "amount" as number)
    # 4) Possibly insert an extra field (ignored by all, no divergence)
    # 5) Possibly set "tags" to empty array or array with non-string element (should cause rejection)
    # 6) Possibly set "child" to null or empty object or malformed object
    # 7) Possibly set "status" to invalid enum string (all reject)
    # 8) Possibly set "name" to int (all reject)
    # 9) Possibly set "amount" to int (all reject)
    # 10) Possibly omit "amount" (all reject)
    # 11) Possibly omit "id" (all reject)
    # 12) Possibly set "tags" to array with null element (all reject)
    # 13) Possibly set "child" to malformed nested record (should cause rejection)
    # 14) Possibly set "child" to empty object (all reject)
    # 15) Possibly set "child" to non-object (all reject)
    # 16) Possibly set "status" to null (all reject)
    # 17) Possibly set "name" to null (all accept)
    # 18) Possibly set "tags" to missing (only built_value accepts)
    # 19) Possibly set "status" to missing (only built_value accepts)
    # 20) Possibly set "child" to missing (all accept)
    # 21) Possibly set "name" to missing (all accept)
    # 22) Possibly set "tags" to array with empty string element (valid)
    # 23) Possibly set "tags" to array with whitespace string element (valid)
    # 24) Possibly set "amount" to empty string (should cause rejection)
    # 25) Possibly set "amount" to string with spaces (should cause rejection)
    # 26) Possibly set "id" to string number (should cause rejection)
    # 27) Possibly set "id" to float number (should cause rejection)
    # 28) Possibly set "tags" to array with numeric string elements (valid)
    # 29) Possibly set "tags" to array with unicode strings (valid)
    # 30) Possibly set "child" to nested record with one field wrong type (should cause rejection)

    # We pick one or two of these mutations at random to maximize divergence chances.

    # Helper to render a JSON value from Python value (int, str, None, list, or JSON string for child)
    def render_json_value(val):
        if val is None:
            return "null"
        elif isinstance(val, int):
            return str(val)
        elif isinstance(val, str):
            return json_string(val)
        elif isinstance(val, list):
            return "[" + ",".join(json_string(x) for x in val) + "]"
        elif isinstance(val, dict):
            # Should not happen here
            raise ValueError("Unexpected dict in render_json_value")
        else:
            # If val is a pre-rendered JSON string (for child)
            return val

    # Start with all fields present
    fields = dict(base_fields)

    # Define mutation functions

    def omit_field(field):
        if field in fields:
            del fields[field]

    def set_field(field, value):
        fields[field] = value

    def mutate_field_type(field):
        # Change type of field to provoke rejection or divergence
        if field == "id":
            # id normally int, try string or float string
            choice = draw(st.sampled_from(["string", "float"]))
            if choice == "string":
                # id as string number
                set_field("id", str(fields["id"]))
            else:
                # id as float number (string with decimal)
                set_field("id", float(fields["id"]) + 0.5)
        elif field == "amount":
            # amount normally string, try int or empty string or spaces
            choice = draw(st.sampled_from(["int", "empty", "spaces"]))
            if choice == "int":
                # amount as int (number)
                try:
                    intval = int(float(fields["amount"]))
                except Exception:
                    intval = 0
                set_field("amount", intval)
            elif choice == "empty":
                set_field("amount", "")
            else:
                set_field("amount", "  ")
        elif field == "name":
            # name normally string or null, try int
            set_field("name", 123)
        elif field == "status":
            # status normally valid enum string, try invalid string or null
            choice = draw(st.sampled_from(["invalid", "null"]))
            if choice == "invalid":
                set_field("status", "invalid_status")
            else:
                set_field("status", None)
        elif field == "tags":
            # tags normally array of strings, try array with non-string element or missing
            choice = draw(st.sampled_from(["nonstring", "missing", "null_element"]))
            if choice == "nonstring":
                set_field("tags", ["valid", 123])
            elif choice == "missing":
                omit_field("tags")
            else:
                set_field("tags", ["valid", None])
        elif field == "child":
            # child normally null or record, try non-object, empty object, malformed nested
            choice = draw(st.sampled_from(["nonobject", "emptyobject", "malformed_nested"]))
            if choice == "nonobject":
                set_field("child", 123)
            elif choice == "emptyobject":
                set_field("child", "{}")
            else:
                # malformed nested: child with one field wrong type
                malformed_child = {
                    "id": "string_instead_of_int",
                    "amount": "123.45",
                    "name": None,
                    "status": "active",
                    "tags": ["tag1"],
                    "child": None,
                }
                # Render malformed child as JSON string
                parts = []
                for k, v in malformed_child.items():
                    if v is None:
                        parts.append(f'"{k}":null')
                    elif isinstance(v, str):
                        parts.append(f'"{k}":{json_string(v)}')
                    elif isinstance(v, list):
                        parts.append(f'"{k}":[' + ",".join(json_string(x) for x in v) + "]")
                    else:
                        parts.append(f'"{k}":{v}')
                set_field("child", "{" + ",".join(parts) + "}")

    def omit_or_null_field(field):
        # Either omit or set to null (for nullable fields)
        choice = draw(st.sampled_from(["omit", "null"]))
        if choice == "omit":
            omit_field(field)
        else:
            set_field(field, None)

    # Pick one or two mutations to apply
    mutations = []

    # Always include one mutation to provoke divergence
    mutation_choices = [
        lambda: omit_field("status"),  # only built_value accepts missing status
        lambda: omit_field("tags"),    # only built_value accepts missing tags
        lambda: omit_or_null_field("name"),  # all accept missing or null name
        lambda: omit_or_null_field("child"),  # all accept missing or null child
        lambda: mutate_field_type("id"),
        lambda: mutate_field_type("amount"),
        lambda: mutate_field_type("name"),
        lambda: mutate_field_type("status"),
        lambda: mutate_field_type("tags"),
        lambda: mutate_field_type("child"),
    ]

    # Draw how many mutations to apply: 1 or 2
    n_mutations = draw(st.integers(min_value=1, max_value=2))

    chosen_mutations = draw(st.lists(st.sampled_from(mutation_choices), min_size=n_mutations, max_size=n_mutations, unique=True))

    for mut in chosen_mutations:
        mut()

    # Compose JSON string from fields

    # Render fields to JSON key:value pairs
    json_fields = []
    for k in ["id", "amount", "name", "status", "tags", "child"]:
        if k not in fields:
            continue
        v = fields[k]
        if k == "child":
            # child can be None, JSON string, or malformed string
            if v is None:
                json_fields.append(f'"child":null')
            elif isinstance(v, str):
                # v is pre-rendered JSON string for child or "{}"
                # If v is "{}", output as empty object
                if v == "{}":
                    json_fields.append(f'"child":{{}}')
                else:
                    json_fields.append(f'"child":{v}')
            else:
                # Should not happen
                json_fields.append(f'"child":null')
        elif k == "tags":
            # tags is list or possibly mutated
            if isinstance(v, list):
                # array of strings or possibly with non-string elements
                elems = []
                for e in v:
                    if isinstance(e, str):
                        elems.append(json_string(e))
                    elif e is None:
                        elems.append("null")
                    else:
                        # number or other type, render as JSON number or string
                        if isinstance(e, int) or isinstance(e, float):
                            elems.append(str(e))
                        else:
                            elems.append(json_string(str(e)))
                json_fields.append(f'"tags":[{",".join(elems)}]')
            elif v is None:
                json_fields.append(f'"tags":null')
            else:
                # malformed tags, e.g. string or number
                if isinstance(v, str):
                    json_fields.append(f'"tags":{json_string(v)}')
                else:
                    json_fields.append(f'"tags":{str(v)}')
        elif k == "name":
            if v is None:
                json_fields.append(f'"name":null')
            elif isinstance(v, int):
                json_fields.append(f'"name":{v}')
            else:
                json_fields.append(f'"name":{json_string(v)}')
        elif k == "amount":
            # amount normally string, but may be int or empty string
            if isinstance(v, int):
                json_fields.append(f'"amount":{v}')
            elif isinstance(v, float):
                # floats rendered as JSON number
                json_fields.append(f'"amount":{v}')
            elif isinstance(v, str):
                json_fields.append(f'"amount":{json_string(v)}')
            else:
                json_fields.append(f'"amount":null')
        elif k == "id":
            # id normally int, but may be string or float
            if isinstance(v, int):
                json_fields.append(f'"id":{v}')
            elif isinstance(v, float):
                json_fields.append(f'"id":{v}')
            elif isinstance(v, str):
                json_fields.append(f'"id":{json_string(v)}')
            else:
                json_fields.append(f'"id":null')
        elif k == "status":
            if v is None:
                json_fields.append(f'"status":null')
            elif isinstance(v, str):
                json_fields.append(f'"status":{json_string(v)}')
            else:
                json_fields.append(f'"status":null')

    json_text = "{" + ",".join(json_fields) + "}"

    return json_text.encode("utf-8")