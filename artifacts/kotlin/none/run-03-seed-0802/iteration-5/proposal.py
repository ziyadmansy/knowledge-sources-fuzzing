from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslashes only (minimal)
def json_string_escape(s: str) -> str:
    # Escape backslash and double quote only, minimal for test purposes
    return s.replace("\\", "\\\\").replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    # We produce JSON text representing the record schema:
    # {
    #   "id": <integer>,
    #   "amount": <string>,
    #   "name": <string or null>,
    #   "status": <one of "active", "inactive", "unknown">,
    #   "tags": <array of strings>,
    #   "child": <Record or null, one level recursion>
    # }
    #
    # Strategy hint: produce mostly well-formed documents with 1-2 fields slightly off:
    # - wrong type (e.g. number instead of string)
    # - missing field (omit field)
    # - null where string expected or vice versa
    # - enum field with invalid string or null
    # - tags array with some non-string element
    # - child null or a record (one level recursion only)
    #
    # We do bounded recursion: child is either null or a record with child=null.
    #
    # We vary only 1 or 2 fields off well-formed to maximize divergence.
    #
    # We build JSON text by string concatenation.

    # Constants
    statuses = ["active", "inactive", "unknown"]
    # Probability to produce a field with a type error or missing
    p_off = 0.3
    # Probability to produce null for nullable fields
    p_null = 0.2

    # Recursive function to produce a record JSON text
    def record_json(depth=0):
        # id: integer (always present)
        # amount: string (always present)
        # name: string or null (always present)
        # status: enum string (always present)
        # tags: array of strings (always present)
        # child: record or null (always present)

        # Decide which fields to "off" (wrong type or missing)
        # Pick 0,1 or 2 fields to be off, but never more than 2
        fields = ["id", "amount", "name", "status", "tags", "child"]
        off_count = draw(st.integers(min_value=0, max_value=2))
        off_fields = draw(st.sampled_from(fields).flatmap(
            lambda f: st.just(f)
        )).filter(lambda f: True)  # dummy to satisfy API, will override below

        # Actually pick off_fields as a set of size off_count
        off_fields = set(draw(st.sampled_from(fields).flatmap(
            lambda f: st.just(f)
        ) for _ in range(off_count)))
        # Above is incorrect usage, fix:
        off_fields = set(draw(st.lists(st.sampled_from(fields), min_size=off_count, max_size=off_count, unique=True)))

        # id field
        if "id" in off_fields:
            # Off: either missing or wrong type (string or null)
            id_choice = draw(st.sampled_from(["missing", "string", "null"]))
            if id_choice == "missing":
                id_json = None
            elif id_choice == "string":
                id_json = '"' + json_string_escape(draw(st.text(min_size=1, max_size=5))) + '"'
            else:  # null
                id_json = "null"
        else:
            # Well formed integer id
            id_json = str(draw(st.integers(min_value=0, max_value=10000)))

        # amount field (string)
        if "amount" in off_fields:
            # Off: missing or number or null
            amount_choice = draw(st.sampled_from(["missing", "number", "null"]))
            if amount_choice == "missing":
                amount_json = None
            elif amount_choice == "number":
                amount_json = str(draw(st.floats(allow_nan=False, allow_infinity=False, width=32)))
            else:
                amount_json = "null"
        else:
            # Well formed string amount, numeric-ish string or random string
            amount_str = draw(st.one_of(
                st.text(min_size=1, max_size=10, alphabet="0123456789.-"),
                st.just("0"),
                st.just("123.45"),
                st.text(min_size=1, max_size=10)
            ))
            amount_json = '"' + json_string_escape(amount_str) + '"'

        # name field (string or null)
        if "name" in off_fields:
            # Off: missing or number or boolean
            name_choice = draw(st.sampled_from(["missing", "number", "bool"]))
            if name_choice == "missing":
                name_json = None
            elif name_choice == "number":
                name_json = str(draw(st.integers(min_value=-1000, max_value=1000)))
            else:
                name_json = "true" if draw(st.booleans()) else "false"
        else:
            # Well formed string or null
            if draw(st.booleans()):
                name_str = draw(st.text(min_size=0, max_size=10))
                name_json = '"' + json_string_escape(name_str) + '"'
            else:
                name_json = "null"

        # status field (enum string)
        if "status" in off_fields:
            # Off: missing or invalid string or null
            status_choice = draw(st.sampled_from(["missing", "invalid_string", "null"]))
            if status_choice == "missing":
                status_json = None
            elif status_choice == "invalid_string":
                # invalid string not in enum
                invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses))
                status_json = '"' + json_string_escape(invalid_status) + '"'
            else:
                status_json = "null"
        else:
            status_json = '"' + draw(st.sampled_from(statuses)) + '"'

        # tags field (array of strings)
        if "tags" in off_fields:
            # Off: missing or array with some non-string element or null
            tags_choice = draw(st.sampled_from(["missing", "mixed_array", "null"]))
            if tags_choice == "missing":
                tags_json = None
            elif tags_choice == "null":
                tags_json = "null"
            else:
                # mixed array: mostly strings but one element is number or bool or null
                length = draw(st.integers(min_value=1, max_value=5))
                # position of bad element
                bad_pos = draw(st.integers(min_value=0, max_value=length - 1))
                elems = []
                for i in range(length):
                    if i == bad_pos:
                        bad_type = draw(st.sampled_from(["number", "bool", "null"]))
                        if bad_type == "number":
                            elems.append(str(draw(st.integers(min_value=-100, max_value=100))))
                        elif bad_type == "bool":
                            elems.append("true" if draw(st.booleans()) else "false")
                        else:
                            elems.append("null")
                    else:
                        s = draw(st.text(min_size=0, max_size=10))
                        elems.append('"' + json_string_escape(s) + '"')
                tags_json = "[" + ",".join(elems) + "]"
        else:
            # Well formed array of strings (possibly empty)
            length = draw(st.integers(min_value=0, max_value=5))
            elems = []
            for _ in range(length):
                s = draw(st.text(min_size=0, max_size=10))
                elems.append('"' + json_string_escape(s) + '"')
            tags_json = "[" + ",".join(elems) + "]"

        # child field (record or null)
        if depth == 0:
            # At top level, child can be null or a record (depth=1)
            if "child" in off_fields:
                # Off: missing or wrong type (string, number, bool)
                child_choice = draw(st.sampled_from(["missing", "string", "number", "bool"]))
                if child_choice == "missing":
                    child_json = None
                elif child_choice == "string":
                    child_json = '"' + json_string_escape(draw(st.text(min_size=1, max_size=10))) + '"'
                elif child_choice == "number":
                    child_json = str(draw(st.integers(min_value=-1000, max_value=1000)))
                else:
                    child_json = "true" if draw(st.booleans()) else "false"
            else:
                # Well formed child: either null or record with child=null
                if draw(st.booleans()):
                    child_json = "null"
                else:
                    child_json = record_json(depth=1)
        else:
            # depth=1: child must be null (no further recursion)
            child_json = "null"

        # Build JSON object text, skipping missing fields
        fields_json = []
        if id_json is not None:
            fields_json.append('"id":' + id_json)
        if amount_json is not None:
            fields_json.append('"amount":' + amount_json)
        if name_json is not None:
            fields_json.append('"name":' + name_json)
        if status_json is not None:
            fields_json.append('"status":' + status_json)
        if tags_json is not None:
            fields_json.append('"tags":' + tags_json)
        if child_json is not None:
            fields_json.append('"child":' + child_json)

        return "{" + ",".join(fields_json) + "}"

    json_text = record_json(depth=0)
    return json_text.encode("utf-8")