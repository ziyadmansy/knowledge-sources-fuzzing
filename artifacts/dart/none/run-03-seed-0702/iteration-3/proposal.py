from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # To keep recursion bounded, pass depth parameter internally
    def record_strategy(depth: int) -> st.SearchStrategy[str]:
        # Base fields, mostly correct types but with small chance of subtle divergence:
        # - id: usually integer, sometimes stringified integer or float to cause divergence
        # - amount: string, but sometimes numeric string or numeric (to cause divergence)
        # - name: string or null, sometimes integer or boolean to cause divergence
        # - status: one of enum strings, sometimes invalid string or null
        # - tags: array of strings, sometimes empty array, sometimes array with non-string elements
        # - child: null or nested record (one level recursion max)

        # id field: mostly integer, sometimes stringified int, sometimes float string
        id_val = draw(
            st.one_of(
                st.integers(min_value=0, max_value=10**9).map(str),
                st.integers(min_value=0, max_value=10**9),
                st.floats(allow_infinity=False, allow_nan=False, width=32).map(lambda f: str(f)),
            )
        )
        # amount field: mostly string representing decimal number, sometimes numeric (int or float)
        amount_val = draw(
            st.one_of(
                st.decimals(min_value=0, max_value=10**9, places=2).map(lambda d: format(d, 'f')),
                st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789." for c in s)),
                st.integers(min_value=0, max_value=10**9),
                st.floats(allow_infinity=False, allow_nan=False).map(lambda f: str(f)),
            )
        )
        # name field: string or null normally, sometimes integer or boolean to cause divergence
        name_val = draw(
            st.one_of(
                st.none(),
                st.text(min_size=0, max_size=20),
                st.integers(min_value=-1000, max_value=1000),
                st.booleans(),
            )
        )
        # status field: mostly valid enum string, sometimes invalid string or null
        status_val = draw(
            st.one_of(
                st.sampled_from(statuses),
                st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses),
                st.none(),
            )
        )
        # tags field: array of strings, sometimes empty, sometimes with non-string elements
        tags_val = draw(
            st.lists(
                st.one_of(
                    st.text(min_size=0, max_size=10),
                    st.integers(min_value=-10, max_value=10),
                    st.booleans(),
                ),
                min_size=0,
                max_size=5,
            )
        )
        # child field: null or nested record (one level max)
        if depth <= 0:
            child_val = "null"
        else:
            # 50% chance null, 50% chance nested record
            if draw(st.booleans()):
                child_val = "null"
            else:
                child_val = draw(record_strategy(depth - 1))

        # Build JSON string for this record:
        # id: if id_val is int, emit as number, else as string with quotes
        if isinstance(id_val, int):
            id_str = str(id_val)
        else:
            # id_val is string (could be float string or int string)
            # We emit as JSON string with quotes
            id_str = '"' + id_val.replace('"', '\\"') + '"'

        # amount: if amount_val is int or float, emit as number, else string with quotes
        if isinstance(amount_val, (int, float)):
            amount_str = str(amount_val)
        else:
            amount_str = '"' + amount_val.replace('"', '\\"') + '"'

        # name: null, string, int, or bool
        if name_val is None:
            name_str = "null"
        elif isinstance(name_val, str):
            name_str = '"' + name_val.replace('"', '\\"') + '"'
        elif isinstance(name_val, bool):
            name_str = "true" if name_val else "false"
        else:
            # int
            name_str = str(name_val)

        # status: null or string
        if status_val is None:
            status_str = "null"
        else:
            status_str = '"' + status_val.replace('"', '\\"') + '"'

        # tags: array of mixed types, build JSON array string
        def json_value(v):
            if v is None:
                return "null"
            elif isinstance(v, str):
                return '"' + v.replace('"', '\\"') + '"'
            elif isinstance(v, bool):
                return "true" if v else "false"
            else:
                return str(v)

        tags_str = "[" + ",".join(json_value(t) for t in tags_val) + "]"

        # child_val is already JSON string or "null"
        child_str = child_val

        # Compose full JSON object string
        json_obj = (
            '{'
            + '"id":' + id_str + ','
            + '"amount":' + amount_str + ','
            + '"name":' + name_str + ','
            + '"status":' + status_str + ','
            + '"tags":' + tags_str + ','
            + '"child":' + child_str
            + '}'
        )
        return json_obj

    # Start recursion with depth 1 (one level child)
    result = draw(record_strategy(1))
    return result.encode("utf-8")