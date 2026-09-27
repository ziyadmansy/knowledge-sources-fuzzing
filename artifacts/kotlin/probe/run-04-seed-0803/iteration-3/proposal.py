from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and fields
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # Also include some invalid enum values to trigger divergence
    STATUS_INVALIDS = ['"invalid"', 'null', '123', '{}']

    # Helper: produce a JSON string literal with proper escaping for simple ASCII only
    # (Hypothesis strings are unicode, but we restrict to ascii for simplicity)
    def json_string(s: str) -> str:
        # Escape backslash and quote only (minimal)
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    # Helper: produce a JSON array of strings, allowing some coercion cases
    # We want to sometimes produce integers inside string arrays (known divergence)
    # or wrong types (should cause rejection by all)
    @st.composite
    def tags_array(draw):
        # Decide if normal string array or with int coercion or wrong type
        kind = draw(st.sampled_from(['strings', 'ints_in_strings', 'wrong_type']))
        if kind == 'strings':
            strs = draw(st.lists(st.text(min_size=1, max_size=10).filter(lambda x: all(32 <= ord(c) <= 126 and c not in '"\\' for c in x)), min_size=0, max_size=5))
            arr = '[' + ','.join(json_string(s) for s in strs) + ']'
            return arr
        elif kind == 'ints_in_strings':
            # mix of strings and ints (ints coerced to strings by Gson, Moshi, Jackson; rejected by kotlinx)
            elems = []
            n = draw(st.integers(min_value=0, max_value=5))
            for _ in range(n):
                if draw(st.booleans()):
                    # string element
                    s = draw(st.text(min_size=1, max_size=10).filter(lambda x: all(32 <= ord(c) <= 126 and c not in '"\\' for c in x)))
                    elems.append(json_string(s))
                else:
                    # int element
                    i = draw(st.integers(min_value=-1000, max_value=1000))
                    elems.append(str(i))
            return '[' + ','.join(elems) + ']'
        else:
            # wrong type: produce a string instead of array
            s = draw(st.text(min_size=1, max_size=10).filter(lambda x: all(32 <= ord(c) <= 126 and c not in '"\\' for c in x)))
            return json_string(s)

    # Helper: produce "amount" field value, which is string normally,
    # but known divergence on numeric values accepted by Gson/Moshi/Jackson but rejected by kotlinx
    @st.composite
    def amount_field(draw):
        kind = draw(st.sampled_from(['string', 'number', 'empty_string']))
        if kind == 'string':
            s = draw(st.text(min_size=1, max_size=10).filter(lambda x: all(32 <= ord(c) <= 126 and c not in '"\\' for c in x)))
            return json_string(s)
        elif kind == 'number':
            # integer or float number as JSON number (not string)
            if draw(st.booleans()):
                n = draw(st.integers(min_value=-100000, max_value=100000))
                return str(n)
            else:
                f = draw(st.floats(min_value=-1e5, max_value=1e5, allow_nan=False, allow_infinity=False))
                # format float with minimal decimal places
                return repr(f)
        else:
            # empty string (edge case)
            return '""'

    # Helper: produce "id" field value, which is integer but known to accept string integers too
    @st.composite
    def id_field(draw):
        kind = draw(st.sampled_from(['int', 'string_int']))
        n = draw(st.integers(min_value=0, max_value=1000000))
        if kind == 'int':
            return str(n)
        else:
            return json_string(str(n))

    # Helper: produce "name" field value, string or null
    @st.composite
    def name_field(draw):
        kind = draw(st.sampled_from(['string', 'null']))
        if kind == 'string':
            s = draw(st.text(min_size=0, max_size=10).filter(lambda x: all(32 <= ord(c) <= 126 and c not in '"\\' for c in x)))
            return json_string(s)
        else:
            return 'null'

    # Helper: produce "status" field value, enum or invalid or null
    @st.composite
    def status_field(draw):
        kind = draw(st.sampled_from(['valid_enum', 'invalid_enum', 'null']))
        if kind == 'valid_enum':
            return draw(st.sampled_from(STATUS_VALUES))
        elif kind == 'invalid_enum':
            return draw(st.sampled_from(STATUS_INVALIDS))
        else:
            return 'null'

    # Helper: produce "child" field value, which is either null or a nested record (one level only)
    # Known divergence: Gson accepts empty object for nullable child, others reject
    # Also test missing fields inside child (should reject except Gson)
    @st.composite
    def child_field(draw, depth=0):
        # Limit recursion depth to 1 (only one nested level)
        kind = draw(st.sampled_from(['null', 'full_record', 'empty_object', 'partial_record']))
        if kind == 'null':
            return 'null'
        elif kind == 'empty_object':
            # "{}" accepted only by Gson
            return '{}'
        elif kind == 'partial_record':
            # produce object with some fields missing (only for child)
            # Gson fills missing fields with defaults/nulls, others reject
            # We produce a partial record JSON text with 1-5 fields present
            fields = ['id', 'amount', 'name', 'status', 'tags', 'child']
            present = draw(st.lists(st.sampled_from(fields), min_size=1, max_size=5, unique=True))
            parts = []
            for f in present:
                if f == 'id':
                    parts.append('"id":' + draw(id_field()))
                elif f == 'amount':
                    parts.append('"amount":' + draw(amount_field()))
                elif f == 'name':
                    parts.append('"name":' + draw(name_field()))
                elif f == 'status':
                    parts.append('"status":' + draw(status_field()))
                elif f == 'tags':
                    parts.append('"tags":' + draw(tags_array()))
                elif f == 'child':
                    # For nested child inside child, always null to avoid deep recursion
                    parts.append('"child":null')
            return '{' + ','.join(parts) + '}'
        else:
            # full record nested child, only one level deep
            # recurse once with depth+1 but limit to null child inside
            parts = [
                '"id":' + draw(id_field()),
                '"amount":' + draw(amount_field()),
                '"name":' + draw(name_field()),
                '"status":' + draw(status_field()),
                '"tags":' + draw(tags_array()),
                '"child":null'
            ]
            return '{' + ','.join(parts) + '}'

    # Compose the root record JSON text
    parts = [
        '"id":' + draw(id_field()),
        '"amount":' + draw(amount_field()),
        '"name":' + draw(name_field()),
        '"status":' + draw(status_field()),
        '"tags":' + draw(tags_array()),
        '"child":' + draw(child_field())
    ]

    # Occasionally add an extra unknown field at root or inside child to trigger divergence
    # Gson and Moshi accept extra fields, kotlinx and Jackson reject
    add_extra = draw(st.booleans())
    if add_extra:
        # Add extra field at root or inside child (if child is object)
        where = draw(st.sampled_from(['root', 'child']))
        extra_field = '"extra_field":123'
        if where == 'root':
            parts.append(extra_field)
        else:
            # If child is object (not null or empty object), insert extra field inside child
            # Parse child JSON text to check if object
            child_json = parts[-1]
            if child_json.startswith('{') and child_json != 'null' and child_json != '{}':
                # Insert extra field inside child object before closing }
                # child_json is like {...}, insert before last }
                child_json = child_json[:-1] + ',' + extra_field + '}'
                parts[-1] = child_json
            else:
                # fallback: add extra field at root
                parts.append(extra_field)

    json_text = '{' + ','.join(parts) + '}'
    return json_text.encode('utf-8')