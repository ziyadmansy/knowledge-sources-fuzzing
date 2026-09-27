from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status values
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote minimally
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape control chars (newline, tab, etc) minimally
        s = s.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{s}"'

    # Helper: produce a JSON array of strings
    def json_array_of_strings(strings):
        return "[" + ",".join(json_string(s) for s in strings) + "]"

    # Recursive record generator with bounded depth
    def record(depth):
        # Base valid fields with mostly correct types
        # We will introduce exactly one or two subtle deviations to provoke divergence

        # id: integer normally, but sometimes string or float (to provoke type issues)
        id_val = draw(
            st.one_of(
                st.integers(min_value=0, max_value=2**31 - 1),
                st.text(min_size=1, max_size=5).filter(lambda x: not x.isdigit()),  # invalid string id
                st.floats(allow_nan=False, allow_infinity=False).map(lambda f: round(f, 2)),
            )
        )

        # amount: string normally, but sometimes number or null (null is invalid by schema)
        amount_val = draw(
            st.one_of(
                st.text(min_size=1, max_size=10),
                st.integers(min_value=0, max_value=10000).map(str),
                st.integers(min_value=0, max_value=10000),  # number instead of string
                st.just(None),  # null instead of string
            )
        )

        # name: string or null normally, but sometimes number or missing (missing is invalid)
        # We will sometimes omit the field or set it to number to provoke divergence
        name_choice = draw(st.integers(min_value=0, max_value=3))
        if name_choice == 0:
            # valid string or null
            name_val = draw(st.one_of(st.text(min_size=0, max_size=10), st.just(None)))
            name_present = True
        elif name_choice == 1:
            # number instead of string/null
            name_val = draw(st.integers(min_value=-1000, max_value=1000))
            name_present = True
        elif name_choice == 2:
            # omit field entirely
            name_val = None
            name_present = False
        else:
            # empty string (valid)
            name_val = ""
            name_present = True

        # status: one of the three strings normally, but sometimes invalid string or null
        status_val = draw(
            st.one_of(
                st.sampled_from(statuses),
                st.text(min_size=1, max_size=7).filter(lambda s: s not in statuses),
                st.just(None),
            )
        )

        # tags: array of strings normally, but sometimes array with non-string, or null, or empty
        tags_choice = draw(st.integers(min_value=0, max_value=3))
        if tags_choice == 0:
            tags_val = draw(st.lists(st.text(min_size=1, max_size=5), min_size=0, max_size=3))
        elif tags_choice == 1:
            # array with one non-string element
            tags_val = draw(
                st.lists(
                    st.one_of(
                        st.text(min_size=1, max_size=5),
                        st.integers(min_value=0, max_value=10),
                        st.just(None),
                    ),
                    min_size=1,
                    max_size=3,
                )
            )
        elif tags_choice == 2:
            tags_val = None  # null instead of array
        else:
            tags_val = []

        # child: either null or a nested record (one level max)
        # Sometimes omit child field or set to invalid types to provoke divergence
        child_choice = draw(st.integers(min_value=0, max_value=4))
        if child_choice == 0:
            child_val = None
            child_present = True
        elif child_choice == 1 and depth < 1:
            child_val = record(depth + 1)
            child_present = True
        elif child_choice == 2:
            # invalid type: string instead of record or null
            child_val = draw(st.text(min_size=1, max_size=10))
            child_present = True
        elif child_choice == 3:
            # omit child field
            child_val = None
            child_present = False
        else:
            # number instead of record or null
            child_val = draw(st.integers(min_value=0, max_value=1000))
            child_present = True

        # Build JSON text for this record

        fields = []

        # id field (always present)
        if isinstance(id_val, int):
            fields.append(f'"id":{id_val}')
        elif isinstance(id_val, float):
            # JSON numbers can be floats
            fields.append(f'"id":{id_val}')
        else:
            # string id
            fields.append(f'"id":{json_string(str(id_val))}')

        # amount field (always present)
        if amount_val is None:
            fields.append('"amount":null')
        elif isinstance(amount_val, int):
            fields.append(f'"amount":{amount_val}')
        else:
            # string
            fields.append(f'"amount":{json_string(str(amount_val))}')

        # name field (optional)
        if name_present:
            if name_val is None:
                fields.append('"name":null')
            elif isinstance(name_val, int):
                fields.append(f'"name":{name_val}')
            else:
                fields.append(f'"name":{json_string(str(name_val))}')
        # else omit name field

        # status field (always present)
        if status_val is None:
            fields.append('"status":null')
        else:
            fields.append(f'"status":{json_string(str(status_val))}')

        # tags field (always present)
        if tags_val is None:
            fields.append('"tags":null')
        elif isinstance(tags_val, list):
            # array of strings or mixed
            arr_elems = []
            for v in tags_val:
                if isinstance(v, str):
                    arr_elems.append(json_string(v))
                elif v is None:
                    arr_elems.append("null")
                else:
                    # number or other
                    arr_elems.append(str(v))
            fields.append(f'"tags":[{",".join(arr_elems)}]')
        else:
            # empty array
            fields.append('"tags":[]')

        # child field (optional)
        if child_present:
            if child_val is None:
                fields.append('"child":null')
            elif isinstance(child_val, str):
                fields.append(f'"child":{json_string(child_val)}')
            elif isinstance(child_val, int):
                fields.append(f'"child":{child_val}')
            else:
                # nested record string
                fields.append(f'"child":{child_val}')
        # else omit child field

        json_text = "{" + ",".join(fields) + "}"
        return json_text

    # Generate top-level record with depth 0
    json_obj_text = record(0)
    return json_obj_text.encode("utf-8")