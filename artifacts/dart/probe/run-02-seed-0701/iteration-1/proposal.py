from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]
    # id: integer
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    # amount: string representing a decimal number, but allow edge cases like "0", "0.0", "123.45"
    # We keep it always string to avoid rejection by all.
    amount_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s) and s.count('.') <= 1 and not s.startswith('.')))
    # name: string or null
    # To maximize subtlety, sometimes null, sometimes string, sometimes empty string
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
    # status: one of the enum values or an invalid enum to test rejection differences
    # But all reject invalid enum values, so only use valid ones here to avoid all rejecting
    status_val = draw(st.sampled_from(STATUS_VALUES))
    # tags: array of strings normally, but built_value accepts null for tags, others reject
    # So sometimes tags is null, sometimes a list of strings
    tags_val = draw(st.one_of(
        st.none(),
        st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5)
    ))
    # child: either null or a nested record (one level recursion)
    # To keep bounded recursion, child is either null or a record with no child (child=null)
    # We will produce a nested record with the same schema but child=null
    def gen_child():
        child_id = draw(st.integers(min_value=0, max_value=2**31-1))
        child_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s) and s.count('.') <= 1 and not s.startswith('.')))
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        child_status = draw(st.sampled_from(STATUS_VALUES))
        child_tags = draw(st.one_of(
            st.none(),
            st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5)
        ))
        # child.child is null to avoid deep recursion
        # We will build JSON text for child here as a string
        # Use duplicate keys or subtle type variants in child to try to cause divergence
        # For example, duplicate keys in child "id" or "tags" to test last occurrence behavior
        # But all take last occurrence, so no divergence expected here, just keep normal
        # We can try to produce child with tags=null sometimes to trigger built_value acceptance
        # but others reject
        # Compose child JSON string manually
        # Use double quotes and escape strings properly (only simple ASCII here)
        def json_str(s):
            # Escape backslash and double quote
            return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
        child_json = (
            '{'
            f'"id":{child_id},'
            f'"amount":{json_str(child_amount)},'
            f'"name":{("null" if child_name is None else json_str(child_name))},'
            f'"status":{json_str(child_status)},'
            f'"tags":{("null" if child_tags is None else "[" + ",".join(json_str(t) for t in child_tags) + "]")},'
            f'"child":null'
            '}'
        )
        return child_json

    child_val = draw(st.one_of(st.none(), st.just(gen_child())))

    # Build JSON string for root object
    def json_str(s):
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Compose tags JSON
    if tags_val is None:
        tags_json = "null"
    else:
        tags_json = "[" + ",".join(json_str(t) for t in tags_val) + "]"

    # Compose name JSON
    name_json = "null" if name_val is None else json_str(name_val)

    # Compose child JSON
    child_json = "null" if child_val is None else child_val

    # Compose root JSON string
    root_json = (
        '{'
        f'"id":{id_val},'
        f'"amount":{json_str(amount_val)},'
        f'"name":{name_json},'
        f'"status":{json_str(status_val)},'
        f'"tags":{tags_json},'
        f'"child":{child_json}'
        '}'
    )

    return root_json.encode("utf-8")