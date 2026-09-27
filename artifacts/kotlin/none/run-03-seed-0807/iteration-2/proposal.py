from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for the schema
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

    # Helper: produce a JSON string literal with proper escaping for simple ASCII only
    def json_string(s: str) -> str:
        # Escape backslash and double quote only, minimal escaping for ASCII
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Helper: produce a JSON null or a nested record (one level recursion max)
    # We use bounded recursion: max depth 1 (top-level + child)
    def record(depth: int) -> st.SearchStrategy[str]:
        # At depth 1, child must be null (no further recursion)
        # At depth 0, child can be null or a record at depth 1
        # We produce a dict as JSON text with all fields present, but some fields
        # may be "wrong" type or missing to induce divergences.

        # id: integer normally, but sometimes string or float or null or missing
        id_strat = st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: f'{f:.6g}'),
            st.text(min_size=1, max_size=5).map(json_string),
            st.just("null"),
        )

        # amount: string normally, but sometimes number, null, missing
        amount_strat = st.one_of(
            st.text(min_size=1, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=100000).map(str),
            st.just("null"),
        )

        # name: string or null normally, but sometimes number, missing
        name_strat = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=1000).map(str),
        )

        # status: one of three strings normally, but sometimes wrong string, number, null
        status_strat = st.one_of(
            st.sampled_from(STATUS_VALUES),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown']).map(json_string),
            st.integers(min_value=0, max_value=10).map(str),
            st.just("null"),
        )

        # tags: array of strings normally, but sometimes array of numbers, null, empty array, missing
        tags_strat = st.one_of(
            st.lists(st.text(min_size=0, max_size=5).map(json_string), min_size=0, max_size=5).map(
                lambda lst: "[" + ",".join(lst) + "]"
            ),
            st.lists(st.integers(min_value=0, max_value=100).map(str), min_size=0, max_size=5).map(
                lambda lst: "[" + ",".join(lst) + "]"
            ),
            st.just("null"),
        )

        # child: null or nested record (depth+1), or malformed (string, number)
        if depth >= 1:
            # no further recursion, child must be null or malformed
            child_strat = st.one_of(
                st.just("null"),
                st.text(min_size=1, max_size=10).map(json_string),
                st.integers(min_value=0, max_value=1000).map(str),
            )
        else:
            # child can be null or a nested record at depth+1 or malformed
            child_strat = st.one_of(
                st.just("null"),
                record(depth + 1),
                st.text(min_size=1, max_size=10).map(json_string),
                st.integers(min_value=0, max_value=1000).map(str),
            )

        # Compose fields with possibility of missing or wrong type for one or two fields
        # To maximize divergence, we produce mostly well-formed documents with 1-2 fields off.

        # We decide which fields to "corrupt" (wrong type or missing)
        fields = ["id", "amount", "name", "status", "tags", "child"]
        # Pick 0,1 or 2 fields to corrupt
        corrupt_count = draw(st.integers(min_value=0, max_value=2))
        corrupt_fields = draw(st.lists(st.sampled_from(fields), min_size=corrupt_count, max_size=corrupt_count, unique=True))

        # For each field, produce value or omit if corrupt and chosen to omit
        # We do not omit id or amount (always present) to keep mostly valid
        # But we allow omission of name, status, tags, child if corrupt

        # For each field, produce a value or omit
        def field_value(field):
            if field == "id":
                val = draw(id_strat)
                if "id" in corrupt_fields:
                    # corrupt id: sometimes omit or wrong type
                    # but id is mandatory, so omit only rarely
                    omit = draw(st.booleans())
                    if omit:
                        return None
                    else:
                        # corrupt value already from id_strat includes wrong types
                        return val
                else:
                    return val
            elif field == "amount":
                val = draw(amount_strat)
                if "amount" in corrupt_fields:
                    omit = draw(st.booleans())
                    if omit:
                        return None
                    else:
                        return val
                else:
                    return val
            elif field == "name":
                if "name" in corrupt_fields:
                    omit = draw(st.booleans())
                    if omit:
                        return None
                    else:
                        return draw(name_strat)
                else:
                    return draw(name_strat)
            elif field == "status":
                if "status" in corrupt_fields:
                    omit = draw(st.booleans())
                    if omit:
                        return None
                    else:
                        return draw(status_strat)
                else:
                    return draw(status_strat)
            elif field == "tags":
                if "tags" in corrupt_fields:
                    omit = draw(st.booleans())
                    if omit:
                        return None
                    else:
                        return draw(tags_strat)
                else:
                    return draw(tags_strat)
            elif field == "child":
                if "child" in corrupt_fields:
                    omit = draw(st.booleans())
                    if omit:
                        return None
                    else:
                        return draw(child_strat)
                else:
                    return draw(child_strat)
            else:
                return None

        # Build JSON object text
        parts = []
        for f in fields:
            val = field_value(f)
            if val is not None:
                parts.append(f'"{f}":{val}')
            else:
                # omit field entirely
                pass

        json_text = "{" + ",".join(parts) + "}"

        return json_text.encode("utf-8")

    return draw(record(0))