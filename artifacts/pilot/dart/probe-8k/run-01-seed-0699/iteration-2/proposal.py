from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Base primitives as JSON text
    def json_int(i: int) -> str:
        return str(i)

    def json_str(s: str) -> str:
        # Escape quotes and backslashes minimally for JSON string
        # Hypothesis strings are unicode; escape backslash and quote only
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Generate "id": integer
    id_val = draw(st.integers(min_value=0, max_value=10**6))

    # Generate "amount": string (non-empty to avoid trivial)
    # Include some edge cases: empty string, numeric strings, whitespace
    amount_val = draw(st.one_of(
        st.text(min_size=0, max_size=10),
        st.just("0"),
        st.just(""),
        st.just("  "),
        st.just("123.45"),
        st.just("-0.01"),
    ))
    amount_json = json_str(amount_val)

    # Generate "name": string or null
    # Include empty string, unicode, and null
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20),
    ))
    if name_val is None:
        name_json = "null"
    else:
        name_json = json_str(name_val)

    # Generate "status": one of allowed enum strings
    # Also sometimes produce a wrong enum to test rejection (but that scores zero if all reject)
    # So mostly produce valid enum, but sometimes produce a close invalid string to try divergence
    # But per instructions, divergence is more likely if only one thing off, so mostly valid
    status_val = draw(st.one_of(
        st.sampled_from(STATUS_VALUES),
        # invalid enum strings (rare)
        st.just('"Active"'),
        st.just('"inactiv"'),
        st.just('"unknown "'),
    ))
    # status_val is already JSON string including quotes

    # Generate "tags": array of strings (possibly empty)
    # Strings can be empty or non-empty, but no nulls (all reject if null in tags)
    # To try divergence, sometimes produce empty array, sometimes array with empty string
    # Also try array with one string that is empty or whitespace
    # Also try array with one string that is a number as string (allowed)
    tags_len = draw(st.integers(min_value=0, max_value=3))
    tags_vals = []
    for _ in range(tags_len):
        tag = draw(st.text(min_size=0, max_size=10))
        # Escape tag string
        tags_vals.append(json_str(tag))
    tags_json = "[" + ",".join(tags_vals) + "]"

    # Generate "child": null or nested record (one level recursion max)
    # To keep bounded recursion, child can be null or a record with no child (child=null)
    # To maximize chance of divergence, sometimes omit child (not allowed, all reject)
    # But all reject if missing child, so always present (null or record)
    # Sometimes produce child with one field off type to try divergence
    # But broad malformation rejected by all, so mostly valid child or null

    # Compose child record JSON text
    def gen_child():
        # id: int
        cid = draw(st.integers(min_value=0, max_value=10**6))
        # amount: string
        camount = draw(st.text(min_size=0, max_size=10))
        camount_json = json_str(camount)
        # name: string or null
        cname_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        cname_json = "null" if cname_val is None else json_str(cname_val)
        # status: valid enum only here to avoid all reject
        cstatus_json = draw(st.sampled_from(STATUS_VALUES))
        # tags: array of strings (empty or small)
        clen = draw(st.integers(min_value=0, max_value=2))
        ctags_vals = []
        for _ in range(clen):
            t = draw(st.text(min_size=0, max_size=10))
            ctags_vals.append(json_str(t))
        ctags_json = "[" + ",".join(ctags_vals) + "]"
        # child: null (no deeper recursion)
        cchild_json = "null"

        # Compose child JSON object string
        # Insert fields in random order to test key order (last key wins)
        keys = ["id", "amount", "name", "status", "tags", "child"]
        draw_order = draw(st.permutations(keys))
        parts = []
        for k in draw_order:
            if k == "id":
                parts.append(f'"id":{cid}')
            elif k == "amount":
                parts.append(f'"amount":{camount_json}')
            elif k == "name":
                parts.append(f'"name":{cname_json}')
            elif k == "status":
                parts.append(f'"status":{cstatus_json}')
            elif k == "tags":
                parts.append(f'"tags":{ctags_json}')
            elif k == "child":
                parts.append(f'"child":{cchild_json}')
        return "{" + ",".join(parts) + "}"

    # Decide child: null or record
    child_choice = draw(st.one_of(
        st.just("null"),
        st.just(gen_child()),
    ))
    child_json = child_choice

    # Compose top-level JSON object
    # Insert fields in random order to test duplicate keys and order
    keys = ["id", "amount", "name", "status", "tags", "child"]
    # To try to trigger duplicate keys divergence, sometimes duplicate one key with different value
    # But all implementations take last key, so no divergence there, but allowed by instructions
    # So sometimes duplicate "name" or "id" or "status" with different values
    # To maximize chance of divergence, sometimes duplicate with slightly different type or value

    # Generate base field values for duplicates
    # For id duplicate, produce a different integer
    id_dup_val = id_val + 1 if id_val < 10**6 else id_val - 1
    # For name duplicate, produce different string or null
    name_dup_val = None if name_val is not None else "dup"
    name_dup_json = "null" if name_dup_val is None else json_str(name_dup_val)
    # For status duplicate, produce different valid enum
    status_dup_json = draw(st.sampled_from([v for v in STATUS_VALUES if v != status_val]))

    # Decide if and which key to duplicate (or none)
    dup_key = draw(st.one_of(st.none(), st.just("id"), st.just("name"), st.just("status")))

    # Compose fields with possible duplication
    # Randomize order with duplicates inserted at random positions
    base_fields = []
    for k in keys:
        if k == "id":
            base_fields.append(f'"id":{id_val}')
        elif k == "amount":
            base_fields.append(f'"amount":{amount_json}')
        elif k == "name":
            base_fields.append(f'"name":{name_json}')
        elif k == "status":
            base_fields.append(f'"status":{status_val}')
        elif k == "tags":
            base_fields.append(f'"tags":{tags_json}')
        elif k == "child":
            base_fields.append(f'"child":{child_json}')

    # Insert duplicate key if any
    if dup_key is not None:
        # Compose duplicate field string
        if dup_key == "id":
            dup_field = f'"id":{id_dup_val}'
        elif dup_key == "name":
            dup_field = f'"name":{name_dup_json}'
        elif dup_key == "status":
            dup_field = f'"status":{status_dup_json}'
        else:
            dup_field = None  # Should not happen

        # Insert duplicate field at random position (not necessarily last)
        pos = draw(st.integers(min_value=0, max_value=len(base_fields)))
        base_fields.insert(pos, dup_field)

    # Shuffle fields order to vary key order (except duplicates inserted already)
    # But keep duplicates order fixed relative to insertion
    # So shuffle all except duplicates? To keep simple, do not shuffle after insertion

    json_text = "{" + ",".join(base_fields) + "}"

    # Return as bytes
    return json_text.encode("utf-8")