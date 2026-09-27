from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    valid_statuses = ["active", "inactive", "unknown"]
    # Probability weights for introducing one subtle divergence per document
    # We pick one or two fields to be "off" in a controlled way, else fully valid.

    # Helper: produce a valid "id" integer
    def id_strategy():
        # id must be integer only
        return st.integers(min_value=0, max_value=10**9)

    # Helper: produce a valid "amount" string (decimal number as string)
    def amount_strategy():
        # amount is string, e.g. "123.45"
        # Use decimal-like strings, no exponent, no leading zeros except "0"
        def decimal_str():
            # integer part: "0" or nonzero digit + digits
            int_part = st.one_of(
                st.just("0"),
                st.integers(min_value=1, max_value=9999999).map(str)
            )
            frac_part = st.one_of(
                st.just(""),
                st.integers(min_value=0, max_value=999999).map(lambda x: "." + str(x).rjust(1, "0"))
            )
            return st.tuples(int_part, frac_part).map(lambda t: t[0] + t[1])
        return decimal_str()

    # Helper: produce a valid "name" string or null
    def name_strategy():
        # name can be string or null, null is accepted by all
        # Use simple ascii strings or null
        return st.one_of(
            st.none(),
            st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))
        )

    # Helper: produce a valid "status" string from allowed set
    def status_strategy():
        return st.sampled_from(valid_statuses)

    # Helper: produce a valid "tags" array of strings
    def tags_strategy():
        # tags is array of strings, empty allowed
        # strings nonempty ascii
        return st.lists(
            st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
            max_size=5
        )

    # Forward declaration for child record (one level recursion)
    # We'll limit recursion depth to 1: child can be null or a record with child=null
    @st.composite
    def child_strategy(draw, depth=0):
        # If depth > 0, child must be null (no deeper recursion)
        if depth > 0:
            return "null"
        # Otherwise produce a record JSON string with child=null or child=record with child=null
        # We'll produce a valid record here (no divergence inside child)
        id_val = draw(id_strategy())
        amount_val = draw(amount_strategy())
        name_val = draw(name_strategy())
        status_val = draw(status_strategy())
        tags_val = draw(tags_strategy())
        # child: null or record with child=null
        child_null = st.just("null")
        # child record with child=null
        def record_json(idv, amtv, nmv, stv, tgs):
            # Compose JSON string for child record with child=null
            # name_val can be null or string
            name_json = "null" if nmv is None else '"' + nmv.replace('"', '\\"') + '"'
            tags_json = "[" + ",".join('"' + t.replace('"', '\\"') + '"' for t in tgs) + "]"
            return (
                '{'
                + f'"id":{idv},'
                + f'"amount":"{amtv}",'
                + f'"name":{name_json},'
                + f'"status":"{stv}",'
                + f'"tags":{tags_json},'
                + '"child":null'
                + '}'
            )
        child_record = st.tuples(id_strategy(), amount_strategy(), name_strategy(), status_strategy(), tags_strategy()).map(
            lambda tpl: record_json(*tpl)
        )
        child_val = draw(st.one_of(child_null, child_record))
        return child_val

    # Compose a valid record JSON string from components
    def record_json(idv, amtv, nmv, stv, tgs, chd):
        name_json = "null" if nmv is None else '"' + nmv.replace('"', '\\"') + '"'
        tags_json = "[" + ",".join('"' + t.replace('"', '\\"') + '"' for t in tgs) + "]"
        return (
            '{'
            + f'"id":{idv},'
            + f'"amount":"{amtv}",'
            + f'"name":{name_json},'
            + f'"status":"{stv}",'
            + f'"tags":{tags_json},'
            + f'"child":{chd}'
            + '}'
        )

    # Now, to produce documents that cause divergence, we apply one of these "mutations":
    # 1) Missing required field "tags" (accepted only by built_value)
    # 2) "tags": null (accepted only by built_value)
    # 3) "name" missing (accepted by all, no divergence)
    # 4) "status" invalid value (built_value throws DeserializationError, others ArgumentError)
    # 5) "status": null or empty string (same as above)
    # 6) "id" as float or string (rejected by all, no divergence)
    # 7) "amount" as non-string (rejected by all, no divergence)
    # 8) "child" missing or null or malformed (rejected by all if malformed)
    # 9) "tags" missing (only built_value accepts)
    # 10) "tags" with non-string element (rejected by all)
    # 11) "child" with missing required field (rejected by all)
    # 12) "status" with unrecognized string (built_value DeserializationError, others ArgumentError)
    # 13) "tags" empty array (accepted by all)
    # 14) "tags" null (only built_value accepts)
    # 15) "name" missing (accepted by all)
    # 16) "child" null (accepted by all)
    # 17) "child" present and valid (accepted by all)
    # 18) "tags" missing (only built_value accepts)
    # 19) "tags" present but empty (accepted by all)
    # 20) "tags" present with one non-string element (rejected by all)

    # We focus on producing documents with exactly one subtle divergence:
    # - missing "tags" field (accepted only by built_value)
    # - "tags": null (accepted only by built_value)
    # - invalid "status" value (built_value throws DeserializationError, others ArgumentError)
    # - "status": null or empty string (same as above)
    # - "tags" missing but present "child" valid
    # - "tags" null but present "child" valid
    # - "status" invalid but other fields valid
    # - "tags" missing and "child" null
    # - "tags" null and "child" null

    # We randomly pick one divergence type or produce fully valid document

    divergence_choices = st.sampled_from([
        "missing_tags",      # omit "tags" field (only built_value accepts)
        "tags_null",         # "tags": null (only built_value accepts)
        "status_invalid",    # "status" invalid string (built_value DeserializationError, others ArgumentError)
        "status_null",       # "status": null (built_value DeserializationError, others ArgumentError)
        "status_empty",      # "status": "" (built_value DeserializationError, others ArgumentError)
        "valid"              # fully valid document
    ])

    divergence = draw(divergence_choices)

    # Draw common fields
    id_val = draw(id_strategy())
    amount_val = draw(amount_strategy())
    name_val = draw(name_strategy())
    # For status, if divergence is invalid/null/empty, produce accordingly
    if divergence == "status_invalid":
        # invalid string not in valid_statuses
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_statuses and s != "" and s != "null"))
        status_val = invalid_status
    elif divergence == "status_null":
        status_val = None
    elif divergence == "status_empty":
        status_val = ""
    else:
        status_val = draw(status_strategy())

    # For tags:
    if divergence == "missing_tags":
        tags_val = None  # means omit field
    elif divergence == "tags_null":
        tags_val = None  # will encode as null explicitly
    else:
        tags_val = draw(tags_strategy())

    # For child: always produce valid child (null or valid record)
    child_val = draw(child_strategy(depth=0))

    # Compose JSON string manually
    # Compose fields except tags (conditionally)
    name_json = "null" if name_val is None else '"' + name_val.replace('"', '\\"') + '"'
    # Compose status JSON
    if status_val is None:
        status_json = "null"
    else:
        status_json = '"' + status_val.replace('"', '\\"') + '"'

    # Compose tags JSON or omit
    if divergence == "missing_tags":
        # omit tags field entirely
        tags_json = None
    elif divergence == "tags_null":
        tags_json = "null"
    else:
        tags_json = "[" + ",".join('"' + t.replace('"', '\\"') + '"' for t in tags_val) + "]"

    # Build JSON fields list
    fields = [
        f'"id":{id_val}',
        f'"amount":"{amount_val}"',
        f'"name":{name_json}',
        f'"status":{status_json}',
    ]
    if tags_json is not None:
        fields.append(f'"tags":{tags_json}')
    fields.append(f'"child":{child_val}')

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")