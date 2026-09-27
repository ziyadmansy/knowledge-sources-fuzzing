from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string
    # Minimal escaping: backslash and quote
    def json_string(s: str) -> str:
        # Escape backslash and double quote
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control characters minimally (newline, tab)
        s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return '"' + s + '"'

    # Helper: produce a JSON array of strings
    def json_array_of_strings(lst):
        return "[" + ",".join(json_string(x) for x in lst) + "]"

    # Recursive record generator with bounded depth
    # We produce a JSON text string representing the record
    def record_json(depth=0):
        # To encourage divergence, we produce mostly well-formed fields,
        # but with a small chance to tweak one or two fields to "almost correct" but off-type or missing.

        # Base well-formed fields:
        # id: integer
        # amount: string
        # name: string or null
        # status: one of "active", "inactive", "unknown"
        # tags: array of strings
        # child: record or null (one level recursion max)

        # Strategy for id: mostly integer, sometimes string or float or missing
        id_val = draw(st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            st.text(min_size=1, max_size=5).map(json_string),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: repr(f)),
            st.just("null"),
            st.just("true"),
            st.just("false"),
        ))

        # Strategy for amount: mostly string decimal, sometimes number, sometimes null, sometimes missing
        # We'll produce a string decimal normally, but sometimes a number literal or null or boolean
        amount_val = draw(st.one_of(
            st.decimals(min_value=0, max_value=1e9, places=2).map(lambda d: json_string(format(d, 'f'))),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: repr(f)),
            st.just("null"),
            st.just("true"),
            st.just("false"),
            st.text(min_size=1, max_size=5).map(json_string),
        ))

        # Strategy for name: string or null or missing or number or boolean
        name_val = draw(st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=1000).map(str),
            st.just("true"),
            st.just("false"),
        ))

        # Strategy for status: mostly valid enum string, sometimes invalid string, sometimes null, sometimes number
        status_val = draw(st.one_of(
            st.sampled_from(statuses).map(json_string),
            st.text(min_size=1, max_size=7).filter(lambda s: s not in statuses).map(json_string),
            st.just("null"),
            st.integers(min_value=0, max_value=10).map(str),
        ))

        # Strategy for tags: mostly array of strings, sometimes array of numbers, sometimes null, sometimes empty array
        # We'll produce arrays of 0-3 elements
        tags_list = draw(st.lists(st.one_of(
            st.text(min_size=1, max_size=5),
            st.integers(min_value=0, max_value=100).map(str),
            st.just("true"),
            st.just("false"),
        ), min_size=0, max_size=3))
        # Convert to JSON array string, escaping strings properly
        def tag_to_json(t):
            if t in ("true", "false") or t.isdigit():
                # number or boolean literal
                return t
            else:
                return json_string(t)
        tags_val = "[" + ",".join(tag_to_json(t) for t in tags_list) + "]"

        # Strategy for child: null or nested record (only one level deep)
        if depth >= 1:
            # At max depth, only null
            child_val = "null"
        else:
            # 50% chance null, 50% chance nested record
            if draw(st.booleans()):
                child_val = "null"
            else:
                child_val = record_json(depth + 1)

        # Now decide if we omit one field to create divergence (missing field)
        # Or if we tweak one field to an off-type or borderline value
        # We pick one or two fields to "corrupt" or omit

        fields = {
            "id": id_val,
            "amount": amount_val,
            "name": name_val,
            "status": status_val,
            "tags": tags_val,
            "child": child_val,
        }

        # Pick 0,1 or 2 fields to corrupt or omit
        corrupt_count = draw(st.integers(min_value=0, max_value=2))
        corrupt_fields = draw(st.lists(st.sampled_from(list(fields.keys())), min_size=corrupt_count, max_size=corrupt_count, unique=True))

        # For each corrupt field, either omit or replace with a different type or invalid value
        for f in corrupt_fields:
            choice = draw(st.sampled_from(["omit", "wrong_type", "boundary"]))
            if choice == "omit":
                # Remove field
                del fields[f]
            elif choice == "wrong_type":
                # Replace with a different type value
                if f == "id":
                    # Replace with string literal (if not already), or boolean literal
                    fields[f] = draw(st.one_of(
                        st.text(min_size=1, max_size=5).map(json_string),
                        st.just("true"),
                        st.just("false"),
                        st.just("null"),
                    ))
                elif f == "amount":
                    # Replace with number literal or boolean or null
                    fields[f] = draw(st.one_of(
                        st.integers(min_value=0, max_value=1000).map(str),
                        st.just("true"),
                        st.just("false"),
                        st.just("null"),
                    ))
                elif f == "name":
                    # Replace with number or boolean or null
                    fields[f] = draw(st.one_of(
                        st.integers(min_value=0, max_value=1000).map(str),
                        st.just("true"),
                        st.just("false"),
                        st.just("null"),
                    ))
                elif f == "status":
                    # Replace with invalid string or number or null
                    fields[f] = draw(st.one_of(
                        st.text(min_size=1, max_size=7).filter(lambda s: s not in statuses).map(json_string),
                        st.integers(min_value=0, max_value=10).map(str),
                        st.just("null"),
                    ))
                elif f == "tags":
                    # Replace with non-array: string, number, boolean, null
                    fields[f] = draw(st.one_of(
                        st.text(min_size=1, max_size=5).map(json_string),
                        st.integers(min_value=0, max_value=100).map(str),
                        st.just("true"),
                        st.just("false"),
                        st.just("null"),
                    ))
                elif f == "child":
                    # Replace with non-object non-null: string, number, boolean
                    fields[f] = draw(st.one_of(
                        st.text(min_size=1, max_size=5).map(json_string),
                        st.integers(min_value=0, max_value=100).map(str),
                        st.just("true"),
                        st.just("false"),
                    ))
            elif choice == "boundary":
                # Put borderline values that might cause divergence
                if f == "id":
                    # Large integer as string or float notation
                    fields[f] = draw(st.one_of(
                        st.just(str(2**31)),  # just above int32 max
                        st.just(json_string(str(2**31))),  # string of large number
                        st.just("0"),  # zero as string
                    ))
                elif f == "amount":
                    # Empty string, or very large decimal string
                    fields[f] = draw(st.one_of(
                        st.just(json_string("")),
                        st.just(json_string("999999999999999999999.99")),
                        st.just("0"),
                    ))
                elif f == "name":
                    # Empty string or very long string
                    fields[f] = draw(st.one_of(
                        st.just(json_string("")),
                        st.just(json_string("a"*100)),
                        st.just("null"),
                    ))
                elif f == "status":
                    # Valid enum but uppercase or mixed case (should be invalid)
                    fields[f] = draw(st.one_of(
                        st.just(json_string("Active")),
                        st.just(json_string("INACTIVE")),
                        st.just(json_string("unknown")),
                    ))
                elif f == "tags":
                    # Empty array or array with empty string
                    fields[f] = draw(st.one_of(
                        st.just("[]"),
                        st.just('[""]'),
                        st.just('["tag1",""]'),
                    ))
                elif f == "child":
                    # null or empty object or object missing fields
                    fields[f] = draw(st.one_of(
                        st.just("null"),
                        st.just("{}"),
                        # Object with only id field
                        st.just('{"id":1}'),
                    ))

        # Compose JSON object string from fields
        # Fields order fixed for consistency
        keys_order = ["id", "amount", "name", "status", "tags", "child"]
        items = []
        for k in keys_order:
            if k in fields:
                items.append(json_string(k) + ":" + fields[k])
        json_obj = "{" + ",".join(items) + "}"

        return json_obj.encode("utf-8")

    return record_json()