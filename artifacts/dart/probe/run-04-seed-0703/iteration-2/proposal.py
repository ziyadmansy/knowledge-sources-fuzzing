from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for allowed values
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Base valid fields strategies
    id_strat = st.integers(min_value=0, max_value=2**31-1)
    amount_strat = st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))
    name_strat = st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)))
    status_strat = st.sampled_from(STATUS_VALUES)
    tags_strat = st.lists(st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), max_size=5)

    # To produce slight divergences, we will sometimes:
    # - Replace a field with a wrong type (but only one field at a time)
    # - Omit a field (to test missing required fields)
    # - Use null where not allowed (e.g. for status)
    # - Use empty strings or empty arrays
    # - Use nested child with one level recursion, or null
    # - Use nested child with missing fields or wrong types (to test rejection)
    # - Use boundary values (empty string, zero, empty array)
    # - Use extra fields (allowed, but might cause subtle differences)
    # - Use subtle type confusions (e.g. integer as string "0", string "0" as integer)
    # But only one or two such "off" things per document to maximize divergence chances.

    # Strategy to generate a valid child record or null
    # We limit recursion depth to 1 normally, but allow 2 levels sometimes.
    # We also allow malformed child sometimes (missing fields or wrong types)
    def child_strategy(depth=0):
        if depth > 1:
            # At max depth, only null or valid child with no further recursion
            return st.one_of(st.none(), valid_record_strategy(depth=2))
        else:
            # Sometimes produce malformed child (missing fields or wrong types)
            malformed_child = st.just("malformed")  # placeholder, will be replaced
            # We'll produce either valid child or null or malformed child
            # malformed child: missing fields or wrong types
            # We'll implement malformed child as a dict missing one required field or with wrong type in one field
            def malformed_child_strategy():
                # Start from valid record dict
                base = draw_record_dict(depth=depth+1)
                # Remove one required field or replace one field with wrong type
                keys = ["id", "amount", "name", "status", "tags", "child"]
                # Choose one field to break
                field_to_break = draw(st.sampled_from(keys))
                d = dict(base)
                if field_to_break == "id":
                    # id as string (wrong type)
                    d["id"] = "wrong"
                elif field_to_break == "amount":
                    # amount as integer (wrong type)
                    d["amount"] = 123
                elif field_to_break == "name":
                    # name as integer (wrong type)
                    d["name"] = 456
                elif field_to_break == "status":
                    # status invalid string
                    d["status"] = "badstatus"
                elif field_to_break == "tags":
                    # tags as string (wrong type)
                    d["tags"] = "notarray"
                elif field_to_break == "child":
                    # child missing required fields or wrong type
                    d["child"] = {"id": 1}  # missing fields
                return d

            # We cannot call draw inside child_strategy because it's nested.
            # So we return a strategy that includes malformed child as a st.deferred
            # We'll implement malformed child as a separate strategy outside.

            # So child_strategy returns a strategy of either:
            # - None
            # - Valid record dict (depth+1)
            # - Malformed record dict (depth+1)
            # We'll implement malformed child outside and combine here.

            # To avoid complexity, we return only None or valid record here.
            # Malformed child will be injected at top level by replacing child field.

            return st.one_of(st.none(), valid_record_strategy(depth=depth+1))

    # Helper to produce a valid record dict (all fields present, correct types)
    def draw_record_dict(depth=0):
        # We cannot call draw here, so this is a helper for internal use only.
        # Instead, we will build a strategy that produces valid record dicts.
        # We'll implement valid_record_strategy below.
        pass

    # Valid record dict strategy (all fields present, correct types)
    @st.composite
    def valid_record_strategy(draw, depth=0):
        idv = draw(id_strat)
        amountv = draw(amount_strat)
        namev = draw(name_strat)
        statusv = draw(status_strat)
        tagsv = draw(tags_strat)
        childv = draw(child_strategy(depth=depth))
        return {
            "id": idv,
            "amount": amountv,
            "name": namev,
            "status": statusv,
            "tags": tagsv,
            "child": childv,
        }

    # Strategy to produce a dict with one field missing (to test missing required fields)
    @st.composite
    def missing_field_strategy(draw):
        base = draw(valid_record_strategy())
        # Remove one required field (not child, because child can be null)
        field_to_remove = draw(st.sampled_from(["id", "amount", "name", "status", "tags"]))
        d = dict(base)
        d.pop(field_to_remove)
        return d

    # Strategy to produce a dict with one field of wrong type (one field only)
    @st.composite
    def one_wrong_type_field_strategy(draw):
        base = draw(valid_record_strategy())
        field_to_break = draw(st.sampled_from(["id", "amount", "name", "status", "tags", "child"]))
        d = dict(base)
        if field_to_break == "id":
            # id as string (wrong type)
            d["id"] = "wrong"
        elif field_to_break == "amount":
            # amount as integer (wrong type)
            d["amount"] = 123
        elif field_to_break == "name":
            # name as integer (wrong type)
            d["name"] = 456
        elif field_to_break == "status":
            # status invalid string
            d["status"] = "badstatus"
        elif field_to_break == "tags":
            # tags as string (wrong type)
            d["tags"] = "notarray"
        elif field_to_break == "child":
            # child malformed: missing fields or wrong type
            # We'll produce a child with missing fields
            d["child"] = {"id": 1}
        return d

    # Strategy to produce a dict with one field null where not allowed (e.g. status)
    @st.composite
    def one_null_field_strategy(draw):
        base = draw(valid_record_strategy())
        # Only status is not nullable normally, so test null there
        d = dict(base)
        d["status"] = None
        return d

    # Strategy to produce a dict with extra fields (allowed)
    @st.composite
    def extra_fields_strategy(draw):
        base = draw(valid_record_strategy())
        d = dict(base)
        # Add 1-3 extra fields with string keys and simple values
        n_extra = draw(st.integers(min_value=1, max_value=3))
        for i in range(n_extra):
            key = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in d))
            val = draw(st.one_of(st.integers(), st.text(min_size=0, max_size=10), st.none()))
            d[key] = val
        return d

    # Strategy to produce a dict with subtle type confusions (e.g. id as string "0")
    @st.composite
    def subtle_type_confusion_strategy(draw):
        base = draw(valid_record_strategy())
        d = dict(base)
        # Choose one field to subtly confuse
        field = draw(st.sampled_from(["id", "amount"]))
        if field == "id":
            # id as string numeric
            d["id"] = str(d["id"])
        else:
            # amount as string numeric is normal, so try amount as integer string with leading zeros
            d["amount"] = "000" + d["amount"]
        return d

    # Strategy to produce a dict with child null or valid or malformed (missing fields)
    @st.composite
    def child_variants_strategy(draw):
        base = draw(valid_record_strategy())
        d = dict(base)
        choice = draw(st.integers(min_value=0, max_value=2))
        if choice == 0:
            d["child"] = None
        elif choice == 1:
            d["child"] = draw(valid_record_strategy(depth=1))
        else:
            # malformed child missing fields
            d["child"] = {"id": 1}
        return d

    # Compose a top-level strategy that picks one of the above variants or a plain valid record
    top_level_strategy = st.one_of(
        valid_record_strategy(),
        missing_field_strategy(),
        one_wrong_type_field_strategy(),
        one_null_field_strategy(),
        extra_fields_strategy(),
        subtle_type_confusion_strategy(),
        child_variants_strategy(),
    )

    # Now map the dict to a JSON string manually (no json module)
    # We must produce syntactically valid JSON objects only.
    # We'll implement a recursive function to encode JSON values as strings.

    def json_escape_str(s: str) -> str:
        # Escape backslash, double quote, and control chars minimally
        # We only allow printable ASCII in strings, so minimal escaping needed
        # Escape backslash and double quote
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Escape control chars (0x00-0x1F) as \u00XX
        def esc_char(c):
            if ord(c) < 0x20:
                return "\\u%04x" % ord(c)
            else:
                return c
        s = "".join(esc_char(c) for c in s)
        return '"' + s + '"'

    def json_encode(value) -> str:
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, int):
            return str(value)
        elif isinstance(value, str):
            return json_escape_str(value)
        elif isinstance(value, list):
            return "[" + ",".join(json_encode(v) for v in value) + "]"
        elif isinstance(value, dict):
            # keys must be strings
            items = []
            for k, v in value.items():
                items.append(json_escape_str(k) + ":" + json_encode(v))
            return "{" + ",".join(items) + "}"
        else:
            # Should not happen
            raise ValueError("Unsupported type in json_encode")

    # Draw a dict from top_level_strategy
    d = draw(top_level_strategy)
    # Encode to JSON string
    json_text = json_encode(d)
    # Return as bytes
    return json_text.encode("utf-8")