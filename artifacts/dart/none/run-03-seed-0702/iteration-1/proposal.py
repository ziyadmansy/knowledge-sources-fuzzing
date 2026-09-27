from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper: generate a JSON string literal with proper escaping for " and \
    # We'll keep escaping minimal for simplicity, only " and \ are escaped
    def json_string(s: str) -> str:
        # Escape backslash and double quote
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'

    # Helper: generate JSON array of strings
    def json_array_of_strings(lst):
        # lst is list of strings
        return "[" + ",".join(json_string(x) for x in lst) + "]"

    # Recursive generator for the "child" field, bounded to one level of recursion
    # We produce either null or a record object (with no further recursion)
    @st.composite
    def child_record(draw):
        # To induce divergence, we vary one or two fields off from spec:
        # - id: integer (always)
        # - amount: string (always)
        # - name: string or null
        # - status: one of statuses
        # - tags: array of strings
        # - child: null only here (no deeper recursion)
        #
        # We produce mostly valid fields, but with small chance to produce:
        # - wrong type for one field (e.g. amount as number)
        # - missing field (should not happen in well-formed, but we do it rarely)
        # - null where string expected or vice versa
        # - status as string but not in enum (to test enum parsing)
        # - tags as array but with non-string elements
        # - child as something other than null (should be null here)
        #
        # But only one or two such deviations per record to maximize divergence chances.

        # Decide how many deviations: 0 or 1 or 2
        deviations = draw(st.integers(min_value=0, max_value=2))

        # Field generators with possible deviations
        # id: integer, deviation: string or float instead of int
        if deviations > 0 and draw(st.booleans()):
            id_val = draw(st.one_of(st.text(min_size=1, max_size=5), st.floats(allow_nan=False, allow_infinity=False)))
            deviations -= 1
        else:
            id_val = draw(st.integers(min_value=0, max_value=10**9))

        # amount: string, deviation: number or null
        if deviations > 0 and draw(st.booleans()):
            amount_val = draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.just(None)))
            deviations -= 1
        else:
            # amount string: numeric string or arbitrary string
            amount_val = draw(st.one_of(
                st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in ".-" for c in s)),
                st.text(min_size=1, max_size=10)
            ))

        # name: string or null, deviation: number or boolean instead of string/null
        if deviations > 0 and draw(st.booleans()):
            name_val = draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.booleans()))
            deviations -= 1
        else:
            name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))

        # status: one of statuses, deviation: string not in enum or number
        if deviations > 0 and draw(st.booleans()):
            status_val = draw(st.one_of(
                st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses),
                st.integers()
            ))
            deviations -= 1
        else:
            status_val = draw(st.sampled_from(statuses))

        # tags: array of strings, deviation: array with non-string elements or null
        if deviations > 0 and draw(st.booleans()):
            # array with mixed types or null
            if draw(st.booleans()):
                tags_val = draw(st.none())
            else:
                # array with some non-string elements
                length = draw(st.integers(min_value=0, max_value=5))
                elems = []
                for _ in range(length):
                    if draw(st.booleans()):
                        elems.append(draw(st.text(min_size=0, max_size=5)))
                    else:
                        elems.append(draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.none(), st.booleans())))
                tags_val = elems
            deviations -= 1
        else:
            length = draw(st.integers(min_value=0, max_value=5))
            tags_val = [draw(st.text(min_size=0, max_size=5)) for _ in range(length)]

        # child: normally null here, deviation: object or wrong type
        if deviations > 0 and draw(st.booleans()):
            # child as wrong type or object with missing fields
            if draw(st.booleans()):
                # child as a string or number
                child_val = draw(st.one_of(st.text(min_size=1, max_size=5), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.booleans()))
            else:
                # child as object missing some fields or with wrong types
                # For simplicity, produce empty object or object with one wrong field
                if draw(st.booleans()):
                    child_val = {}
                else:
                    child_val = {"id": draw(st.text(min_size=1, max_size=5))}
            deviations -= 1
        else:
            child_val = None

        # Now serialize fields to JSON text
        def serialize_value(v):
            if v is None:
                return "null"
            elif isinstance(v, str):
                return json_string(v)
            elif isinstance(v, bool):
                return "true" if v else "false"
            elif isinstance(v, int):
                return str(v)
            elif isinstance(v, float):
                # JSON floats must be finite
                if v != v or v == float("inf") or v == float("-inf"):
                    return "null"
                else:
                    # Use repr to preserve decimal point if any
                    return repr(v)
            elif isinstance(v, list):
                # array
                return "[" + ",".join(serialize_value(x) for x in v) + "]"
            elif isinstance(v, dict):
                # object
                items = []
                for k, val in v.items():
                    items.append(json_string(k) + ":" + serialize_value(val))
                return "{" + ",".join(items) + "}"
            else:
                # fallback to string
                return json_string(str(v))

        obj = (
            "{" +
            '"id":' + serialize_value(id_val) + "," +
            '"amount":' + serialize_value(amount_val) + "," +
            '"name":' + serialize_value(name_val) + "," +
            '"status":' + serialize_value(status_val) + "," +
            '"tags":' + serialize_value(tags_val) + "," +
            '"child":' + serialize_value(child_val) +
            "}"
        )
        return obj

    # Top-level record, similar to child_record but with one level recursion for child
    # We produce a record with child either null or a child_record (no deeper recursion)
    # We apply the same deviation logic but only 1 or 2 deviations total per top-level record

    deviations = draw(st.integers(min_value=0, max_value=2))

    # id
    if deviations > 0 and draw(st.booleans()):
        id_val = draw(st.one_of(st.text(min_size=1, max_size=5), st.floats(allow_nan=False, allow_infinity=False)))
        deviations -= 1
    else:
        id_val = draw(st.integers(min_value=0, max_value=10**9))

    # amount
    if deviations > 0 and draw(st.booleans()):
        amount_val = draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.just(None)))
        deviations -= 1
    else:
        amount_val = draw(st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in ".-" for c in s)),
            st.text(min_size=1, max_size=10)
        ))

    # name
    if deviations > 0 and draw(st.booleans()):
        name_val = draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.booleans()))
        deviations -= 1
    else:
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))

    # status
    if deviations > 0 and draw(st.booleans()):
        status_val = draw(st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses),
            st.integers()
        ))
        deviations -= 1
    else:
        status_val = draw(st.sampled_from(statuses))

    # tags
    if deviations > 0 and draw(st.booleans()):
        if draw(st.booleans()):
            tags_val = draw(st.none())
        else:
            length = draw(st.integers(min_value=0, max_value=5))
            elems = []
            for _ in range(length):
                if draw(st.booleans()):
                    elems.append(draw(st.text(min_size=0, max_size=5)))
                else:
                    elems.append(draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.none(), st.booleans())))
            tags_val = elems
        deviations -= 1
    else:
        length = draw(st.integers(min_value=0, max_value=5))
        tags_val = [draw(st.text(min_size=0, max_size=5)) for _ in range(length)]

    # child: null or child_record
    if deviations > 0 and draw(st.booleans()):
        # child as wrong type or object with missing fields
        if draw(st.booleans()):
            if draw(st.booleans()):
                child_val = draw(st.one_of(st.text(min_size=1, max_size=5), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.booleans()))
            else:
                if draw(st.booleans()):
                    child_val = {}
                else:
                    child_val = {"id": draw(st.text(min_size=1, max_size=5))}
        else:
            child_val = None
        deviations -= 1
    else:
        # valid child record or null
        if draw(st.booleans()):
            child_val = None
        else:
            child_val = draw(child_record())

    # Serialize top-level record
    def serialize_value(v):
        if v is None:
            return "null"
        elif isinstance(v, str):
            s = v.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{s}"'
        elif isinstance(v, bool):
            return "true" if v else "false"
        elif isinstance(v, int):
            return str(v)
        elif isinstance(v, float):
            if v != v or v == float("inf") or v == float("-inf"):
                return "null"
            else:
                return repr(v)
        elif isinstance(v, list):
            return "[" + ",".join(serialize_value(x) for x in v) + "]"
        elif isinstance(v, dict):
            items = []
            for k, val in v.items():
                items.append(serialize_value(k) + ":" + serialize_value(val))
            return "{" + ",".join(items) + "}"
        else:
            return serialize_value(str(v))

    obj = (
        "{" +
        '"id":' + serialize_value(id_val) + "," +
        '"amount":' + serialize_value(amount_val) + "," +
        '"name":' + serialize_value(name_val) + "," +
        '"status":' + serialize_value(status_val) + "," +
        '"tags":' + serialize_value(tags_val) + "," +
        '"child":' + serialize_value(child_val) +
        "}"
    )
    return obj.encode("utf-8")