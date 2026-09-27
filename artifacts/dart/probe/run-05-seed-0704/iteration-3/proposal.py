from hypothesis import strategies as st

# Helper to produce a JSON string literal with proper escaping of " and \ only (minimal)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping for JSON string
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper to produce JSON array of strings text from list of strings
def json_array_of_strings(lst):
    # lst is list of strings, produce JSON array text
    return '[' + ','.join(json_string_literal(s) for s in lst) + ']'

# Helper to produce JSON null text
json_null = "null"

# Allowed status strings
allowed_status = ["active", "inactive", "unknown"]

# Compose a JSON object text from dict of fieldname->text (field values already JSON text)
def json_object(fields):
    # fields: list of (key, json_value_text)
    # Compose JSON object text with fields in stable order
    parts = []
    for k, v in fields:
        parts.append(json_string_literal(k) + ':' + v)
    return '{' + ','.join(parts) + '}'

# Compose a JSON number text from int (no quotes)
def json_int_text(i):
    return str(i)

# Compose a JSON string text from string (quoted and escaped)
def json_str_text(s):
    return json_string_literal(s)

@st.composite
def generated_json(draw) -> bytes:
    """
    Produce syntactically valid JSON objects as bytes, representing the Record schema,
    with small controlled deviations to trigger behavioral divergence between
    four Dart JSON deserializers (manual, json_serializable, freezed, built_value).

    Strategy:
    - Start from a valid record with all fields present and well-typed.
    - Introduce exactly one or two small deviations (type or value) in one field or nested child.
    - Use bounded recursion for child (max depth 1 or 2).
    - Variations include:
      * "id": int normally, or string (known to be rejected by all, no divergence)
        but try int boundary values or string int vs string non-int.
      * "amount": string normally, try numeric string vs non-numeric string.
      * "name": string or null normally, try null vs string, or string vs int (known reject all).
      * "status": allowed strings normally, try unknown string or case variants.
      * "tags": array of strings normally, try empty array, array with empty string,
        array with one non-string element (known reject all), or missing field (known reject all).
      * "child": null or valid record normally, try null vs empty object (known reject all),
        try child with one field wrong type, or child with extra unknown fields.
    - Introduce one or two deviations only, to maximize chance of divergence.
    """

    # Max recursion depth for child
    MAX_DEPTH = 2

    # Generate a valid "id" int (positive, zero, negative, boundary)
    def gen_id():
        # Include some boundary values and normal positive ints
        return draw(st.one_of(
            st.integers(min_value=0, max_value=1000),
            st.just(0),
            st.just(-1),
            st.just(2147483647),  # max 32-bit int
            st.just(-2147483648), # min 32-bit int
        ))

    # Generate "amount" string normally numeric string or arbitrary string
    def gen_amount():
        # numeric string or arbitrary string
        return draw(st.one_of(
            st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Nd',))),
            st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')),
        ))

    # Generate "name" string or null
    def gen_name():
        # null or string
        return draw(st.one_of(
            st.none(),
            st.text(min_size=0, max_size=20, alphabet=st.characters(blacklist_characters='"\\')),
        ))

    # Generate "status" string from allowed or close variants
    def gen_status():
        # Mostly allowed strings, sometimes close variants to test rejection
        return draw(st.one_of(
            st.sampled_from(allowed_status),
            st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')),  # random string
            st.just("Active"),  # case variant
            st.just("inactive "), # trailing space
            st.just("unknown\n"), # newline
        ))

    # Generate "tags" array of strings
    def gen_tags():
        # array of strings, sometimes empty, sometimes with empty string
        return draw(st.lists(
            st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters='"\\')),
            min_size=0, max_size=5
        ))

    # Generate a valid record JSON text at given depth
    def gen_record(depth):
        # Compose fields with possible small deviations

        # Decide if this record will have a deviation or not
        # Probability to deviate at this level: 0.4
        deviate = draw(st.booleans())

        # Base valid fields
        id_val = gen_id()
        amount_val = gen_amount()
        name_val = gen_name()
        status_val = draw(st.sampled_from(allowed_status))
        tags_val = gen_tags()

        # child_val: null or nested record if depth < MAX_DEPTH
        if depth < MAX_DEPTH:
            child_val = draw(st.one_of(
                st.none(),
                gen_record(depth + 1)
            ))
        else:
            child_val = None

        # Now apply at most one or two deviations at this level if deviate==True
        # Possible deviations:
        # - id: string instead of int (known reject all, no divergence)
        # - id: int boundary or string numeric (try string numeric to test)
        # - amount: int instead of string (known reject all)
        # - amount: string numeric vs non-numeric
        # - name: int instead of string/null (known reject all)
        # - name: null vs string
        # - status: invalid string variants (case, trailing space)
        # - tags: array with one non-string element (known reject all)
        # - tags: empty array vs array with empty string
        # - child: null vs empty object (known reject all)
        # - child: child with one field wrong type (e.g. id string)
        # - child: child with extra unknown fields (accepted by all)
        # - missing fields (known reject all)
        # We want to produce deviations that might cause divergence:
        # For example, "status" with case variant might cause built_value to reject but others accept.
        # Or "child" with one field wrong type might cause different error types.
        # Or "name" null vs string might cause different decoding.

        # We'll pick one or two deviations randomly from a curated list.

        # First, build a dict of fields as JSON text
        fields = {}

        # id field: normally int as JSON number text
        id_json = json_int_text(id_val)

        # amount field: normally string JSON text
        amount_json = json_str_text(amount_val)

        # name field: null or string JSON text
        if name_val is None:
            name_json = json_null
        else:
            name_json = json_str_text(name_val)

        # status field: string JSON text
        status_json = json_str_text(status_val)

        # tags field: JSON array of strings
        tags_json = json_array_of_strings(tags_val)

        # child field: null or nested record JSON text
        if child_val is None:
            child_json = json_null
        else:
            child_json = child_val

        # Start with valid fields
        fields = [
            ("id", id_json),
            ("amount", amount_json),
            ("name", name_json),
            ("status", status_json),
            ("tags", tags_json),
            ("child", child_json),
        ]

        # If no deviation, return valid record JSON text
        if not deviate:
            return json_object(fields)

        # Otherwise, apply one or two deviations from below:

        # Define possible deviations as functions that take fields list and return modified fields list
        deviations = []

        # 1) "id" as string numeric (e.g. "123") instead of int
        def dev_id_string_numeric(fields):
            # Replace id field with string numeric
            for i, (k, v) in enumerate(fields):
                if k == "id":
                    fields[i] = (k, json_str_text(str(id_val)))
                    break
            return fields

        deviations.append(dev_id_string_numeric)

        # 2) "id" as string non-numeric (e.g. "abc")
        def dev_id_string_non_numeric(fields):
            for i, (k, v) in enumerate(fields):
                if k == "id":
                    fields[i] = (k, json_str_text("abc"))
                    break
            return fields

        deviations.append(dev_id_string_non_numeric)

        # 3) "amount" as numeric (int) instead of string (known reject all, but keep)
        def dev_amount_int(fields):
            for i, (k, v) in enumerate(fields):
                if k == "amount":
                    # Use id_val as int for amount numeric
                    fields[i] = (k, json_int_text(id_val))
                    break
            return fields

        deviations.append(dev_amount_int)

        # 4) "amount" as empty string (valid string but edge case)
        def dev_amount_empty_string(fields):
            for i, (k, v) in enumerate(fields):
                if k == "amount":
                    fields[i] = (k, json_str_text(""))
                    break
            return fields

        deviations.append(dev_amount_empty_string)

        # 5) "name" as int (known reject all)
        def dev_name_int(fields):
            for i, (k, v) in enumerate(fields):
                if k == "name":
                    fields[i] = (k, json_int_text(id_val))
                    break
            return fields

        deviations.append(dev_name_int)

        # 6) "name" null vs string (flip)
        def dev_name_flip_null_string(fields):
            for i, (k, v) in enumerate(fields):
                if k == "name":
                    if name_val is None:
                        # change null to string "nullname"
                        fields[i] = (k, json_str_text("nullname"))
                    else:
                        # change string to null
                        fields[i] = (k, json_null)
                    break
            return fields

        deviations.append(dev_name_flip_null_string)

        # 7) "status" invalid string (case variant or trailing space)
        def dev_status_invalid(fields):
            for i, (k, v) in enumerate(fields):
                if k == "status":
                    # pick one invalid variant
                    invalids = ["Active", "inactive ", "unknown\n", "invalid"]
                    fields[i] = (k, json_str_text(draw(st.sampled_from(invalids))))
                    break
            return fields

        deviations.append(dev_status_invalid)

        # 8) "tags" array with one non-string element (known reject all)
        def dev_tags_non_string(fields):
            for i, (k, v) in enumerate(fields):
                if k == "tags":
                    # Insert one int element in tags array
                    # Compose JSON array with strings plus one int element
                    arr = tags_val.copy()
                    if len(arr) == 0:
                        arr = ["tag1"]
                    # Insert int element at random position
                    pos = draw(st.integers(min_value=0, max_value=len(arr)))
                    # Compose JSON array text manually with one int element
                    parts = []
                    for idx, s in enumerate(arr):
                        if idx == pos:
                            parts.append(json_int_text(42))
                        parts.append(json_string_literal(s))
                    if pos == len(arr):
                        parts.append(json_int_text(42))
                    fields[i] = (k, '[' + ','.join(parts) + ']')
                    break
            return fields

        deviations.append(dev_tags_non_string)

        # 9) "tags" empty array (valid edge case)
        def dev_tags_empty_array(fields):
            for i, (k, v) in enumerate(fields):
                if k == "tags":
                    fields[i] = (k, "[]")
                    break
            return fields

        deviations.append(dev_tags_empty_array)

        # 10) "child" empty object {} (known reject all)
        def dev_child_empty_object(fields):
            for i, (k, v) in enumerate(fields):
                if k == "child":
                    fields[i] = (k, "{}")
                    break
            return fields

        deviations.append(dev_child_empty_object)

        # 11) "child" with one field wrong type (e.g. id string instead of int)
        def dev_child_id_string(fields):
            for i, (k, v) in enumerate(fields):
                if k == "child":
                    if child_val is None:
                        # create child with id string "123", other fields valid
                        child_fields = [
                            ("id", json_str_text("123")),
                            ("amount", json_str_text("100")),
                            ("name", json_null),
                            ("status", json_str_text("active")),
                            ("tags", "[]"),
                            ("child", json_null),
                        ]
                        fields[i] = (k, json_object(child_fields))
                    else:
                        # child_val is JSON text, parse not possible, so replace with above
                        child_fields = [
                            ("id", json_str_text("123")),
                            ("amount", json_str_text("100")),
                            ("name", json_null),
                            ("status", json_str_text("active")),
                            ("tags", "[]"),
                            ("child", json_null),
                        ]
                        fields[i] = (k, json_object(child_fields))
                    break
            return fields

        deviations.append(dev_child_id_string)

        # 12) "child" with extra unknown fields (accepted by all)
        def dev_child_extra_fields(fields):
            for i, (k, v) in enumerate(fields):
                if k == "child":
                    if child_val is None:
                        # create child with valid fields plus extra unknown
                        child_fields = [
                            ("id", json_int_text(1)),
                            ("amount", json_str_text("10")),
                            ("name", json_null),
                            ("status", json_str_text("active")),
                            ("tags", "[]"),
                            ("child", json_null),
                            ("extra_field", json_str_text("extra")),
                        ]
                        fields[i] = (k, json_object(child_fields))
                    else:
                        # Append extra field to existing child JSON text by string manipulation
                        # child_val is JSON text like {...}
                        # Insert before last } the extra field
                        s = child_val
                        if s.endswith('}'):
                            s = s[:-1] + ',"extra_field":' + json_str_text("extra") + '}'
                        fields[i] = (k, s)
                    break
            return fields

        deviations.append(dev_child_extra_fields)

        # 13) Remove one required field (known reject all)
        def dev_remove_field(fields):
            # Remove one random field except "id" (to avoid all reject same)
            removable = [f for f in fields if f[0] != "id"]
            if not removable:
                return fields
            rem = draw(st.sampled_from(removable))
            fields = [f for f in fields if f != rem]
            return fields

        deviations.append(dev_remove_field)

        # Pick one or two deviations randomly and apply in sequence
        num_devs = draw(st.integers(min_value=1, max_value=2))
        chosen_devs = draw(st.lists(st.sampled_from(deviations), min_size=num_devs, max_size=num_devs, unique=True))

        for dev in chosen_devs:
            fields = dev(fields)

        # Compose final JSON object text
        return json_object(fields).encode("utf-8")