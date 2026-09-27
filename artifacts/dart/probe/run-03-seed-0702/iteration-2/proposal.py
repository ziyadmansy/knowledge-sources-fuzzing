from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Enum values for "status"
    statuses = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal with proper escaping of backslash and quote
    def json_string(s: str) -> str:
        # Minimal escaping for " and \ only, enough for this context
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Compose a JSON array of strings (tags)
    def json_tags():
        # tags must be array of strings, but try to produce edge cases:
        # - empty array
        # - array with one string
        # - array with multiple strings
        # Strings can be empty or normal words
        tag_strs = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        # Compose JSON array string
        inner = ",".join(json_string(t) for t in tag_strs)
        return "[" + inner + "]"

    # Compose a JSON value for "name": either null or string
    def json_name():
        # Nullable string
        if draw(st.booleans()):
            # null
            return "null"
        else:
            # string, possibly empty or normal text
            s = draw(st.text(min_size=0, max_size=20))
            return json_string(s)

    # Compose a JSON value for "amount": string
    def json_amount():
        # amount is string, but try edge cases: empty string, numeric string, normal string
        s = draw(st.one_of(
            st.just(""),
            st.from_regex(r"^\d+(\.\d+)?$", fullmatch=True),  # numeric string
            st.text(min_size=1, max_size=20)
        ))
        return json_string(s)

    # Compose a JSON value for "id": integer
    def json_id():
        # id is integer, try edge values and normal
        i = draw(st.integers(min_value=0, max_value=2**31-1))
        return str(i)

    # Compose a JSON value for "status": enum string
    def json_status():
        # Pick one of the valid enum values
        return json_string(draw(st.sampled_from(statuses)))

    # Compose a JSON value for "child": either null or a nested record (one level only)
    # To avoid deeper recursion, child.child must be null
    def json_child():
        if draw(st.booleans()):
            return "null"
        else:
            # Compose nested record with child.child = null always
            # Use mostly valid fields, but allow one subtle variation to try to cause divergence:
            # e.g. duplicate keys in child, or missing fields in child, or null name in child
            # But per strategy hint, vary only one or two things at a time.
            # We'll produce a fully valid nested record here to keep baseline.
            # The outer function can vary fields to cause divergence.
            # Compose fields for child record:
            cid = draw(st.integers(min_value=0, max_value=2**31-1))
            camount = draw(st.text(min_size=1, max_size=20))
            cname = draw(st.one_of(st.just("null"), st.text(min_size=0, max_size=20))).strip()
            if cname == "null":
                cname_json = "null"
            else:
                cname_json = json_string(cname)
            cstatus = draw(st.sampled_from(statuses))
            ctags = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))
            ctags_json = "[" + ",".join(json_string(t) for t in ctags) + "]"
            # child.child is null
            child_child_json = "null"
            # Compose child JSON object string
            child_fields = [
                '"id":' + str(cid),
                '"amount":' + json_string(camount),
                '"name":' + cname_json,
                '"status":' + json_string(cstatus),
                '"tags":' + ctags_json,
                '"child":' + child_child_json,
            ]
            # Possibly add duplicate keys in child to test last-wins behavior
            # But duplicates are accepted identically by all implementations, so no divergence
            # So keep unique keys here
            return "{" + ",".join(child_fields) + "}"

    # Compose the top-level record with all six fields
    # We'll produce mostly valid documents but vary one or two fields subtly to try to cause divergence
    # Strategy: produce valid document, then with small probability:
    # - swap type of one field to a borderline invalid type (e.g. "id" as string numeric)
    # - omit a field (not allowed by schema, but see if any implementation accepts)
    # - produce enum with different casing (known to be rejected by all, so no divergence)
    # - produce "name" as null or string (allowed)
    # - produce "tags" with empty array or array of strings
    # - produce "child" null or nested record
    # - produce duplicate keys for one field (last wins)
    # - produce extra unknown fields (accepted by all, no divergence)
    # - produce "amount" as string but empty or numeric string
    # - produce "id" as integer or string numeric (string numeric rejected by all)
    # - produce "status" as valid enum only (invalid rejected by all)
    # So to maximize chance of divergence, try:
    # - "id" as integer or string numeric (string numeric rejected by all)
    # - "amount" as string or number (number rejected by all)
    # - "name" as string or null (both accepted)
    # - "status" always valid enum
    # - "tags" always array of strings
    # - "child" null or nested record
    # - duplicate keys for one field (last wins)
    # - omit no fields (all fields always present)
    # - extra unknown fields (accepted by all)
    # Since no divergence found yet, try to produce documents with one field subtly off type but still valid JSON
    # to see if any implementation accepts differently.

    # Decide if we produce a subtle type mismatch on one field (only one field per document)
    subtle_type_mismatch_field = draw(st.one_of(
        st.none(),
        st.just("id"),
        st.just("amount"),
        st.just("name"),
        st.just("status"),
        st.just("tags"),
        st.just("child"),
    ))

    # Compose fields with possible subtle mismatch
    # id
    if subtle_type_mismatch_field == "id":
        # id as string numeric (known rejected by all, but try)
        id_val = json_string(str(draw(st.integers(min_value=0, max_value=2**31-1))))
    else:
        id_val = str(draw(st.integers(min_value=0, max_value=2**31-1)))

    # amount
    if subtle_type_mismatch_field == "amount":
        # amount as number (known rejected by all)
        amount_val = str(draw(st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)))
    else:
        amount_val = json_amount()

    # name
    if subtle_type_mismatch_field == "name":
        # name as number (known rejected by all)
        name_val = str(draw(st.integers(min_value=0, max_value=1000)))
    else:
        name_val = json_name()

    # status
    if subtle_type_mismatch_field == "status":
        # invalid enum (known rejected by all)
        status_val = json_string(draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses)))
    else:
        status_val = json_status()

    # tags
    if subtle_type_mismatch_field == "tags":
        # tags as array with one element number (known rejected by all)
        tags_val = "[" + str(draw(st.integers(min_value=0, max_value=1000))) + "]"
    else:
        tags_val = json_tags()

    # child
    if subtle_type_mismatch_field == "child":
        # child as empty object (known rejected by all)
        child_val = "{}"
    else:
        child_val = json_child()

    # Compose fields list
    fields = [
        '"id":' + id_val,
        '"amount":' + amount_val,
        '"name":' + name_val,
        '"status":' + status_val,
        '"tags":' + tags_val,
        '"child":' + child_val,
    ]

    # Possibly add duplicate keys for one field (last wins)
    # Only add duplicates if no subtle mismatch (to keep one variation at a time)
    if subtle_type_mismatch_field is None and draw(st.booleans()):
        # Pick a field to duplicate
        dup_field = draw(st.sampled_from(["id", "amount", "name", "status", "tags", "child"]))
        # Compose duplicate key with different value (valid type)
        if dup_field == "id":
            dup_val = str(draw(st.integers(min_value=0, max_value=2**31-1)))
        elif dup_field == "amount":
            dup_val = json_amount()
        elif dup_field == "name":
            dup_val = json_name()
        elif dup_field == "status":
            dup_val = json_status()
        elif dup_field == "tags":
            dup_val = json_tags()
        else:  # child
            dup_val = json_child()
        # Insert duplicate key at random position (append for simplicity)
        fields.append(f'"{dup_field}":{dup_val}')

    # Possibly add extra unknown fields (accepted by all, no divergence)
    if draw(st.booleans()):
        # Add 1 or 2 unknown fields with string or number values
        extra_count = draw(st.integers(min_value=1, max_value=2))
        for i in range(extra_count):
            key = f'"extra_field_{i}"'
            val = draw(st.one_of(
                json_string(draw(st.text(min_size=0, max_size=10))),
                str(draw(st.integers(min_value=0, max_value=1000)))
            ))
            fields.append(f"{key}:{val}")

    # Shuffle fields to vary order (duplicates last if any)
    # Keep duplicates last to respect last-wins semantics
    normal_fields = [f for f in fields if not f.startswith('"id":') or fields.count(f) == 1]
    # Actually simpler: shuffle all except duplicates at end
    # Find duplicates keys (keys appearing more than once)
    keys = [f.split(":", 1)[0] for f in fields]
    dup_keys = set(k for k in keys if keys.count(k) > 1)
    normal_fields = [f for f in fields if f.split(":", 1)[0] not in dup_keys]
    dup_fields = [f for f in fields if f.split(":", 1)[0] in dup_keys]
    normal_fields = draw(st.permutations(normal_fields))
    all_fields = list(normal_fields) + dup_fields

    # Compose final JSON object string
    json_obj = "{" + ",".join(all_fields) + "}"

    return json_obj.encode("utf-8")