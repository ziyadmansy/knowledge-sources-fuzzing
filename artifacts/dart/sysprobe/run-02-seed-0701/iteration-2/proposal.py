from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper: JSON string with proper escaping for "amount", "name", "tags" elements, "status" enum, and keys.
    # We build JSON text manually with string concatenation.

    # id: integer, required, non-null
    # amount: string, required, non-null
    # name: string or null, required (always present)
    # status: enum string ("active", "inactive", "unknown"), required (always present)
    # tags: array of strings, required (always present)
    # child: null or Record (one level recursion max)

    # Strategy to produce a valid "status" or an invalid variant to provoke divergence.
    # We bias towards valid but sometimes produce invalid or case variants.
    valid_statuses = st.sampled_from(["active", "inactive", "unknown"])
    # Introduce a small chance of invalid or case-variant status to provoke divergence.
    status_strat = st.one_of(
        valid_statuses,
        st.sampled_from(["ACTIVE", "Inactive", "invalid_status", "unknown "]),  # invalid or case variants
    )

    # "amount" string: mostly normal strings, but sometimes empty or numeric-looking strings
    amount_strat = st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: '"' not in s and '\\' not in s),
        st.just(""),  # empty string amount (valid string but edge)
        st.just("12345"),  # numeric-looking string
    )

    # "name": string or null
    name_strat = st.one_of(
        st.none(),
        st.text(min_size=0, max_size=15).filter(lambda s: '"' not in s and '\\' not in s),
    )

    # "tags": array of strings, sometimes empty, sometimes with empty string elements
    tag_elem = st.text(min_size=0, max_size=8).filter(lambda s: '"' not in s and '\\' not in s)
    tags_strat = st.lists(tag_elem, min_size=0, max_size=5)

    # "id": integer, but sometimes produce out-of-bound or negative to provoke divergence
    id_strat = st.one_of(
        st.integers(min_value=0, max_value=2**31-1),
        st.integers(min_value=-100, max_value=-1),  # negative id (likely rejected)
        st.integers(min_value=2**31, max_value=2**32),  # large id (possibly accepted or rejected)
    )

    # "child": null or a nested record (one level only)
    # To avoid broad malformation, child is either null or a well-formed record with slight variations.
    # We will produce child with a simpler record, no further recursion.
    # We allow child to be null or a record with one field off (e.g. missing "status" or null "tags") to provoke divergence.

    # Child record fields:
    # id, amount, name, status, tags, child=null (no recursion deeper)

    def child_record():
        # We produce a child record with one subtle variation to provoke divergence:
        # - sometimes missing "status" (accepted by built_value only)
        # - sometimes null "tags" (accepted by built_value only)
        # - sometimes all fields present and valid
        # - sometimes "status" invalid enum string
        child_id = draw(id_strat)
        child_amount = draw(amount_strat)
        child_name = draw(name_strat)
        child_status = draw(st.one_of(
            valid_statuses,
            st.just("invalid_status"),
            st.none(),  # null status (should be rejected by all except built_value?)
        ))
        child_tags = draw(st.one_of(
            tags_strat,
            st.none(),  # null tags accepted only by built_value
        ))
        # child.child is always null (no deeper recursion)
        # Compose JSON text for child record with possible missing fields or nulls

        # We randomly omit "status" or "tags" to provoke divergence
        omit_status = draw(st.booleans())
        omit_tags = draw(st.booleans())

        parts = []
        parts.append('"id":'+str(child_id))
        parts.append('"amount":"'+child_amount+'"')
        # name can be null or string
        if child_name is None:
            parts.append('"name":null')
        else:
            parts.append('"name":"'+child_name+'"')
        if not omit_status:
            if child_status is None:
                parts.append('"status":null')
            else:
                parts.append('"status":"'+child_status+'"')
        if not omit_tags:
            if child_tags is None:
                parts.append('"tags":null')
            else:
                # tags array
                tags_json = '[' + ','.join('"'+t+'"' for t in child_tags) + ']'
                parts.append('"tags":'+tags_json)
        parts.append('"child":null')

        return '{'+','.join(parts)+'}'

    # Top-level record fields:
    # We produce one or two subtle deviations from a valid record:
    # - sometimes omit a required field (except "tags" which built_value accepts missing)
    # - sometimes null a non-nullable field (except "name" allowed null)
    # - sometimes invalid enum in "status"
    # - sometimes null "tags" (accepted only by built_value)
    # - sometimes child with subtle deviations

    # We pick one or two fields to "break" to provoke divergence
    # But keep the rest valid to avoid universal rejection

    # Fields to consider for breaking: "id", "amount", "status", "tags", "child"
    # "name" can be null always, so less interesting to break

    # Choose 0,1 or 2 fields to break
    fields = ["id", "amount", "status", "tags", "child"]
    num_breaks = draw(st.integers(min_value=0, max_value=2))
    break_fields = draw(st.lists(st.sampled_from(fields), min_size=num_breaks, max_size=num_breaks, unique=True))

    # Compose fields:

    # id
    if "id" in break_fields:
        # break id by null or missing
        id_break_type = draw(st.sampled_from(["null", "missing", "large_negative"]))
        if id_break_type == "null":
            id_val = None
            id_present = True
        elif id_break_type == "missing":
            id_present = False
            id_val = None
        else:
            id_present = True
            id_val = draw(st.integers(min_value=-1000, max_value=-1))
    else:
        id_present = True
        id_val = draw(id_strat)

    # amount
    if "amount" in break_fields:
        amount_break_type = draw(st.sampled_from(["null", "missing", "number_instead_string"]))
        if amount_break_type == "null":
            amount_val = None
            amount_present = True
        elif amount_break_type == "missing":
            amount_present = False
            amount_val = None
        else:
            amount_present = True
            # number instead of string (probe 12 known to cause rejection by all)
            # but we want divergence, so maybe a stringified number is better
            # but let's try number here to see if built_value accepts it differently
            amount_val = draw(st.integers(min_value=0, max_value=10000))
    else:
        amount_present = True
        amount_val = draw(amount_strat)

    # name (always present, can be null)
    name_val = draw(name_strat)
    name_present = True

    # status
    if "status" in break_fields:
        status_break_type = draw(st.sampled_from(["null", "missing", "invalid_enum", "case_variant"]))
        if status_break_type == "null":
            status_val = None
            status_present = True
        elif status_break_type == "missing":
            status_present = False
            status_val = None
        elif status_break_type == "invalid_enum":
            status_val = "invalid_status"
            status_present = True
        else:
            # case variant
            status_val = draw(st.sampled_from(["ACTIVE", "Inactive", "UNKNOWN"]))
            status_present = True
    else:
        status_val = draw(valid_statuses)
        status_present = True

    # tags
    if "tags" in break_fields:
        tags_break_type = draw(st.sampled_from(["null", "missing", "non_string_element"]))
        if tags_break_type == "null":
            tags_val = None
            tags_present = True
        elif tags_break_type == "missing":
            tags_present = False
            tags_val = None
        else:
            # non-string element in tags array (probe 19 causes all reject)
            # To provoke divergence, we insert a number as one element
            tags_val = draw(tags_strat)
            if len(tags_val) == 0:
                tags_val = ["valid"]
            # replace one element with a number (as JSON text)
            idx = draw(st.integers(min_value=0, max_value=len(tags_val)-1))
            # We'll mark this specially in JSON construction
            tags_present = True
            tags_val = list(tags_val)
            tags_val[idx] = None  # None will be rendered as number 42 below
    else:
        tags_val = draw(tags_strat)
        tags_present = True

    # child
    if "child" in break_fields:
        # break child by invalid type or malformed record or null
        child_break_type = draw(st.sampled_from(["invalid_type", "malformed_record", "null"]))
        if child_break_type == "invalid_type":
            # child as a number (invalid type)
            child_val = 42
        elif child_break_type == "malformed_record":
            # child as object missing required fields or with wrong types
            # We'll produce a child record missing "id" or with null "amount"
            malformed_choice = draw(st.sampled_from(["missing_id", "null_amount"]))
            if malformed_choice == "missing_id":
                # child missing "id"
                child_val = '{' + '"amount":"childamt","name":null,"status":"active","tags":["c"],"child":null' + '}'
            else:
                # child with null amount
                child_val = '{' + '"id":1,"amount":null,"name":"c","status":"active","tags":["c"],"child":null' + '}'
        else:
            child_val = None
    else:
        # child normal or with subtle deviation
        child_val = child_record()

    # Compose JSON text parts
    parts = []

    if id_present:
        if id_val is None:
            parts.append('"id":null')
        else:
            parts.append('"id":'+str(id_val))
    # else omit "id"

    if amount_present:
        if amount_val is None:
            parts.append('"amount":null')
        elif isinstance(amount_val, int):
            # number instead of string
            parts.append('"amount":'+str(amount_val))
        else:
            parts.append('"amount":"'+amount_val+'"')
    # else omit "amount"

    # name always present
    if name_val is None:
        parts.append('"name":null')
    else:
        parts.append('"name":"'+name_val+'"')

    if status_present:
        if status_val is None:
            parts.append('"status":null')
        else:
            parts.append('"status":"'+status_val+'"')
    # else omit "status"

    if tags_present:
        if tags_val is None:
            parts.append('"tags":null')
        elif isinstance(tags_val, list):
            # Check if any element is None (means non-string element)
            if any(t is None for t in tags_val):
                # Render non-string element as number 42
                tags_json = '[' + ','.join(
                    ('42' if t is None else '"'+t+'"') for t in tags_val
                ) + ']'
            else:
                tags_json = '[' + ','.join('"'+t+'"' for t in tags_val) + ']'
            parts.append('"tags":'+tags_json)
        else:
            # Should not happen
            parts.append('"tags":null')
    # else omit "tags"

    # child
    if child_val is None:
        parts.append('"child":null')
    elif isinstance(child_val, int):
        # invalid type child as number
        parts.append('"child":'+str(child_val))
    elif isinstance(child_val, str):
        # malformed record as string (already JSON text)
        parts.append('"child":'+child_val)
    else:
        # normal child record JSON text
        parts.append('"child":'+child_val)

    json_text = '{' + ','.join(parts) + '}'
    return json_text.encode('utf-8')