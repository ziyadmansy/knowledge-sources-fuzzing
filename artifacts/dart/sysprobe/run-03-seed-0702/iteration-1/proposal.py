from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python str (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars minimally
        # Hypothesis strings are unicode, so escape control chars and quotes
        def esc_char(c):
            if c == '"':
                return '\\"'
            elif c == '\\':
                return '\\\\'
            elif c == '\b':
                return '\\b'
            elif c == '\f':
                return '\\f'
            elif c == '\n':
                return '\\n'
            elif c == '\r':
                return '\\r'
            elif c == '\t':
                return '\\t'
            elif ord(c) < 0x20:
                # Control chars as \u00XX
                return '\\u%04x' % ord(c)
            else:
                return c
        return '"' + ''.join(esc_char(c) for c in s) + '"'

    # Compose a JSON array of strings (all strings)
    # We want to sometimes produce null for "tags" only for built_value acceptance (Probe 10,20)
    # But we want to vary that only in child, not top-level, to avoid all rejecting.
    # So top-level tags: always array of strings (non-empty or empty)
    # child tags: sometimes null or array of strings

    # Compose a JSON value for "tags" field, param: allow_null (bool)
    def tags_json(allow_null: bool) -> st.SearchStrategy[str]:
        # array of strings, possibly empty
        arr = st.lists(st.text(min_size=0, max_size=10), max_size=5).map(
            lambda lst: "[" + ",".join(json_string(s) for s in lst) + "]"
        )
        if allow_null:
            return st.one_of(st.just("null"), arr)
        else:
            return arr

    # Compose a JSON value for "name" field: string or null
    name_json = st.one_of(st.none(), st.text(min_size=0, max_size=20)).map(
        lambda v: "null" if v is None else json_string(v)
    )

    # Compose a JSON value for "status" field: one of the enum strings (case sensitive)
    # We want to test boundary cases, so sometimes produce valid, sometimes invalid to cause rejection
    # But per instructions, only produce valid enum values here to avoid all rejecting
    status_json = st.sampled_from(STATUS_VALUES).map(json_string)

    # Compose a JSON value for "amount" field: string (always string, never null or number)
    amount_json = st.text(min_size=1, max_size=20).map(json_string)

    # Compose a JSON value for "id" field: integer (always integer, never null)
    id_json = st.integers(min_value=0, max_value=1000000).map(str)

    # Compose a JSON object for "child" field: either null or a nested record (one level only)
    # We want to vary child presence and content to trigger divergences:
    # built_value accepts missing child, others reject (Probe 6)
    # built_value accepts null tags in child, others reject (Probe 20)
    # all reject null id in child (Probe 19)
    # So child can be null or a valid record with tags possibly null

    # To avoid broad malformation, child is either null or a valid record with tags possibly null
    # We do not omit fields in child (except maybe tags null), to avoid all rejecting

    # Compose child record JSON string
    @st.composite
    def child_record(draw) -> str:
        # id: int (not null)
        cid = draw(id_json)
        # amount: string
        camount = draw(amount_json)
        # name: string or null
        cname = draw(name_json)
        # status: valid enum string
        cstatus = draw(status_json)
        # tags: allow null to trigger built_value acceptance divergence
        ctags = draw(tags_json(allow_null=True))
        # child: always null (no recursion deeper)
        cchild = "null"

        # Compose JSON object with all fields present
        # Order fields consistently
        obj = (
            '{'
            + '"id":' + cid + ','
            + '"amount":' + camount + ','
            + '"name":' + cname + ','
            + '"status":' + cstatus + ','
            + '"tags":' + ctags + ','
            + '"child":' + cchild
            + '}'
        )
        return obj

    # Compose top-level child field: either null or child record
    child_field = st.one_of(st.just("null"), child_record())

    # Compose top-level tags field: always array of strings (never null)
    top_tags = tags_json(allow_null=False)

    # Compose top-level record JSON string
    # We want to vary one or two fields at a time from valid baseline to maximize divergence
    # Strategy: produce a valid baseline, then with small probability mutate one field to a borderline value

    # Baseline fields
    base_id = id_json
    base_amount = amount_json
    base_name = name_json
    base_status = status_json
    base_tags = top_tags
    base_child = child_field

    # Draw baseline values
    id_val = draw(base_id)
    amount_val = draw(base_amount)
    name_val = draw(base_name)
    status_val = draw(base_status)
    tags_val = draw(base_tags)
    child_val = draw(base_child)

    # Now decide whether to mutate one field to a borderline value to trigger divergence
    # Possible mutations:
    # 1) tags null at top-level (should be rejected by all except built_value accepts null tags only in child, so top-level null tags rejected by all)
    # 2) tags null in child (already possible)
    # 3) missing fields (all reject except built_value accepts missing tags and child)
    # 4) null for non-nullable fields (id, amount, status) - all reject except built_value accepts null tags
    # 5) wrong types for fields (e.g. number for amount)
    # 6) duplicate keys with different values (last wins)
    # 7) unknown enum values (all reject)
    # 8) null name (accepted by all)
    # 9) missing name (all reject)
    # 10) missing child (built_value accepts, others reject)
    # 11) null child (accepted by all)
    # 12) nested child with null tags (built_value accepts, others reject)
    # 13) nested child with null id (all reject)
    # 14) nested child missing tags (built_value accepts, others reject)
    # 15) nested child missing child (built_value accepts, others reject)

    # We want to produce only syntactically valid JSON objects, so no missing fields by omission, but we can simulate missing by duplicate keys with null or by explicit nulls.

    # We will implement a small mutation set that changes one or two fields to borderline values.

    mutation_choices = [
        "none",             # no mutation, baseline valid
        "top_tags_null",    # top-level tags null (all reject except built_value accepts null tags only in child)
        "top_tags_wrong_type", # top-level tags as array with non-string element (all reject)
        "top_amount_number", # amount as number (all reject)
        "top_id_null",      # id null (all reject)
        "top_status_invalid", # status invalid enum (all reject)
        "top_name_missing", # simulate missing name by duplicate keys: first with value, second missing (not possible in JSON, so skip)
        "top_child_missing", # simulate missing child by duplicate keys: first with value, second missing (skip)
        "top_child_null",   # child null (accepted by all)
        "child_tags_null",  # child tags null (built_value accepts, others reject)
        "child_tags_wrong_type", # child tags array with non-string element (all reject)
        "child_id_null",    # child id null (all reject)
        "child_missing_tags", # simulate missing tags in child (skip)
        "duplicate_keys",   # duplicate keys at top-level, last wins
    ]

    mutation = draw(st.sampled_from(mutation_choices))

    # Compose fields as dict to allow duplicate keys if needed
    # We'll build a list of (key,json_value) pairs, then join with commas

    fields = [
        ("id", id_val),
        ("amount", amount_val),
        ("name", name_val),
        ("status", status_val),
        ("tags", tags_val),
        ("child", child_val),
    ]

    # Apply mutations
    if mutation == "none":
        # no change
        pass

    elif mutation == "top_tags_null":
        # top-level tags null (all reject except built_value accepts null tags only in child)
        fields = [
            (k, v) if k != "tags" else (k, "null")
            for (k, v) in fields
        ]

    elif mutation == "top_tags_wrong_type":
        # top-level tags array with non-string element (e.g. [1, "a"])
        wrong_tags = '[1,"a"]'
        fields = [
            (k, v) if k != "tags" else (k, wrong_tags)
            for (k, v) in fields
        ]

    elif mutation == "top_amount_number":
        # amount as number (e.g. 12345)
        fields = [
            (k, v) if k != "amount" else (k, "12345")
            for (k, v) in fields
        ]

    elif mutation == "top_id_null":
        # id null
        fields = [
            (k, v) if k != "id" else (k, "null")
            for (k, v) in fields
        ]

    elif mutation == "top_status_invalid":
        # status invalid enum string (e.g. "pending")
        fields = [
            (k, v) if k != "status" else (k, json_string("pending"))
            for (k, v) in fields
        ]

    elif mutation == "top_name_missing":
        # Cannot omit keys in JSON object, so skip this mutation
        pass

    elif mutation == "top_child_missing":
        # Cannot omit keys in JSON object, so skip this mutation
        pass

    elif mutation == "top_child_null":
        # child null (already possible)
        fields = [
            (k, v) if k != "child" else (k, "null")
            for (k, v) in fields
        ]

    elif mutation == "child_tags_null":
        # child tags null (built_value accepts, others reject)
        # If child is null, replace with a child record with tags null
        # If child is record, replace tags with null
        if child_val == "null":
            # create child record with tags null
            child_obj = draw(child_record())
            # parse and replace tags with null by string manipulation
            # safer to rebuild child record with tags null
            # but we cannot parse JSON here, so just rebuild child record with tags null
            # We'll do a new draw for child_record with tags null forced
            @st.composite
            def child_record_tags_null(draw):
                cid = draw(id_json)
                camount = draw(amount_json)
                cname = draw(name_json)
                cstatus = draw(status_json)
                ctags = "null"
                cchild = "null"
                obj = (
                    '{'
                    + '"id":' + cid + ','
                    + '"amount":' + camount + ','
                    + '"name":' + cname + ','
                    + '"status":' + cstatus + ','
                    + '"tags":' + ctags + ','
                    + '"child":' + cchild
                    + '}'
                )
                return obj
            child_val = draw(child_record_tags_null())
        else:
            # child is a record string, replace tags field with null by string replacement
            # We can do a regex replace or simple replace of tags array with tags:null
            # But no regex allowed, so do a simple replace of tags array with tags:null
            # Find '"tags":' and replace the value after it with null until next comma or }
            # We can do a simple split on '"tags":' and then replace after it
            parts = child_val.split('"tags":')
            if len(parts) == 2:
                prefix = parts[0]
                suffix = parts[1]
                # suffix starts with array or null or something, find end of value
                # value ends at first comma or }
                # find first comma or }
                comma_pos = suffix.find(",")
                brace_pos = suffix.find("}")
                if comma_pos == -1:
                    comma_pos = 1_000_000
                if brace_pos == -1:
                    brace_pos = 1_000_000
                end_pos = min(comma_pos, brace_pos)
                new_suffix = "null" + suffix[end_pos:]
                child_val = prefix + '"tags":' + new_suffix
            else:
                # no tags field? should not happen, keep as is
                pass
        # update fields
        fields = [
            (k, v) if k != "child" else (k, child_val)
            for (k, v) in fields
        ]

    elif mutation == "child_tags_wrong_type":
        # child tags array with non-string element (e.g. [1,"a"])
        # similar to above, replace tags field in child with '[1,"a"]'
        wrong_tags = '[1,"a"]'
        if child_val == "null":
            # create child record with wrong tags
            @st.composite
            def child_record_tags_wrong(draw):
                cid = draw(id_json)
                camount = draw(amount_json)
                cname = draw(name_json)
                cstatus = draw(status_json)
                ctags = wrong_tags
                cchild = "null"
                obj = (
                    '{'
                    + '"id":' + cid + ','
                    + '"amount":' + camount + ','
                    + '"name":' + cname + ','
                    + '"status":' + cstatus + ','
                    + '"tags":' + ctags + ','
                    + '"child":' + cchild
                    + '}'
                )
                return obj
            child_val = draw(child_record_tags_wrong())
        else:
            parts = child_val.split('"tags":')
            if len(parts) == 2:
                prefix = parts[0]
                suffix = parts[1]
                comma_pos = suffix.find(",")
                brace_pos = suffix.find("}")
                if comma_pos == -1:
                    comma_pos = 1_000_000
                if brace_pos == -1:
                    brace_pos = 1_000_000
                end_pos = min(comma_pos, brace_pos)
                new_suffix = wrong_tags + suffix[end_pos:]
                child_val = prefix + '"tags":' + new_suffix
            else:
                pass
        fields = [
            (k, v) if k != "child" else (k, child_val)
            for (k, v) in fields
        ]

    elif mutation == "child_id_null":
        # child id null (all reject)
        if child_val == "null":
            # create child record with id null
            @st.composite
            def child_record_id_null(draw):
                cid = "null"
                camount = draw(amount_json)
                cname = draw(name_json)
                cstatus = draw(status_json)
                ctags = draw(tags_json(allow_null=True))
                cchild = "null"
                obj = (
                    '{'
                    + '"id":' + cid + ','
                    + '"amount":' + camount + ','
                    + '"name":' + cname + ','
                    + '"status":' + cstatus + ','
                    + '"tags":' + ctags + ','
                    + '"child":' + cchild
                    + '}'
                )
                return obj
            child_val = draw(child_record_id_null())
        else:
            parts = child_val.split('"id":')
            if len(parts) == 2:
                prefix = parts[0]
                suffix = parts[1]
                comma_pos = suffix.find(",")
                brace_pos = suffix.find("}")
                if comma_pos == -1:
                    comma_pos = 1_000_000
                if brace_pos == -1:
                    brace_pos = 1_000_000
                end_pos = min(comma_pos, brace_pos)
                new_suffix = "null" + suffix[end_pos:]
                child_val = prefix + '"id":' + new_suffix
            else:
                pass
        fields = [
            (k, v) if k != "child" else (k, child_val)
            for (k, v) in fields
        ]

    elif mutation == "child_missing_tags":
        # cannot omit keys, skip
        pass

    elif mutation == "duplicate_keys":
        # duplicate keys at top-level, last wins
        # pick one field to duplicate with different value
        dup_field = draw(st.sampled_from(["id", "amount", "name", "status", "tags", "child"]))
        # produce a different value for that field
        def different_value(field, old_val):
            if field == "id":
                # different int as string
                new_int = str((int(old_val) + 1) % 1000000) if old_val.isdigit() else "123"
                return new_int
            elif field == "amount":
                # different string
                return json_string("dup_amount")
            elif field == "name":
                # different string or null
                if old_val == "null":
                    return json_string("dup_name")
                else:
                    return "null"
            elif field == "status":
                # different valid enum different from old_val
                for s in STATUS_VALUES:
                    if json_string(s) != old_val:
                        return json_string(s)
                return json_string("active")
            elif field == "tags":
                # different array of strings
                return '["dup_tag"]'
            elif field == "child":
                # different child record with different id
                @st.composite
                def child_dup(draw):
                    cid = draw(id_json)
                    if cid == old_val:
                        cid = str((int(cid) + 1) % 1000000)
                    camount = draw(amount_json)
                    cname = draw(name_json)
                    cstatus = draw(status_json)
                    ctags = draw(tags_json(allow_null=True))
                    cchild = "null"
                    obj = (
                        '{'
                        + '"id":' + cid + ','
                        + '"amount":' + camount + ','
                        + '"name":' + cname + ','
                        + '"status":' + cstatus + ','
                        + '"tags":' + ctags + ','
                        + '"child":' + cchild
                        + '}'
                    )
                    return obj
                return draw(child_dup())
            else:
                return old_val

        # Build list with duplicate key inserted at random position (last wins)
        new_val = different_value(dup_field, dict(fields)[dup_field])
        # Insert duplicate key at random position (not first to avoid confusion)
        pos = draw(st.integers(min_value=1, max_value=len(fields)))
        new_fields = []
        inserted = False
        for i, (k, v) in enumerate(fields):
            new_fields.append((k, v))
            if i == pos - 1 and not inserted:
                new_fields.append((dup_field, new_val))
                inserted = True
        if not inserted:
            new_fields.append((dup_field, new_val))
        fields = new_fields

    # Compose JSON object string from fields list (allow duplicate keys)
    # Join key:value pairs with commas
    # Keys are always strings, values are JSON literals or objects or arrays or null
    json_pairs = []
    for k, v in fields:
        json_pairs.append(json_string(k) + ":" + v)
    json_obj = "{" + ",".join(json_pairs) + "}"

    # Return as bytes
    return json_obj.encode("utf-8")