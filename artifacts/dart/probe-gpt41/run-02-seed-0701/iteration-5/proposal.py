from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema:
    {
      "id": <integer>,
      "amount": <string>,
      "name": <string or null, or missing>,
      "status": <"active"|"inactive"|"unknown">,
      "tags": <array of strings or null (only built_value accepts null)>,
      "child": <Record or null or missing>
    }
    Intentionally produce near-valid documents with one or two subtle divergences:
    - sometimes omit "name" (allowed),
    - sometimes omit "child" (allowed),
    - sometimes set "tags" to null (only built_value accepts),
    - sometimes set "tags" to empty array or array of strings,
    - sometimes set "status" to invalid enum or null (to trigger different error types),
    - sometimes set "id" or "amount" to wrong types (string for id, int for amount),
    - sometimes set "child" to null or a nested record,
    - sometimes omit required fields (to cause rejection),
    - never produce broadly malformed JSON (always valid JSON syntax).
    """

    # Helper: JSON string escape for simple strings (no control chars, no quotes inside)
    def json_str(s: str) -> str:
        # Hypothesis strings are safe ASCII by default, but we restrict to safe chars
        # We generate strings without quotes or backslashes to avoid escaping complexity
        # We'll generate strings from a safe alphabet below
        return '"' + s + '"'

    # Safe string strategy for JSON string values (no quotes, no backslash)
    safe_chars = st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd', 'Zs'),
        blacklist_characters='"\\',
        min_codepoint=32,
        max_codepoint=126,
    )
    safe_str = st.text(safe_chars, min_size=0, max_size=10)

    # id: integer, but sometimes string (to cause type mismatch)
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),  # valid int as string (will cause type error)
        st.integers(min_value=0, max_value=2**31-1),          # valid int
    )

    # amount: string normally, but sometimes int (to cause type mismatch)
    amount_strategy = st.one_of(
        safe_str,  # valid string
        st.integers(min_value=0, max_value=10000),  # invalid int for amount
    )

    # name: string or null or missing
    name_strategy = st.one_of(
        safe_str,
        st.just("null"),
        st.just(None),
        st.just("missing"),  # special marker for missing field
    )

    # status: valid enum or invalid enum or null
    valid_status = st.sampled_from(["active", "inactive", "unknown"])
    invalid_status = st.sampled_from(["pending", "ACTIVE", "inactivee", ""])
    status_strategy = st.one_of(
        valid_status,
        invalid_status,
        st.just("null"),
    )

    # tags: array of strings, or null (only built_value accepts null)
    # Also sometimes wrong type (int array or string)
    tags_string_array = st.lists(safe_str, min_size=0, max_size=3)
    tags_strategy = st.one_of(
        tags_string_array,
        st.just(None),
        st.lists(st.integers(min_value=0, max_value=10), min_size=0, max_size=3),
        safe_str,
    )

    # child: null, missing, or nested record (one level recursion)
    # To avoid deep recursion, child record is generated with recursion_depth=0
    # We'll generate child record with recursion_depth=0 (no child inside)
    # Also sometimes child is wrong type (string)
    # Use a helper to generate child record with recursion_depth=0

    def record(recursion_depth: int):
        # recursion_depth 0 means child must be null or missing only
        # recursion_depth 1 means child can be nested record with recursion_depth=0
        def gen_record():
            # id
            id_val = draw(id_strategy)
            # amount
            amount_val = draw(amount_strategy)
            # name
            name_val = draw(name_strategy)
            # status
            status_val = draw(status_strategy)
            # tags
            tags_val = draw(tags_strategy)
            # child
            if recursion_depth > 0:
                child_val = draw(st.one_of(
                    st.just(None),
                    record(recursion_depth - 1),
                    safe_str,  # invalid type for child
                    st.just("missing"),
                ))
            else:
                child_val = draw(st.one_of(
                    st.just(None),
                    safe_str,
                    st.just("missing"),
                ))

            # Compose JSON object string with controlled field presence and order
            # Fields: id (required), amount (required), name (optional), status (required), tags (required), child (optional)
            # Omit fields marked as "missing"
            fields = []

            # id
            if id_val == "missing":
                pass
            else:
                if isinstance(id_val, int):
                    fields.append('"id":' + str(id_val))
                else:
                    # id_val is string (wrong type)
                    fields.append('"id":' + json_str(id_val))

            # amount
            if amount_val == "missing":
                pass
            else:
                if isinstance(amount_val, int):
                    fields.append('"amount":' + str(amount_val))
                else:
                    fields.append('"amount":' + json_str(amount_val))

            # name
            if name_val == "missing":
                pass
            else:
                if name_val is None or name_val == "null":
                    fields.append('"name":null')
                else:
                    fields.append('"name":' + json_str(name_val))

            # status
            if status_val == "missing":
                pass
            else:
                if status_val == "null":
                    fields.append('"status":null')
                else:
                    fields.append('"status":' + json_str(status_val))

            # tags
            if tags_val == "missing":
                pass
            else:
                if tags_val is None:
                    fields.append('"tags":null')
                elif isinstance(tags_val, list):
                    # list of strings or ints
                    elems = []
                    for e in tags_val:
                        if isinstance(e, int):
                            elems.append(str(e))
                        else:
                            elems.append(json_str(e))
                    fields.append('"tags":[' + ",".join(elems) + ']')
                else:
                    # string
                    fields.append('"tags":' + json_str(tags_val))

            # child
            if child_val == "missing":
                pass
            else:
                if child_val is None:
                    fields.append('"child":null')
                elif isinstance(child_val, str):
                    # invalid type for child (string)
                    fields.append('"child":' + json_str(child_val))
                else:
                    # nested record string
                    fields.append('"child":' + child_val)

            # Join fields with commas
            obj_str = "{" + ",".join(fields) + "}"
            return obj_str

        return st.deferred(lambda: st.just(gen_record()))

    # Generate top-level record with recursion_depth=1 (allow one nested child)
    top_record_str = draw(record(1))

    # Return bytes
    return top_record_str.encode("utf-8")