from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum status
    valid_statuses = ["active", "inactive", "unknown"]

    # Base valid values for fields
    base_id = st.integers(min_value=0, max_value=2**31-1)
    base_amount = st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))
    base_name = st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)))
    base_status = st.sampled_from(valid_statuses)
    base_tag = st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))
    base_tags = st.lists(base_tag, min_size=0, max_size=3)

    # Helper to produce a valid child record (one level recursion only)
    # We'll produce a valid child or null, then apply small mutations to cause divergence
    @st.composite
    def child_record(draw):
        # Start with a valid child record (no further recursion)
        child_id = draw(base_id)
        child_amount = draw(base_amount)
        child_name = draw(base_name)
        child_status = draw(base_status)
        child_tags = draw(base_tags)
        # child.child must be null (one level recursion only)
        child_child = None

        # Compose JSON text for child record
        # We'll build it as a dict string with keys in fixed order
        # We will mutate one or two fields to cause divergence:
        # - null in non-nullable fields (id, amount, status)
        # - invalid enum values (wrong case, unknown)
        # - missing fields (except built_value accepts missing tags and child)
        # - wrong types (number instead of string, empty object instead of child)
        # - null tags (accepted only by built_value)
        # - tags with non-string element (all reject)
        # We'll pick one mutation per child record to keep divergence focused.

        # Choose mutation type for child (or no mutation)
        mutation = draw(st.sampled_from([
            "none",
            "null_id",
            "null_amount",
            "null_status",
            "null_tags",
            "missing_tags",
            "missing_child",
            "invalid_status_unknown",
            "invalid_status_case",
            "wrong_type_amount_number",
            "wrong_type_child_empty_object",
            "tags_nonstring_element",
        ]))

        # Apply mutation
        fields = {
            "id": child_id,
            "amount": child_amount,
            "name": child_name,
            "status": child_status,
            "tags": child_tags,
            "child": child_child,
        }

        # Mutate fields according to mutation
        if mutation == "null_id":
            fields["id"] = None
        elif mutation == "null_amount":
            fields["amount"] = None
        elif mutation == "null_status":
            fields["status"] = None
        elif mutation == "null_tags":
            fields["tags"] = None
        elif mutation == "missing_tags":
            del fields["tags"]
        elif mutation == "missing_child":
            del fields["child"]
        elif mutation == "invalid_status_unknown":
            fields["status"] = "invalid"
        elif mutation == "invalid_status_case":
            # Pick a case variant of a valid status
            variant = draw(st.sampled_from(["ACTIVE", "Inactive", "UnKnOwN"]))
            fields["status"] = variant
        elif mutation == "wrong_type_amount_number":
            # amount as number instead of string
            fields["amount"] = draw(st.integers(min_value=0, max_value=1000))
        elif mutation == "wrong_type_child_empty_object":
            # child as empty object instead of null or record
            fields["child"] = {}
        elif mutation == "tags_nonstring_element":
            # tags with one non-string element (e.g. number)
            if "tags" in fields:
                tags_list = list(fields["tags"])
                if len(tags_list) == 0:
                    tags_list.append(draw(st.integers(min_value=0, max_value=10)))
                else:
                    # Replace one element with number
                    idx = draw(st.integers(min_value=0, max_value=len(tags_list)-1))
                    tags_list[idx] = draw(st.integers(min_value=0, max_value=10))
                fields["tags"] = tags_list

        # Compose JSON text for child record
        # We must produce syntactically valid JSON with correct quoting and escaping
        # We'll build key:value pairs in fixed order if present
        parts = []
        def json_str(s):
            # Escape backslash and double quote and control chars minimally
            # We only allow ASCII printable in strings, so minimal escaping needed
            s = s.replace("\\", "\\\\").replace("\"", "\\\"")
            return f"\"{s}\""

        def json_val(v):
            if v is None:
                return "null"
            elif isinstance(v, str):
                return json_str(v)
            elif isinstance(v, int):
                return str(v)
            elif isinstance(v, list):
                # list of strings or mixed (for tags_nonstring_element)
                elems = []
                for e in v:
                    if isinstance(e, str):
                        elems.append(json_str(e))
                    elif isinstance(e, int):
                        elems.append(str(e))
                    else:
                        # fallback to null for safety (should not happen)
                        elems.append("null")
                return "[" + ",".join(elems) + "]"
            elif isinstance(v, dict):
                # empty object only expected here
                if len(v) == 0:
                    return "{}"
                else:
                    # Should not happen here
                    return "{}"
            else:
                # fallback
                return "null"

        # Order keys as per schema
        for key in ["id", "amount", "name", "status", "tags", "child"]:
            if key in fields:
                parts.append(json_str(key) + ":" + json_val(fields[key]))

        child_json = "{" + ",".join(parts) + "}"
        return child_json

    # Now produce the top-level record similarly, with one mutation to cause divergence
    # Start with valid base fields
    id_val = draw(base_id)
    amount_val = draw(base_amount)
    name_val = draw(base_name)
    status_val = draw(base_status)
    tags_val = draw(base_tags)

    # For child, either null or a child record with mutation
    child_choice = draw(st.booleans())
    if child_choice:
        child_val = draw(child_record())
    else:
        child_val = "null"

    # Mutation for top-level record (one mutation per record)
    mutation = draw(st.sampled_from([
        "none",
        "null_id",
        "null_amount",
        "null_status",
        "null_tags",
        "missing_tags",
        "missing_child",
        "invalid_status_unknown",
        "invalid_status_case",
        "wrong_type_amount_number",
        "wrong_type_child_empty_object",
        "tags_nonstring_element",
    ]))

    fields = {
        "id": id_val,
        "amount": amount_val,
        "name": name_val,
        "status": status_val,
        "tags": tags_val,
        "child": child_val,
    }

    if mutation == "null_id":
        fields["id"] = None
    elif mutation == "null_amount":
        fields["amount"] = None
    elif mutation == "null_status":
        fields["status"] = None
    elif mutation == "null_tags":
        fields["tags"] = None
    elif mutation == "missing_tags":
        del fields["tags"]
    elif mutation == "missing_child":
        del fields["child"]
    elif mutation == "invalid_status_unknown":
        fields["status"] = "invalid"
    elif mutation == "invalid_status_case":
        variant = draw(st.sampled_from(["ACTIVE", "Inactive", "UnKnOwN"]))
        fields["status"] = variant
    elif mutation == "wrong_type_amount_number":
        fields["amount"] = draw(st.integers(min_value=0, max_value=1000))
    elif mutation == "wrong_type_child_empty_object":
        fields["child"] = {}
    elif mutation == "tags_nonstring_element":
        if "tags" in fields:
            tags_list = list(fields["tags"])
            if len(tags_list) == 0:
                tags_list.append(draw(st.integers(min_value=0, max_value=10)))
            else:
                idx = draw(st.integers(min_value=0, max_value=len(tags_list)-1))
                tags_list[idx] = draw(st.integers(min_value=0, max_value=10))
            fields["tags"] = tags_list

    # Compose JSON text for top-level record
    parts = []
    def json_str(s):
        s = s.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{s}\""

    def json_val(v):
        if v is None:
            return "null"
        elif isinstance(v, str):
            return json_str(v)
        elif isinstance(v, int):
            return str(v)
        elif isinstance(v, list):
            elems = []
            for e in v:
                if isinstance(e, str):
                    elems.append(json_str(e))
                elif isinstance(e, int):
                    elems.append(str(e))
                else:
                    elems.append("null")
            return "[" + ",".join(elems) + "]"
        elif isinstance(v, dict):
            if len(v) == 0:
                return "{}"
            else:
                return "{}"
        else:
            # child_val is string JSON for child record or "null" or dict (empty object)
            if isinstance(v, str):
                return v
            else:
                return "null"

    # Output keys in fixed order
    for key in ["id", "amount", "name", "status", "tags", "child"]:
        if key in fields:
            parts.append(json_str(key) + ":" + json_val(fields[key]))

    json_text = "{" + ",".join(parts) + "}"
    return json_text.encode("utf-8")