from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper: produce a JSON string literal from a Python string,
    # escaping only backslash and double quote and control chars minimally.
    def json_string(s: str) -> str:
        # Minimal escaping for JSON string:
        # Replace \ with \\, " with \", and control chars with \u00XX
        def esc_char(c):
            o = ord(c)
            if c == '\\':
                return '\\\\'
            elif c == '"':
                return '\\"'
            elif 0 <= o <= 0x1F:
                return '\\u%04x' % o
            else:
                return c
        return '"' + ''.join(esc_char(c) for c in s) + '"'

    # id: integer or float with .0 to trigger manual rejection but others accept
    # We produce either an int or a float that is integral (like 1.0)
    id_is_float = draw(st.booleans())
    if id_is_float:
        # float with .0 fractional part
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_json = str(float(id_val))  # e.g. "1.0"
    else:
        id_val = draw(st.integers(min_value=0, max_value=1000))
        id_json = str(id_val)

    # amount: string normally, but try also int or float to cause manual rejection
    # or string that looks like a number to cause no rejection
    amount_type = draw(st.sampled_from(['string', 'int', 'float']))
    if amount_type == 'string':
        # string, possibly numeric-looking or normal
        amount_str = draw(st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)),
            st.just("123.45"),
            st.just("0"),
            st.just("1e10"),
        ))
        amount_json = json_string(amount_str)
    elif amount_type == 'int':
        amount_json = str(draw(st.integers(min_value=0, max_value=10000)))
    else:
        # float
        amount_json = str(draw(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)))

    # name: string or null or missing (built_value accepts missing)
    # We produce either null, string, or omit field (omit only for built_value)
    name_choice = draw(st.sampled_from(['string', 'null', 'omit']))
    if name_choice == 'string':
        name_val = draw(st.one_of(
            st.none().filter(lambda _: False),  # never
            st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))
        ))
        name_json = f'"name":{json_string(name_val)}'
        name_present = True
    elif name_choice == 'null':
        name_json = '"name":null'
        name_present = True
    else:
        # omit field entirely
        name_json = None
        name_present = False

    # status: one of "active", "inactive", "unknown" or invalid string to cause manual raw ArgumentError
    # or missing (should reject all)
    # We produce either valid enum string or invalid string or missing
    status_choice = draw(st.sampled_from(['valid', 'invalid', 'missing']))
    if status_choice == 'valid':
        status_val = draw(st.sampled_from(["active", "inactive", "unknown"]))
        status_json = f'"status":{json_string(status_val)}'
        status_present = True
    elif status_choice == 'invalid':
        # invalid enum string to cause manual raw ArgumentError, others throw CheckedFromJsonException or BuiltValueNestedFieldError
        # Use a string not in enum
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in {"active","inactive","unknown"} and all(32 <= ord(c) <= 126 for c in s)))
        status_json = f'"status":{json_string(invalid_status)}'
        status_present = True
    else:
        # missing field
        status_json = None
        status_present = False

    # tags: array of strings normally, but try arrays with non-string elements to cause built_value rejection or manual rejection
    # or empty array, or missing (should reject all)
    tags_choice = draw(st.sampled_from(['all_strings', 'some_nonstring', 'empty', 'missing']))
    if tags_choice == 'all_strings':
        # array of strings (possibly empty)
        tags_list = draw(st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), max_size=5))
        tags_json = '[' + ','.join(json_string(t) for t in tags_list) + ']'
        tags_present = True
    elif tags_choice == 'some_nonstring':
        # array with at least one non-string element
        # non-string elements: int, float, null, bool
        nonstring_elem = draw(st.one_of(
            st.integers(min_value=0, max_value=10).map(str),
            st.floats(min_value=0, max_value=10, allow_nan=False, allow_infinity=False).map(lambda f: repr(f)),
            st.just('null'),
            st.sampled_from(['true', 'false']),
        ))
        # at least one string element
        string_elem = json_string(draw(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))))
        # build list with one non-string and one string, shuffled
        if draw(st.booleans()):
            tags_json = '[' + nonstring_elem + ',' + string_elem + ']'
        else:
            tags_json = '[' + string_elem + ',' + nonstring_elem + ']'
        tags_present = True
    elif tags_choice == 'empty':
        tags_json = '[]'
        tags_present = True
    else:
        tags_json = None
        tags_present = False

    # child: null, nested record, or missing (built_value rejects missing child if non-nullable)
    # We produce either null, or a nested record with one level recursion, or omit
    child_choice = draw(st.sampled_from(['null', 'nested', 'missing']))
    if child_choice == 'null':
        child_json = '"child":null'
        child_present = True
    elif child_choice == 'nested':
        # nested record: reuse this strategy but limit recursion depth to 1
        # To avoid infinite recursion, produce a nested record with no child (child:null)
        # We produce a minimal nested record with all fields present and valid
        # id: int
        nid = draw(st.integers(min_value=0, max_value=1000))
        namount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)))
        nname = draw(st.one_of(st.none(), st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))))
        nstatus = draw(st.sampled_from(["active", "inactive", "unknown"]))
        ntags = draw(st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), max_size=3))
        # child=null for nested
        nested_fields = [
            f'"id":{nid}',
            f'"amount":{json_string(namount)}',
            f'"name":' + ('null' if nname is None else json_string(nname)),
            f'"status":{json_string(nstatus)}',
            f'"tags":[' + ','.join(json_string(t) for t in ntags) + ']',
            '"child":null'
        ]
        child_json = '"child":{' + ','.join(nested_fields) + '}'
        child_present = True
    else:
        child_json = None
        child_present = False

    # Compose top-level fields, always include id and amount (required)
    # Include name, status, tags, child if present
    fields = [f'"id":{id_json}', f'"amount":{amount_json}']
    if name_present:
        fields.append(name_json)
    if status_present:
        fields.append(status_json)
    if tags_present:
        fields.append(f'"tags":{tags_json}')
    if child_present:
        fields.append(child_json)

    json_text = '{' + ','.join(fields) + '}'
    return json_text.encode('utf-8')