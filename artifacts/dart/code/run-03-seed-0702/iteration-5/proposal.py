from hypothesis import strategies as st

# Helper: JSON string escaping (minimal, only for ", \, and control chars)
def json_string_escape(s: str) -> str:
    # Escape backslash and double quote and control chars \b\f\n\r\t
    # Hypothesis strings are unicode, so also escape control chars <0x20
    def esc_char(c):
        o = ord(c)
        if c == '"':
            return '\\"'
        if c == '\\':
            return '\\\\'
        if c == '\b':
            return '\\b'
        if c == '\f':
            return '\\f'
        if c == '\n':
            return '\\n'
        if c == '\r':
            return '\\r'
        if c == '\t':
            return '\\t'
        if o < 0x20:
            return '\\u%04x' % o
        return c
    return ''.join(esc_char(c) for c in s)

# Compose JSON string literal from Python string
def json_string(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

# Compose JSON array of strings from Python list[str]
def json_array_of_strings(lst) -> str:
    # lst is list of strings
    return '[' + ','.join(json_string(s) for s in lst) + ']'

# Compose JSON null or nested record string
# We'll do bounded recursion with max depth 1 (child can be null or record with child=null)
# To avoid infinite recursion, pass depth param
def json_record(draw, depth=0):
    # id: integer or float 1.0 (to trigger manual rejection)
    # amount: string or number (to trigger manual rejection)
    # name: string or null or missing (built_value accepts missing)
    # status: one of enum strings or unknown string (to trigger enum errors)
    # tags: list of strings or list with one non-string element (to trigger tag errors)
    # child: null or nested record (depth limited to 1)
    # We'll vary one or two fields off well-formed to maximize divergence

    # id: mostly int, sometimes float 1.0 (accepted by codegen, rejected by manual)
    id_choice = draw(st.one_of(
        st.integers(min_value=0, max_value=1000),
        st.just(1.0),  # float 1.0 triggers manual rejection
    ))

    # amount: mostly string, sometimes number (to trigger manual rejection)
    amount_choice = draw(st.one_of(
        st.text(min_size=1, max_size=10),
        st.integers(min_value=0, max_value=1000),
        st.floats(allow_infinity=False, allow_nan=False),
    ))

    # name: string or null or missing (built_value accepts missing)
    # We'll encode missing by omitting the field sometimes
    name_present = draw(st.booleans())
    if name_present:
        name_choice = draw(st.one_of(
            st.none(),
            st.text(min_size=0, max_size=10),
        ))
    else:
        name_choice = None  # means omit

    # status: mostly valid enum strings, sometimes unknown string (to trigger enum errors)
    status_choice = draw(st.one_of(
        st.sampled_from(["active", "inactive", "unknown"]),
        st.text(min_size=1, max_size=10).filter(lambda s: s not in {"active", "inactive", "unknown"}),
    ))

    # tags: mostly list of strings, sometimes list with one non-string element (int or null)
    tags_len = draw(st.integers(min_value=0, max_value=5))
    # Decide if tags are all strings or have one non-string element
    tags_all_strings = draw(st.booleans())
    if tags_all_strings:
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=tags_len, max_size=tags_len))
    else:
        # Insert one non-string element at random position if length > 0, else empty list
        if tags_len == 0:
            tags_list = []
        else:
            pos = draw(st.integers(min_value=0, max_value=tags_len - 1))
            strings_before = draw(st.lists(st.text(min_size=0, max_size=10), min_size=pos, max_size=pos))
            strings_after = draw(st.lists(st.text(min_size=0, max_size=10), min_size=tags_len - pos - 1, max_size=tags_len - pos - 1))
            non_string_elem = draw(st.one_of(st.integers(), st.none()))
            tags_list = strings_before + [non_string_elem] + strings_after

    # child: null or nested record (depth limited to 1)
    if depth >= 1:
        child_choice = None
    else:
        child_present = draw(st.booleans())
        if child_present:
            child_choice = json_record(draw, depth=depth + 1)
        else:
            child_choice = None

    # Compose JSON object string with fields in fixed order for consistency
    # id, amount, name (optional), status, tags, child

    parts = []

    # id field: emit as number (int or float)
    if isinstance(id_choice, int):
        parts.append('"id":' + str(id_choice))
    else:
        # float, emit with decimal point to distinguish from int
        parts.append('"id":' + repr(float(id_choice)))

    # amount field: emit as JSON string if string, else as number
    if isinstance(amount_choice, str):
        parts.append('"amount":' + json_string(amount_choice))
    elif isinstance(amount_choice, int):
        parts.append('"amount":' + str(amount_choice))
    else:
        # float
        parts.append('"amount":' + repr(float(amount_choice)))

    # name field: omit if name_choice is None and name_present is False
    if name_present:
        if name_choice is None:
            parts.append('"name":null')
        else:
            parts.append('"name":' + json_string(name_choice))

    # status field: always present, string
    parts.append('"status":' + json_string(status_choice))

    # tags field: array of strings or mixed
    # Compose JSON array manually, non-string elements must be valid JSON values (int or null)
    tags_json_elems = []
    for e in tags_list:
        if isinstance(e, str):
            tags_json_elems.append(json_string(e))
        elif e is None:
            tags_json_elems.append('null')
        elif isinstance(e, int):
            tags_json_elems.append(str(e))
        else:
            # fallback: emit as string forcibly (should not happen)
            tags_json_elems.append(json_string(str(e)))
    parts.append('"tags":[' + ','.join(tags_json_elems) + ']')

    # child field: null or nested record
    if child_choice is None:
        parts.append('"child":null')
    else:
        parts.append('"child":' + child_choice)

    return '{' + ','.join(parts) + '}'

@st.composite
def generated_json(draw) -> bytes:
    # Generate a JSON object string with bounded recursion and controlled malformations
    s = json_record(draw, depth=0)
    return s.encode('utf-8')