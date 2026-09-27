```python
from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal with proper escaping for " and \
    def json_string(s: str) -> str:
        # Minimal escaping for " and \ only, enough for these tests
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # Recursive generator for a record JSON text (string)
    # max_depth limits recursion depth to avoid too deep nesting
    def gen_record(max_depth: int) -> st.SearchStrategy[str]:
        # id: integer
        id_strat = st.integers(min_value=0, max_value=2**31-1).map(str)

        # amount: string (non-empty or empty)
        amount_strat = st.text(min_size=0, max_size=10).map(json_string)

        # name: string or null
        name_strat = st.one_of(st.none(), st.text(min_size=0, max_size=10)).map(
            lambda v: "null" if v is None else json_string(v)
        )

        # status: enum string
        status_strat = st.sampled_from(STATUS_VALUES).map(json_string)

        # tags: array of strings (strings can be empty)
        tags_strat = st.lists(st.text(min_size=0, max_size=10), max_size=5).map(
            lambda lst: "[" + ",".join(json_string(s) for s in lst) + "]"
        )

        # child: null or nested record (one level recursion normally)
        if max_depth <= 0:
            child_strat = st.just("null")
        else:
            # To encourage divergences, sometimes omit child (but spec says always present)
            # So always present but sometimes null or nested record
            child_strat = st.one_of(
                st.just("null"),
                gen_record(max_depth - 1)
            )

        # Compose fields in canonical order
        # To produce almost well-formed documents with one thing off,
        # we will produce a base valid record, then apply one tweak in outer code.

        return st.tuples(id_strat, amount_strat, name_strat, status_strat, tags_strat, child_strat).map(
            lambda t: (
                '{'
                + '"id":' + t[0] + ','
                + '"amount":' + t[1] + ','
                + '"name":' + t[2] + ','
                + '"status":' + t[3] + ','
                + '"tags":' + t[4] + ','
                + '"child":' + t[5]
                + '}'
            )
        )

    # Generate a base valid record JSON string (depth 1 or 2)
    base_record = draw(gen_record(max_depth=2))

    # Now produce a list of candidate tweaks to apply exactly one:
    # Each tweak produces a syntactically valid JSON object string,
    # with exactly one field altered or missing or type-changed or boundary value,
    # to try to cause divergence.

    # We produce a list of functions that take the base JSON string and return a tweaked JSON string.
    # Because we do not parse JSON here, we reconstruct the JSON text from fields,
    # so we parse base_record back to fields by re-generating them with Hypothesis again.

    # Instead, we re-generate fields separately to apply tweaks more easily.

    # So instead of tweaking base_record string, we generate fields separately here:

    # Generate fields separately to apply tweaks:
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    amount_val = draw(st.text(min_size=0, max_size=10))
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
    status_val = draw(st.sampled_from(STATUS_VALUES))
    tags_val = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
    # child is either null or nested record (depth 1)
    def gen_child():
        return draw(st.one_of(
            st.just(None),
            st.tuples(
                st.integers(min_value=0, max_value=2**31-1),
                st.text(min_size=0, max_size=10),
                st.one_of(st.none(), st.text(min_size=0, max_size=10)),
                st.sampled_from(STATUS_VALUES),
                st.lists(st.text(min_size=0, max_size=10), max_size=3),
                st.just(None)  # child.child is always null to limit depth
            ).map(lambda t: {
                "id": t[0],
                "amount": t[1],
                "name": t[2],
                "status": t[3],
                "tags": t[4],
                "child": t[5]
            })
        ))

    child_val = gen_child()

    # Helper to encode a record dict to JSON string
    def encode_record(rec):
        # rec is dict with keys: id, amount, name, status, tags, child
        def encode_string_or_null(v):
            if v is None:
                return "null"
            else:
                return json_string(v)

        def encode_tags(lst):
            return "[" + ",".join(json_string(s) for s in lst) + "]"

        def encode_child(c):
            if c is None:
                return "null"
            else:
                return encode_record(c)

        return (
            '{'
            + '"id":' + str(rec["id"]) + ','
            + '"amount":' + json_string(rec["amount"]) + ','
            + '"name":' + encode_string_or_null(rec["name"]) + ','
            + '"status":' + json_string(rec["status"]) + ','
            + '"tags":' + encode_tags(rec["tags"]) + ','
            + '"child":' + encode_child(rec["child"])
            + '}'
        )

    base_obj = {
        "id": id_val,
        "amount": amount_val,
        "name": name_val,
        "status": status_val,
        "tags": tags_val,
        "child": child_val,
    }

    # Now define tweaks as functions returning JSON strings with exactly one field altered
    tweaks = []

    # 1) id as string (should be rejected by all, but maybe some differ)
    def tweak_id_string():
        rec = base_obj.copy()
        rec["id"] = str(rec["id"])
        return encode_record(rec)

    tweaks.append(tweak_id_string)

    # 2) amount as integer (should be rejected by all)
    def tweak_amount_int():
        rec = base_obj.copy()
        rec["amount"] = 12345  # int instead of string
        # encode_record expects amount as string, so encode manually:
        def encode_record_amount_int(rec):
            def encode_string_or_null(v):
                if v is None:
                    return "null"
                else:
                    return json_string(v)

            def encode_tags(lst):
                return "[" + ",".join(json_string(s) for s in lst) + "]"

            def encode_child(c):
                if c is None:
                    return "null"
                else:
                    return encode_record(c)

            return (
                '{'
                + '"id":' + str(rec["id"]) + ','
                + '"amount":' + str(rec["amount"]) + ','
                + '"name":' + encode_string_or_null(rec["name"]) + ','
                + '"status":' + json_string(rec["status"]) + ','
                + '"tags":' + encode_tags(rec["tags"]) + ','
                + '"child":' + encode_child(rec["child"])
                + '}'
            )
        return encode_record_amount_int(rec)

    tweaks.append(tweak_amount_int)

    # 3) name as integer (should be rejected by all)
    def tweak_name_int():
        rec = base_obj.copy()
        rec["name"] = 999
        def encode_record_name_int(rec):
            def encode_string_or_null(v):
                if v is None:
                    return "null"
                elif isinstance(v, int):
                    return str(v)
                else:
                    return json_string(v)

            def encode_tags(lst):
                return "[" + ",".join(json_string(s) for s in lst) + "]"

            def encode_child(c):
                if c is None:
                    return "null"
                else:
                    return encode_record(c)

            return (
                '{'
                + '"id":' + str(rec["id"]) + ','
                + '"amount":' + json_string(rec["amount"]) + ','
                + '"name":' + encode_string_or_null(rec["name"]) + ','
                + '"status":' + json_string(rec["status"]) + ','
                + '"tags":' + encode_tags(rec["tags"]) + ','
                + '"child":' + encode_child(rec["child"])
                + '}'
            )
        return encode_record_name_int(rec)

    tweaks.append(tweak_name_int)

    # 4) status invalid enum (string "invalid")
    def tweak_status_invalid():
        rec = base_obj.copy()
        rec["status"] = "invalid"
        return encode_record(rec)

    tweaks.append(tweak_status_invalid)

    # 5) tags contains integer (should be rejected by all)
    def tweak_tags_int():
        rec = base_obj.copy()
        if len(rec["tags"]) == 0:
            rec["tags"] = ["tag1"]
        rec["tags"] = rec["tags"][:-1] + [2]
        def encode_record_tags_int(rec):
            def encode_string_or_null(v):
                if v is None:
                    return "null"
                else:
                    return json_string(v)

            def encode_tags(lst):
                parts = []
                for x in lst:
                    if isinstance(x, int):
                        parts.append(str(x))
                    else:
                        parts.append(json_string(x))
                return "[" + ",".join(parts) + "]"

            def encode_child(c):
                if c is None:
                    return "null"
                else:
                    return encode_record(c)

            return (
                '{'
                + '"id":' + str(rec["id"]) + ','
                + '"amount":' + json_string(rec["amount"]) + ','
                + '"name":' + encode_string_or_null(rec["name"]) + ','
                + '"status":' + json_string(rec["status"]) + ','
                + '"tags":' + encode_tags(rec["tags"]) + ','
                + '"child":' + encode_child(rec["child"])
                + '}'
            )
        return encode_record_tags_int(rec)

    tweaks.append(tweak_tags_int)

    # 6) tags contains null (should be rejected by all)
    def tweak_tags_null():
        rec = base_obj.copy()
        if len(rec["tags"]) == 0:
            rec["tags"] = ["tag1"]
        rec["tags"] = rec["tags"][:-1] + [None]
        def encode_record_tags_null(rec):
            def encode_string_or_null(v):
                if v is None:
                    return "null"
                else:
                    return json_string(v)

            def encode_tags(lst):
                parts = []
                for x in lst:
                    if x is None:
                        parts.append("null")
                    else:
                        parts.append(json_string(x))
                return "[" + ",".join(parts) + "]"

            def encode_child(c):
                if c is None:
                    return "null"
                else:
                    return encode_record(c)

            return (
                '{'
                + '"id":