from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for allowed status values
    allowed_status = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal (with quotes, escaped)
    def json_string(s: str) -> str:
        # Minimal escaping for JSON string (only backslash and quote)
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'

    # Helper to produce JSON array of strings
    def json_array_of_strings(lst):
        return "[" + ",".join(json_string(s) for s in lst) + "]"

    # Generate a valid "id" integer
    id_val = draw(st.integers(min_value=0, max_value=10**9))

    # Generate a valid "amount" string (decimal-like)
    amount_val = draw(
        st.one_of(
            # Normal decimal strings
            st.decimals(min_value=0, max_value=10**9, places=2).map(lambda d: format(d, "f")),
            # Also allow integer strings
            st.integers(min_value=0, max_value=10**9).map(str),
        )
    )

    # Generate "name" as either null or string
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))

    # Generate "status" - mostly valid, but sometimes invalid to provoke divergence
    # Strategy hint: mostly valid, but sometimes a close invalid string or null
    status_val = draw(
        st.one_of(
            st.sampled_from(allowed_status),
            # Close invalid strings (e.g. "active " with trailing space, "enabled", "unknownn")
            st.sampled_from(["active ", "inactive ", "enabled", "unknownn"]),
            # null (known to be rejected by all)
            st.none(),
        )
    )

    # Generate "tags" array of strings
    # Mostly valid arrays of strings, but sometimes inject a non-string element or empty array
    # To maximize chance of divergence, sometimes produce a single-element array with a null or int
    tags_valid = st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5)
    tags_invalid_element = st.one_of(st.integers(), st.none())
    tags_val = draw(
        st.one_of(
            tags_valid,
            # Inject one invalid element in array
            st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=4).flatmap(
                lambda good_list: st.tuples(
                    st.just(good_list),
                    tags_invalid_element,
                    st.integers(min_value=0, max_value=len(good_list)),
                )
            ).map(
                lambda tpl: tpl[0][:tpl[2]] + [tpl[1]] + tpl[0][tpl[2]:]
            ),
        )
    )

    # Recursive generation of "child" record or null
    # Limit recursion depth to 1 normally, but sometimes 2 to test nested recursion
    def gen_child(depth=0):
        if depth > 1:
            # At max depth, only null or valid child with null child
            return st.one_of(st.none())
        else:
            # Generate a child record or null
            # To provoke divergence, sometimes omit a required field or put wrong type in child
            # But only one "wrong" thing per child to maximize divergence chance
            # We'll produce either:
            # - valid child record (all fields correct)
            # - child with one field missing (simulate missing required field)
            # - child with one field wrong type
            # - child null
            valid_child = gen_record(depth + 1)
            # Missing one required field: remove one key from JSON text later
            # Wrong type: replace one field with wrong type
            # We'll encode these as dicts here, then serialize later

            # To do this, we generate a dict with a "mode" to decide how to corrupt
            mode = draw(st.sampled_from(["valid", "missing_field", "wrong_type", "null"]))

            if mode == "null":
                return st.just(None)
            elif mode == "valid":
                return valid_child
            else:
                # Start from valid child dict (as dict, not JSON string)
                base = draw(valid_child)

                # Pick one field to corrupt or remove
                corrupt_field = draw(st.sampled_from(["id", "amount", "name", "status", "tags", "child"]))

                if mode == "missing_field":
                    # Remove the field (simulate missing required field)
                    base.pop(corrupt_field, None)
                    return st.just(base)
                else:
                    # wrong_type: replace field with wrong type
                    # For each field, define a wrong type value
                    wrong_values = {
                        "id": "string_instead_of_int",
                        "amount": 12345,
                        "name": 12345,
                        "status": "not_a_status",
                        "tags": "not_an_array",
                        "child": 12345,
                    }
                    base[corrupt_field] = wrong_values[corrupt_field]
                    return st.just(base)

    # Generate a full record dict (not JSON string yet)
    def gen_record(depth=0):
        # id: int
        id_ = draw(st.integers(min_value=0, max_value=10**9))
        # amount: string decimal
        amount = draw(
            st.one_of(
                st.decimals(min_value=0, max_value=10**9, places=2).map(lambda d: format(d, "f")),
                st.integers(min_value=0, max_value=10**9).map(str),
            )
        )
        # name: string or null
        name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=20)))
        # status: mostly valid, sometimes invalid
        status = draw(
            st.one_of(
                st.sampled_from(allowed_status),
                st.sampled_from(["active ", "inactive ", "enabled", "unknownn"]),
                st.none(),
            )
        )
        # tags: mostly valid array of strings, sometimes invalid element
        tags_valid = st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5)
        tags_invalid_element = st.one_of(st.integers(), st.none())
        tags = draw(
            st.one_of(
                tags_valid,
                st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=4).flatmap(
                    lambda good_list: st.tuples(
                        st.just(good_list),
                        tags_invalid_element,
                        st.integers(min_value=0, max_value=len(good_list)),
                    )
                ).map(
                    lambda tpl: tpl[0][:tpl[2]] + [tpl[1]] + tpl[0][tpl[2]:]
                ),
            )
        )
        # child: null or record or corrupted record
        child = draw(gen_child(depth))

        # Compose dict
        rec = {
            "id": id_,
            "amount": amount,
            "name": name,
            "status": status,
            "tags": tags,
            "child": child,
        }
        return rec

    # Generate top-level record dict
    record = draw(gen_record(depth=0))

    # Serialize dict to JSON string manually, with control over missing fields or wrong types
    # Because gen_record can produce dicts missing fields or with wrong types in child,
    # we must handle that carefully.

    def serialize_value(v):
        if v is None:
            return "null"
        elif isinstance(v, bool):
            return "true" if v else "false"
        elif isinstance(v, int):
            return str(v)
        elif isinstance(v, float):
            # JSON floats must have decimal point
            s = format(v, "f")
            if "." not in s:
                s += ".0"
            return s
        elif isinstance(v, str):
            return json_string(v)
        elif isinstance(v, list):
            # list of strings or possibly invalid elements
            # Elements may be int or None (invalid), serialize accordingly
            elems = []
            for e in v:
                if isinstance(e, str):
                    elems.append(json_string(e))
                elif e is None:
                    elems.append("null")
                elif isinstance(e, int):
                    elems.append(str(e))
                else:
                    # fallback to string
                    elems.append(json_string(str(e)))
            return "[" + ",".join(elems) + "]"
        elif isinstance(v, dict):
            # nested record
            return serialize_record(v)
        else:
            # fallback to string
            return json_string(str(v))

    def serialize_record(d):
        # d may be missing fields or have wrong types
        # We serialize only present keys in the order of schema fields
        fields = ["id", "amount", "name", "status", "tags", "child"]
        parts = []
        for f in fields:
            if f in d:
                parts.append(json_string(f) + ":" + serialize_value(d[f]))
            # else omit field (simulate missing required field)
        return "{" + ",".join(parts) + "}"

    json_text = serialize_record(record)
    return json_text.encode("utf-8")