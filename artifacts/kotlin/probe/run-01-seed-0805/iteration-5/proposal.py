from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars)
def json_string(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping for test
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings
def json_array_of_strings(lst):
    return '[' + ','.join(json_string(x) for x in lst) + ']'

# Helper: JSON enum for status, with possibility of invalid string for fuzzing
status_valid = st.sampled_from(["active", "inactive", "unknown"])
status_invalid = st.text(min_size=1, max_size=10).filter(lambda x: x not in {"active","inactive","unknown"})
status_field = st.one_of(status_valid, status_invalid)

# Helper: JSON number as string or number
def json_number_or_string(n: int, allow_string: bool):
    if allow_string:
        # 50% chance string or number
        return st.one_of(st.just(str(n)), st.just(str(n)))
    else:
        return st.just(str(n))

# Helper: JSON value for "amount" field, per known behavior:
# Gson, Moshi, Jackson accept string or number (converted to string)
# kotlinx rejects number
# To maximize divergence, sometimes produce number, sometimes string
amount_value = st.one_of(
    st.text(min_size=1, max_size=10).filter(lambda s: s.isdigit()),  # string digits
    st.integers(min_value=0, max_value=10**6).map(str)  # numeric string
)

# Helper: "name" field can be string, null, or number (converted to string)
# Gson, Moshi accept string or number; kotlinx rejects number; Jackson accepts number converted to string
# To maximize divergence, sometimes produce number, sometimes string, sometimes null
name_value = st.one_of(
    st.none(),
    st.text(min_size=1, max_size=10),
    st.integers(min_value=0, max_value=10**6).map(str)
)

# Helper: "tags" array elements: strings or numbers (converted to strings)
# Gson, Moshi, Jackson accept numbers (Moshi rejects booleans); kotlinx rejects non-string elements
# To maximize divergence, sometimes produce numbers in array, sometimes strings
tags_element = st.one_of(
    st.text(min_size=1, max_size=10),
    st.integers(min_value=0, max_value=100).map(str)
)

# Helper: "child" field: null or nested record (one level recursion)
# Empty object {} accepted only by Gson, rejected by others
# Missing fields inside child cause rejection by Moshi, kotlinx, Jackson; Gson fills with defaults
# To maximize divergence, sometimes produce empty object {}, sometimes full child, sometimes null
# Limit recursion depth to 1

@st.composite
def record(draw, allow_empty_object=False):
    # id: integer or string convertible to integer
    id_val = draw(st.one_of(st.integers(min_value=0, max_value=10**6), st.text(min_size=1, max_size=10).filter(lambda s: s.isdigit())))
    id_json = json_string(str(id_val)) if isinstance(id_val, str) else str(id_val)

    # amount: string or number (string digits or numeric string)
    # To maximize divergence, sometimes number, sometimes string
    amount_is_number = draw(st.booleans())
    if amount_is_number:
        amount_val = draw(st.integers(min_value=0, max_value=10**6))
        amount_json = str(amount_val)
    else:
        amount_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: s.isdigit()))
        amount_json = json_string(amount_val)

    # name: string, null, or number (converted to string)
    name_choice = draw(st.one_of(
        st.none(),
        st.text(min_size=1, max_size=10),
        st.integers(min_value=0, max_value=10**6)
    ))
    if name_choice is None:
        name_json = "null"
    elif isinstance(name_choice, int):
        # number as number or string? To maximize divergence, produce number as number (no quotes)
        # Gson and Moshi accept number converted to string, kotlinx rejects number, Jackson accepts number converted to string
        # So produce number as number (no quotes)
        name_json = str(name_choice)
    else:
        name_json = json_string(name_choice)

    # status: exact enum strings or invalid strings
    status_val = draw(status_field)
    status_json = json_string(status_val)

    # tags: array of strings or numbers (converted to strings)
    # To maximize divergence, sometimes produce numbers, sometimes strings
    tags_len = draw(st.integers(min_value=0, max_value=5))
    tags_list = []
    for _ in range(tags_len):
        # 50% chance string or number string
        tag_is_number = draw(st.booleans())
        if tag_is_number:
            tag_val = draw(st.integers(min_value=0, max_value=100))
            tags_list.append(str(tag_val))
        else:
            tag_val = draw(st.text(min_size=1, max_size=10))
            tags_list.append(tag_val)
    tags_json = json_array_of_strings(tags_list)

    # child: null, empty object {}, or nested record (one level recursion)
    child_choice = draw(st.one_of(
        st.none(),
        st.just({}),  # empty object
        st.just("nested")
    ))
    if child_choice is None:
        child_json = "null"
    elif child_choice == {}:
        # empty object
        child_json = "{}"
    else:
        # nested record, no empty object allowed inside nested (to avoid deep recursion)
        nested = draw(record(allow_empty_object=False))
        child_json = nested

    # Compose JSON object string
    # Fields: id, amount, name, status, tags, child
    json_fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
        '"child":' + child_json
    ]
    json_obj = "{" + ",".join(json_fields) + "}"
    return json_obj

@st.composite
def generated_json(draw) -> bytes:
    # Generate a record JSON string
    # To maximize divergence, sometimes produce empty object {} as child, sometimes nested, sometimes null
    # Also sometimes produce invalid status strings, sometimes numbers in name, sometimes amount as number or string
    # Use record() helper with allow_empty_object=True for top-level child only
    rec = draw(record(allow_empty_object=True))
    return rec.encode("utf-8")