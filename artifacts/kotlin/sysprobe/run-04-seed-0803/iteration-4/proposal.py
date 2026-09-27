from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
def json_string(s: str) -> str:
    # Escape backslash and double quote only for simplicity
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    # We produce a JSON text for the record schema:
    # {
    #   "id": <integer>,
    #   "amount": <string>,
    #   "name": <string or null>,
    #   "status": <one of "active", "inactive", "unknown">,
    #   "tags": <array of strings>,
    #   "child": <Record or null, one level recursion>
    # }
    #
    # We want to produce mostly well-formed documents with 0 or 1 subtle divergence:
    # - sometimes missing fields (testing missing vs present)
    # - sometimes null vs missing vs present
    # - sometimes wrong types for fields known to cause divergence (amount, tags, id)
    # - sometimes unknown enum values or case variants for status
    # - sometimes extra unknown keys (to trigger accept/reject)
    # - sometimes null for non-nullable fields (id, amount, tags, status)
    # - sometimes missing child vs null child vs present child
    # - sometimes child with 1-level recursion, but bounded depth
    #
    # We do not produce broadly malformed JSON (always valid JSON).
    #
    # We produce JSON text as bytes.

    # Constants
    statuses = ["active", "inactive", "unknown"]
    unknown_statuses = ["Active", "INACTIVE", "unknownx", ""]  # case variants and unknowns

    # Helper to produce JSON for a string or null
    def json_string_or_null(draw, allow_null=True):
        if allow_null:
            choice = draw(st.sampled_from(["string", "null"]))
        else:
            choice = "string"
        if choice == "null":
            return "null"
        else:
            s = draw(st.text(min_size=0, max_size=20))
            return json_string(s)

    # Helper to produce JSON for "amount" field:
    # Known divergence: accepts string normally,
    # Gson/Moshi/Jackson accept number coercing to string,
    # kotlinx.serialization rejects number.
    def json_amount(draw):
        # 80% string, 20% number (int or float)
        typ = draw(st.weighted_choices([(0.8, "string"), (0.2, "number")]))
        if typ == "string":
            s = draw(st.text(min_size=0, max_size=20))
            return json_string(s)
        else:
            # number as int or float
            n = draw(st.one_of(st.integers(-1000, 1000), st.floats(-1000, 1000, allow_nan=False, allow_infinity=False)))
            # JSON number formatting
            if isinstance(n, int):
                return str(n)
            else:
                # format float with minimal digits
                return repr(n)

    # Helper to produce JSON for "id" field:
    # integer normally,
    # but Gson/Jackson accept null (decoding as 0), Moshi/kotlinx reject null
    # Also test missing field (Gson accepts missing as 0, Moshi/kotlinx reject)
    def json_id(draw):
        # 70% integer, 15% null, 15% missing (handled outside)
        typ = draw(st.weighted_choices([(0.7, "int"), (0.15, "null"), (0.15, "missing")]))
        if typ == "int":
            return str(draw(st.integers(0, 10000)))
        elif typ == "null":
            return "null"
        else:
            return None  # missing

    # Helper to produce JSON for "name" field:
    # string or null, always present (name is nullable)
    def json_name(draw):
        return json_string_or_null(draw, allow_null=True)

    # Helper to produce JSON for "status" field:
    # enum string normally,
    # Gson accepts unknown/case-variant as null,
    # Moshi/kotlinx/Jackson reject unknown/case-variant,
    # Gson/Jackson accept null, Moshi/kotlinx reject null,
    # Also test missing (Moshi/kotlinx reject, Gson/Jackson reject)
    def json_status(draw):
        # 70% valid enum, 10% unknown/case variant, 10% null, 10% missing
        typ = draw(st.weighted_choices([(0.7, "valid"), (0.1, "unknown"), (0.1, "null"), (0.1, "missing")]))
        if typ == "valid":
            s = draw(st.sampled_from(statuses))
            return json_string(s)
        elif typ == "unknown":
            s = draw(st.sampled_from(unknown_statuses))
            return json_string(s)
        elif typ == "null":
            return "null"
        else:
            return None  # missing

    # Helper to produce JSON for "tags" field:
    # array of strings normally,
    # Gson/Jackson accept null (decoding as null),
    # Moshi/kotlinx reject null,
    # Gson/Moshi/Jackson accept arrays of integers coercing to strings,
    # kotlinx rejects arrays of integers,
    # Also test missing (Moshi/kotlinx reject, Gson/Jackson accept)
    def json_tags(draw):
        # 60% array of strings,
        # 15% array of ints (coerced to strings),
        # 10% null,
        # 15% missing
        typ = draw(st.weighted_choices([(0.6, "str_array"), (0.15, "int_array"), (0.1, "null"), (0.15, "missing")]))
        if typ == "str_array":
            arr = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
            # produce JSON array of strings
            return "[" + ",".join(json_string(s) for s in arr) + "]"
        elif typ == "int_array":
            arr = draw(st.lists(st.integers(-100, 100), min_size=0, max_size=5))
            return "[" + ",".join(str(i) for i in arr) + "]"
        elif typ == "null":
            return "null"
        else:
            return None  # missing

    # Helper to produce JSON for "child" field:
    # child is either null, missing, or a nested record (one level recursion)
    # Gson and Moshi accept missing child, kotlinx rejects missing child, Jackson accepts missing child
    # We limit recursion depth to 1 (child's child is always null)
    def json_child(draw, depth=0):
        # 50% null, 30% missing, 20% present nested record (only if depth == 0)
        if depth >= 1:
            # no further recursion, child is null or missing only
            typ = draw(st.sampled_from(["null", "missing"]))
        else:
            typ = draw(st.weighted_choices([(0.5, "null"), (0.3, "missing"), (0.2, "record")]))
        if typ == "null":
            return "null"
        elif typ == "missing":
            return None
        else:
            # nested record with child's child always null (no deeper recursion)
            # We reuse the same logic but force child's child to null and no missing fields
            # To keep it simple, child's child is always present and null
            # We produce a record JSON text with no missing fields, no nulls except child's child null
            # id: int
            cid = str(draw(st.integers(0, 10000)))
            # amount: string
            camount = json_string(draw(st.text(min_size=0, max_size=20)))
            # name: string or null
            cname = json_string_or_null(draw, allow_null=True)
            # status: valid enum only (to avoid too many rejects)
            cstatus = json_string(draw(st.sampled_from(statuses)))
            # tags: array of strings only
            ctags_arr = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=3))
            ctags = "[" + ",".join(json_string(s) for s in ctags_arr) + "]"
            # child: always null (no deeper recursion)
            cchild = "null"
            # Compose child record JSON
            child_fields = [
                '"id":' + cid,
                '"amount":' + camount,
                '"name":' + cname,
                '"status":' + cstatus,
                '"tags":' + ctags,
                '"child":' + cchild,
            ]
            return "{" + ",".join(child_fields) + "}"

    # Helper to produce extra unknown keys (Gson/Moshi accept, kotlinx/Jackson reject)
    def json_extra_keys(draw):
        # 30% chance to add 0 or 1 extra unknown keys
        if draw(st.booleans()):
            # one extra key with string or number value
            key = draw(st.text(min_size=1, max_size=10))
            # value: string or number
            if draw(st.booleans()):
                val = json_string(draw(st.text(min_size=0, max_size=20)))
            else:
                val = str(draw(st.integers(-1000, 1000)))
            return [json_string(key) + ":" + val]
        else:
            return []

    # Compose the top-level record fields, allowing missing fields where known to cause divergence
    # id
    id_val = json_id(draw)
    # amount
    amount_val = json_amount(draw)
    # name always present (nullable)
    name_val = json_name(draw)
    # status
    status_val = json_status(draw)
    # tags
    tags_val = json_tags(draw)
    # child
    child_val = json_child(draw, depth=0)

    # Compose fields list with presence control
    fields = []

    # id field: include only if not missing
    if id_val is not None:
        fields.append('"id":' + id_val)
    # amount always present (never missing, only string or number)
    fields.append('"amount":' + amount_val)
    # name always present
    fields.append('"name":' + name_val)
    # status: include only if not missing
    if status_val is not None:
        fields.append('"status":' + status_val)
    # tags: include only if not missing
    if tags_val is not None:
        fields.append('"tags":' + tags_val)
    # child: include only if not missing
    if child_val is not None:
        fields.append('"child":' + child_val)

    # Add extra unknown keys if any
    extra = json_extra_keys(draw)
    fields.extend(extra)

    # Shuffle fields order to test duplicate keys and order independence
    # Also, with 10% chance, add duplicate keys for one field (last wins)
    fields = draw(st.permutations(fields))
    if draw(st.booleans()):
        # pick one field to duplicate
        if len(fields) > 0:
            dup_field = draw(st.sampled_from(fields))
            fields = list(fields) + [dup_field]

    # Compose JSON text
    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")