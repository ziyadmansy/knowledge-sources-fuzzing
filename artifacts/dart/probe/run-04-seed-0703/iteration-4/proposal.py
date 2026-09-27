from hypothesis import strategies as st

# Constants for allowed values
STATUS_VALUES = ["active", "inactive", "unknown"]

# Helper to produce a JSON string literal from a Python string (with minimal escaping)
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote and control chars minimally
    # We do not import json, so do a minimal safe escape for test strings
    # Replace \ with \\, " with \", and control chars with \u00XX
    def esc_char(c):
        o = ord(c)
        if c == '\\':
            return '\\\\'
        elif c == '"':
            return '\\"'
        elif 0 <= o <= 0x1F:
            return '\\u%04x' % o
        else:
            return c
    return '"' + ''.join(esc_char(c) for c in s) + '"'

@st.composite
def generated_json(draw) -> bytes:
    # We produce a JSON object text as bytes.
    # Strategy: produce a dict with all six fields always present,
    # mostly well-formed but with exactly zero or one small deviation from the schema,
    # chosen from a set of "almost valid" perturbations that might cause divergence.

    # Base valid fields generators:
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    amount_val = draw(st.text(min_size=1, max_size=10))  # non-empty string
    # name: string or null
    name_val = draw(st.one_of(st.none(), st.text(max_size=10)))
    status_val = draw(st.sampled_from(STATUS_VALUES))
    tags_val = draw(st.lists(st.text(min_size=1, max_size=10), max_size=5))
    # child: either null or a nested record with same schema but no further recursion
    # To avoid deep recursion, child.child must be null always.
    def child_record():
        cid = draw(st.integers(min_value=0, max_value=2**31-1))
        camount = draw(st.text(min_size=1, max_size=10))
        cname = draw(st.one_of(st.none(), st.text(max_size=10)))
        cstatus = draw(st.sampled_from(STATUS_VALUES))
        ctags = draw(st.lists(st.text(min_size=1, max_size=10), max_size=3))
        # child.child is always null here (one level recursion)
        return {
            "id": cid,
            "amount": camount,
            "name": cname,
            "status": cstatus,
            "tags": ctags,
            "child": None,
        }
    child_val = draw(st.one_of(st.none(), st.just(child_record())))

    # Compose a base valid record dict
    base = {
        "id": id_val,
        "amount": amount_val,
        "name": name_val,
        "status": status_val,
        "tags": tags_val,
        "child": child_val,
    }

    # Define a set of perturbations that change exactly one field slightly:
    # Each perturbation is a function that takes the base dict and returns a new dict.
    # Perturbations chosen to try to cause divergence:
    perturbations = []

    # 1) id as string (all reject, no divergence)
    # skip - no divergence

    # 2) amount as integer (all reject, no divergence)
    # skip

    # 3) name as integer (all reject, no divergence)
    # skip

    # 4) status as invalid string (all reject, no divergence)
    # skip

    # 5) tags as array with one non-string element (all reject, no divergence)
    # skip

    # 6) child missing required fields (all reject, no divergence)
    # skip

    # 7) child present but null (valid)
    # 8) child present with valid nested record (valid)
    # no perturbation needed

    # Known from experience: all four implementations behave identically on these,
    # so we try subtle perturbations that might cause divergence:

    # Perturbation A: omit one required field at top level (e.g. remove "amount")
    # All reject, no divergence, skip

    # Perturbation B: present "name" as empty string vs null (both accepted, no divergence)
    # no divergence

    # Perturbation C: "tags" array empty vs non-empty (both accepted)
    # no divergence

    # Perturbation D: "child" present but with one field type subtly wrong (e.g. child.id as string)
    # All reject, no divergence

    # Perturbation E: "child" present but with extra fields (all accept, no divergence)

    # Perturbation F: "status" as correct string but with trailing space (e.g. "active ")
    # Possibly some implementations trim or reject differently

    def perturb_status_trailing_space(d):
        d2 = d.copy()
        d2["status"] = d2["status"] + " "
        return d2

    perturbations.append(perturb_status_trailing_space)

    # Perturbation G: "tags" array contains empty string (allowed?), might cause subtle difference
    def perturb_tags_empty_string(d):
        d2 = d.copy()
        if len(d2["tags"]) == 0:
            d2["tags"] = [""]
        else:
            # replace first tag with empty string
            tags = list(d2["tags"])
            tags[0] = ""
            d2["tags"] = tags
        return d2
    perturbations.append(perturb_tags_empty_string)

    # Perturbation H: "name" as empty string vs null (both accepted, no divergence)
    # skip

    # Perturbation I: "child" present with "name": null replaced by "name": "" (empty string)
    def perturb_child_name_empty_string(d):
        d2 = d.copy()
        if d2["child"] is not None:
            child = dict(d2["child"])
            if child["name"] is None:
                child["name"] = ""
                d2["child"] = child
        return d2
    perturbations.append(perturb_child_name_empty_string)

    # Perturbation J: "child" present with "tags" empty replaced by [""] (empty string tag)
    def perturb_child_tags_empty_string(d):
        d2 = d.copy()
        if d2["child"] is not None:
            child = dict(d2["child"])
            if len(child["tags"]) == 0:
                child["tags"] = [""]
                d2["child"] = child
        return d2
    perturbations.append(perturb_child_tags_empty_string)

    # Perturbation K: "child" present with "status" with trailing space
    def perturb_child_status_trailing_space(d):
        d2 = d.copy()
        if d2["child"] is not None:
            child = dict(d2["child"])
            child["status"] = child["status"] + " "
            d2["child"] = child
        return d2
    perturbations.append(perturb_child_status_trailing_space)

    # Perturbation L: "tags" array as ["valid", 123] (mixed types) - all reject, no divergence
    # skip

    # Perturbation M: "child" present but null replaced by {} (empty object) - all reject, no divergence
    # skip

    # Perturbation N: "child" present with one field missing (e.g. no "id") - all reject, no divergence
    # skip

    # Perturbation O: "amount" as string but empty "" (allowed?), might cause subtle difference
    def perturb_amount_empty_string(d):
        d2 = d.copy()
        d2["amount"] = ""
        return d2
    perturbations.append(perturb_amount_empty_string)

    # Perturbation P: "id" as zero (valid), no perturbation needed

    # Perturbation Q: "id" as negative integer (valid?), might cause subtle difference
    # The schema says integer, no range specified, so negative might be accepted or rejected differently
    def perturb_id_negative(d):
        d2 = d.copy()
        d2["id"] = -1
        return d2
    perturbations.append(perturb_id_negative)

    # Perturbation R: "name" as very long string (max 10 chars allowed?), no divergence expected
    # skip

    # Perturbation S: "tags" array with duplicate strings (allowed?), no divergence expected
    # skip

    # Perturbation T: "child" present with "child" field non-null (two-level recursion)
    # All accept, no divergence

    # We pick zero or one perturbation at random to apply, to keep documents mostly valid or with one subtle deviation.

    apply_perturb = draw(st.one_of(st.just(None), st.sampled_from(perturbations)))

    if apply_perturb is not None:
        base = apply_perturb(base)

    # Now serialize base dict to JSON text manually:

    def serialize_string(s):
        if s is None:
            return "null"
        else:
            return json_string_literal(s)

    def serialize_array(arr):
        # arr is list of strings
        return "[" + ",".join(serialize_string(x) for x in arr) + "]"

    def serialize_record(rec):
        # rec is dict with six fields
        parts = []
        parts.append('"id":' + str(rec["id"]))
        parts.append('"amount":' + serialize_string(rec["amount"]))
        parts.append('"name":' + serialize_string(rec["name"]))
        parts.append('"status":' + serialize_string(rec["status"]))
        parts.append('"tags":' + serialize_array(rec["tags"]))
        if rec["child"] is None:
            parts.append('"child":null')
        else:
            parts.append('"child":' + serialize_record(rec["child"]))
        return "{" + ",".join(parts) + "}"

    json_text = serialize_record(base)
    return json_text.encode("utf-8")