from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]
    # id: integer, always present, non-null
    id_val = draw(st.integers(min_value=-(2**31), max_value=2**31-1))
    # amount: string, always present, non-null
    # To induce subtle divergences, allow empty string and strings with spaces
    amount_val = draw(st.text(min_size=0, max_size=20))
    # name: string or null, always present (null allowed)
    # To induce divergence, sometimes null, sometimes string (including empty)
    name_val = draw(st.one_of(st.none(), st.text(max_size=20)))
    # status: enum string, always present, non-null, case-sensitive
    # To induce divergence, mostly valid, sometimes invalid or case variant
    # But probes show all reject invalid or case variants, so keep mostly valid
    # To maximize divergence, sometimes use valid, sometimes invalid but known to be rejected
    status_val = draw(
        st.one_of(
            st.sampled_from(STATUS_VALUES),
            # invalid enum to test rejection divergence
            st.just("invalid"),
            st.just("ACTIVE"),
        )
    )
    # tags: array of strings, always present, non-null
    # built_value accepts null tags and converts to empty array, others reject null
    # To induce divergence, sometimes null, sometimes empty array, sometimes array with strings
    tags_val = draw(
        st.one_of(
            st.none(),
            st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5),
        )
    )
    # child: Record or null, always present (except manual/json_serializable/freezed reject missing)
    # built_value accepts missing child and defaults to null
    # To induce divergence, sometimes null, sometimes valid child, sometimes child with subtle errors
    # Limit recursion depth to 1 (one level of child)
    # Compose child record similarly but simpler: no nested child inside child (child.child always null)
    def child_record():
        # id: integer non-null
        c_id = draw(st.integers(min_value=-(2**31), max_value=2**31-1))
        # amount: string non-null
        c_amount = draw(st.text(min_size=0, max_size=20))
        # name: string or null
        c_name = draw(st.one_of(st.none(), st.text(max_size=20)))
        # status: valid enum only here to reduce complexity (invalid tested at top level)
        c_status = draw(st.sampled_from(STATUS_VALUES))
        # tags: non-null array of strings (empty allowed)
        c_tags = draw(st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5))
        # child: always null (no deeper recursion)
        c_child = None

        # Build JSON text for child record
        # Fields always present, no missing keys
        # name can be null or string
        # child is null
        # tags is array of strings
        # status is string enum
        # amount is string
        # id is integer
        # Compose JSON string manually
        def json_escape(s):
            # minimal escaping for JSON string: backslash and quote
            return s.replace('\\', '\\\\').replace('"', '\\"')

        child_json = (
            '{'
            f'"id":{c_id},'
            f'"amount":"{json_escape(c_amount)}",'
            f'"name":'
            + ("null" if c_name is None else f'"{json_escape(c_name)}"')
            + ','
            f'"status":"{c_status}",'
            f'"tags":['
            + ",".join(f'"{json_escape(t)}"' for t in c_tags)
            + '],'
            f'"child":null'
            '}'
        )
        return child_json

    # Decide child field value:
    #  - missing (to test missing child rejection by manual/json_serializable/freezed, accepted by built_value)
    #  - null
    #  - valid child record
    #  - child with subtle error: e.g. child with null id (known to be rejected by all)
    # To maximize divergence, do not produce child with null id (all reject)
    # Instead produce missing child, null child, or valid child
    child_choice = draw(st.sampled_from(["missing", "null", "valid"]))
    if child_choice == "missing":
        child_field_present = False
        child_json = None
    elif child_choice == "null":
        child_field_present = True
        child_json = "null"
    else:  # valid
        child_field_present = True
        child_json = child_record()

    # Compose tags JSON text
    def json_escape(s):
        # minimal escaping for JSON string: backslash and quote
        return s.replace('\\', '\\\\').replace('"', '\\"')

    if tags_val is None:
        tags_json = "null"
    else:
        tags_json = "[" + ",".join(f'"{json_escape(t)}"' for t in tags_val) + "]"

    # Compose name JSON text
    if name_val is None:
        name_json = "null"
    else:
        name_json = f'"{json_escape(name_val)}"'

    # Compose status JSON text
    # status_val is string, possibly invalid or case variant
    status_json = f'"{json_escape(status_val)}"'

    # Compose amount JSON text
    amount_json = f'"{json_escape(amount_val)}"'

    # Compose id JSON text
    id_json = str(id_val)

    # Compose top-level JSON object text
    # Fields always present except child may be missing
    # Order fields as per schema: id, amount, name, status, tags, child (if present)
    parts = [
        f'"id":{id_json}',
        f'"amount":{amount_json}',
        f'"name":{name_json}',
        f'"status":{status_json}',
        f'"tags":{tags_json}',
    ]
    if child_field_present:
        parts.append(f'"child":{child_json}')

    json_text = "{" + ",".join(parts) + "}"

    # Return bytes
    return json_text.encode("utf-8")