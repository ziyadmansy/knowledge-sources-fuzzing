from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Base valid fields strategies
    id_strat = st.integers(min_value=0, max_value=2**31-1)
    amount_strat = st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))  # printable ascii
    # name nullable string
    name_strat = st.one_of(st.none(), st.text(min_size=0, max_size=10))
    status_strat = st.sampled_from(STATUS_VALUES)
    # tags: array of strings (strings nonempty, ascii printable)
    tag_strat = st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))
    tags_strat = st.lists(tag_strat, max_size=3)

    # To induce divergences, we will create a mostly valid record, then
    # vary exactly one or two fields in subtle ways:
    # - missing required field (except tags and status which built_value accepts)
    # - null for non-nullable fields (except name)
    # - wrong type for a field (e.g. number instead of string)
    # - enum with invalid value (but only one invalid value per doc)
    # - child null or valid record or invalid record (wrong type or missing fields)
    # - tags null (built_value accepts as empty array), or tags with null element (all reject)
    # - duplicate keys (last wins) - but this is accepted by all, so no divergence
    # - extra keys ignored by all, no divergence

    # We build a valid base record first
    def gen_base_record():
        return st.fixed_dictionaries({
            "id": id_strat,
            "amount": amount_strat,
            "name": name_strat,
            "status": status_strat,
            "tags": tags_strat,
            "child": st.none(),  # initially no child
        })

    # Recursive child record, max depth 1 (only one level)
    # To avoid infinite recursion, child is either null or a base record with child=null
    child_record = st.deferred(lambda: st.one_of(
        st.none(),
        gen_base_record().map(lambda d: {**d, "child": None})
    ))

    # We redefine gen_base_record with child possibility
    def gen_base_record_with_child():
        return st.fixed_dictionaries({
            "id": id_strat,
            "amount": amount_strat,
            "name": name_strat,
            "status": status_strat,
            "tags": tags_strat,
            "child": child_record,
        })

    base_record = gen_base_record_with_child()

    # Now define subtle mutations that cause divergence:
    # We pick one or two fields to mutate per record, else keep valid.

    # Mutation strategies for fields:
    # 1) Missing required field (except tags and status which built_value accepts)
    # 2) Null for non-nullable fields (except name)
    # 3) Wrong type for field
    # 4) Enum invalid value (only for status)
    # 5) tags null (built_value accepts), tags with null element (all reject)
    # 6) child wrong type or malformed

    # Field names and their types:
    # id: int (required, non-nullable)
    # amount: string (required, non-nullable)
    # name: string or null (required, nullable)
    # status: enum string (required, non-nullable)
    # tags: array of strings (required, non-nullable)
    # child: record or null (nullable)

    # Helper to serialize JSON string with proper escaping (only minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars minimally
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Escape control chars (0x00-0x1F)
        s = ''.join(c if 0x20 <= ord(c) <= 0x7E else '\\u%04x' % ord(c) for c in s)
        return f'"{s}"'

    # Serialize JSON value from Python value (int, str, None, list, dict)
    # We build JSON text manually to avoid importing json module
    def serialize_json(val) -> str:
        if val is None:
            return "null"
        elif isinstance(val, bool):
            return "true" if val else "false"
        elif isinstance(val, int):
            return str(val)
        elif isinstance(val, str):
            return json_string(val)
        elif isinstance(val, list):
            return "[" + ",".join(serialize_json(v) for v in val) + "]"
        elif isinstance(val, dict):
            # keys are strings
            items = []
            for k, v in val.items():
                items.append(json_string(k) + ":" + serialize_json(v))
            return "{" + ",".join(items) + "}"
        else:
            # fallback, should not happen
            return "null"

    # Mutation functions that produce dicts with one subtle error
    def mutate_missing_field(d: dict, field: str) -> dict:
        # Remove field from dict
        d2 = dict(d)
        if field in d2:
            del d2[field]
        return d2

    def mutate_null_field(d: dict, field: str) -> dict:
        d2 = dict(d)
        d2[field] = None
        return d2

    def mutate_wrong_type_field(d: dict, field: str) -> dict:
        d2 = dict(d)
        # For each field, pick a wrong type value:
        # id: string instead of int
        # amount: int instead of string
        # name: int instead of string/null
        # status: int instead of string
        # tags: int instead of array
        # child: int instead of object/null
        wrong_values = {
            "id": "wrong_type",
            "amount": 123,
            "name": 456,
            "status": 789,
            "tags": 42,
            "child": 99,
        }
        d2[field] = wrong_values[field]
        return d2

    def mutate_enum_invalid(d: dict) -> dict:
        d2 = dict(d)
        # invalid enum value for status
        d2["status"] = "invalid_status"
        return d2

    def mutate_tags_null(d: dict) -> dict:
        d2 = dict(d)
        d2["tags"] = None
        return d2

    def mutate_tags_with_null_element(d: dict) -> dict:
        d2 = dict(d)
        # tags array with one null element (all reject)
        tags = d2.get("tags", [])
        if not tags:
            tags = ["tag1"]
        d2["tags"] = [tags[0], None]
        return d2

    def mutate_child_wrong_type(d: dict) -> dict:
        d2 = dict(d)
        d2["child"] = 12345  # int instead of object/null
        return d2

    def mutate_child_malformed(d: dict) -> dict:
        d2 = dict(d)
        # child object missing required field "id"
        if d2["child"] is None:
            # create a malformed child
            d2["child"] = {
                "amount": "10",
                "name": None,
                "status": "active",
                "tags": [],
                "child": None,
            }
        else:
            # remove id from existing child
            child = dict(d2["child"])
            if "id" in child:
                del child["id"]
            d2["child"] = child
        return d2

    # Compose all mutation strategies with weights
    # Also include "valid" (no mutation) to keep diversity
    mutation_strategies = [
        ("valid", lambda d: d),
        ("missing_id", lambda d: mutate_missing_field(d, "id")),
        ("missing_amount", lambda d: mutate_missing_field(d, "amount")),
        ("missing_name", lambda d: mutate_missing_field(d, "name")),
        ("missing_status", lambda d: mutate_missing_field(d, "status")),
        # missing tags is accepted by built_value, so interesting
        ("missing_tags", lambda d: mutate_missing_field(d, "tags")),
        ("null_id", lambda d: mutate_null_field(d, "id")),
        ("null_amount", lambda d: mutate_null_field(d, "amount")),
        ("null_status", lambda d: mutate_null_field(d, "status")),
        ("null_tags", mutate_tags_null),
        ("wrong_type_id", lambda d: mutate_wrong_type_field(d, "id")),
        ("wrong_type_amount", lambda d: mutate_wrong_type_field(d, "amount")),
        ("wrong_type_name", lambda d: mutate_wrong_type_field(d, "name")),
        ("wrong_type_status", lambda d: mutate_wrong_type_field(d, "status")),
        ("wrong_type_tags", lambda d: mutate_wrong_type_field(d, "tags")),
        ("wrong_type_child", mutate_child_wrong_type),
        ("enum_invalid_status", mutate_enum_invalid),
        ("tags_with_null_element", mutate_tags_with_null_element),
        ("child_malformed", mutate_child_malformed),
    ]

    # Pick one mutation per example, weighted to favor mutations that cause divergence
    # Weights chosen heuristically to favor known divergence-causing mutations
    weights = [
        10,  # valid
        8,  # missing_id
        8,  # missing_amount
        2,  # missing_name (all reject)
        6,  # missing_status (built_value accepts)
        6,  # missing_tags (built_value accepts)
        8,  # null_id
        8,  # null_amount
        6,  # null_status
        6,  # null_tags
        8,  # wrong_type_id
        8,  # wrong_type_amount
        6,  # wrong_type_name
        6,  # wrong_type_status
        6,  # wrong_type_tags
        6,  # wrong_type_child
        6,  # enum_invalid_status
        6,  # tags_with_null_element
        6,  # child_malformed
    ]

    mutation_choice = draw(st.choices(mutation_strategies, weights=weights, k=1))[0]

    base = draw(base_record)

    mutated = mutation_choice[1](base)

    # Serialize mutated dict to JSON string
    json_text = serialize_json(mutated)

    # Return bytes
    return json_text.encode("utf-8")