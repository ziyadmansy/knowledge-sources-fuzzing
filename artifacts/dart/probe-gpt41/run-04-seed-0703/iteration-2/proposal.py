from hypothesis import strategies as st

# Constants for fixed sets
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

# Helper to produce a JSON string literal from a Python string (no escapes needed here, just simple ASCII)
def json_string(s: str) -> str:
    # We only generate ASCII letters/digits/spaces, so no escapes needed
    # But we must quote and escape backslash and quote if any (we won't generate those)
    # To be safe, replace backslash and quote with escaped versions
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + s + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Produce syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to trigger behavioral divergence between four Dart JSON deserializers.
    """

    # Strategy for "id": integer only (no floats or strings)
    # We will sometimes produce valid int, sometimes invalid type (string or float) to trigger rejection
    # But per hint, vary only one or two fields at a time, so mostly valid with one off.
    # To do that, we will produce a "field fault" selector to pick which field to fault and how.
    # Fields: id, amount, name, status, tags, child
    # Fault types: missing, wrong type, null where not allowed, invalid enum, null where allowed, etc.

    # We want to produce mostly well-formed documents with one subtle fault or variation.

    # Define fault categories:
    # 0 = no fault (fully valid)
    # 1 = id wrong type (string or float)
    # 2 = amount wrong type (number or null)
    # 3 = name missing or wrong type (number)
    # 4 = status invalid value or null
    # 5 = tags missing or null (null only accepted by built_value)
    # 6 = tags with non-string element
    # 7 = child missing required field or wrong type inside child
    # 8 = child null (allowed)
    # 9 = extra field present (ignored by all, no divergence)
    # 10 = multiple faults (avoid, per hint)

    # We'll pick fault in [0..8] to keep one fault at a time.

    fault = draw(st.integers(min_value=0, max_value=8))

    # id field
    if fault == 1:
        # id wrong type: string or float
        id_val = draw(st.one_of(
            st.floats(allow_infinity=False, allow_nan=False).map(lambda f: f if f.is_integer() else f),
            st.text(min_size=1, max_size=5)
        ))
        # We must produce JSON text for id field:
        if isinstance(id_val, float):
            # JSON number (float)
            id_json = str(id_val)
        elif isinstance(id_val, str):
            id_json = json_string(id_val)
        else:
            # fallback, int
            id_json = str(int(id_val))
    else:
        # valid id: integer
        id_val = draw(st.integers(min_value=0, max_value=1000000))
        id_json = str(id_val)

    # amount field: string always, but fault=2 produce number or null
    if fault == 2:
        amount_val = draw(st.one_of(
            st.floats(allow_infinity=False, allow_nan=False).map(lambda f: str(f)),
            st.just("null")
        ))
        if amount_val == "null":
            amount_json = "null"
        else:
            amount_json = amount_val
    else:
        # valid amount: string representing a decimal number, e.g. "123.45"
        # generate a string of digits with optional decimal point
        integral = draw(st.integers(min_value=0, max_value=1000000))
        fractional = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=99)))
        if fractional is None:
            amount_str = str(integral)
        else:
            amount_str = f"{integral}.{fractional:02d}"
        amount_json = json_string(amount_str)

    # name field: string or null, fault=3 produce missing or wrong type (number)
    if fault == 3:
        # choose missing or wrong type
        name_fault_type = draw(st.sampled_from(["missing", "wrong_type"]))
        if name_fault_type == "missing":
            name_json = None  # omit field
        else:
            # wrong type: number
            name_json = str(draw(st.integers(min_value=0, max_value=1000)))
    else:
        # valid name: string or null
        name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        if name_val is None:
            name_json = "null"
        else:
            name_json = json_string(name_val)

    # status field: one of "active", "inactive", "unknown"
    # fault=4 produce null or invalid string or empty string
    if fault == 4:
        status_val = draw(st.one_of(
            st.just("null"),
            st.text(min_size=0, max_size=10).filter(lambda s: s not in ["active", "inactive", "unknown"])
        ))
        if status_val == "null":
            status_json = "null"
        else:
            status_json = json_string(status_val)
    else:
        status_json = draw(st.sampled_from(STATUS_VALUES))

    # tags field: array of strings, fault=5 missing or null, fault=6 non-string element
    if fault == 5:
        # missing or null
        tags_fault_type = draw(st.sampled_from(["missing", "null"]))
        if tags_fault_type == "missing":
            tags_json = None  # omit field
        else:
            tags_json = "null"
    elif fault == 6:
        # tags array with at least one non-string element
        # build array with mostly strings and one non-string (number or null or object)
        n_tags = draw(st.integers(min_value=1, max_value=5))
        # positions of non-string element
        non_string_pos = draw(st.integers(min_value=0, max_value=n_tags - 1))
        tags_elems = []
        for i in range(n_tags):
            if i == non_string_pos:
                # non-string element
                non_str = draw(st.one_of(
                    st.integers(min_value=0, max_value=1000).map(str),
                    st.just("null"),
                    st.just("123.45"),  # number as string, but we want actual number, so no quotes
                ))
                # Actually, we want JSON number or null or object, not string
                # So produce JSON number or null literal
                non_str_json = draw(st.one_of(
                    st.integers(min_value=0, max_value=1000).map(str),
                    st.just("null"),
                    st.just("123.45")
                ))
                tags_elems.append(non_str_json)
            else:
                # string element
                s = draw(st.text(min_size=0, max_size=10))
                tags_elems.append(json_string(s))
        tags_json = "[" + ",".join(tags_elems) + "]"
    else:
        # valid tags: array of strings (possibly empty)
        n_tags = draw(st.integers(min_value=0, max_value=5))
        tags_elems = [json_string(draw(st.text(min_size=0, max_size=10))) for _ in range(n_tags)]
        tags_json = "[" + ",".join(tags_elems) + "]"

    # child field: either null or a nested record (one level only)
    # fault=7 produce child with missing required field or wrong type inside child
    # fault=8 produce child null
    # else valid child or null

    def gen_child_record(fault_in_child):
        # fault_in_child: None or one of the fault codes 1..6 for child fields
        # We reuse the same logic but restrict recursion to one level only
        # For child, we do not recurse further (child.child is always null or omitted)
        # We'll produce a JSON object string for child

        # id in child
        if fault_in_child == 1:
            id_val_c = draw(st.one_of(
                st.floats(allow_infinity=False, allow_nan=False).map(lambda f: f if f.is_integer() else f),
                st.text(min_size=1, max_size=5)
            ))
            if isinstance(id_val_c, float):
                id_json_c = str(id_val_c)
            elif isinstance(id_val_c, str):
                id_json_c = json_string(id_val_c)
            else:
                id_json_c = str(int(id_val_c))
        else:
            id_val_c = draw(st.integers(min_value=0, max_value=1000000))
            id_json_c = str(id_val_c)

        # amount in child
        if fault_in_child == 2:
            amount_val_c = draw(st.one_of(
                st.floats(allow_infinity=False, allow_nan=False).map(lambda f: str(f)),
                st.just("null")
            ))
            if amount_val_c == "null":
                amount_json_c = "null"
            else:
                amount_json_c = amount_val_c
        else:
            integral_c = draw(st.integers(min_value=0, max_value=1000000))
            fractional_c = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=99)))
            if fractional_c is None:
                amount_str_c = str(integral_c)
            else:
                amount_str_c = f"{integral_c}.{fractional_c:02d}"
            amount_json_c = json_string(amount_str_c)

        # name in child
        if fault_in_child == 3:
            name_fault_type_c = draw(st.sampled_from(["missing", "wrong_type"]))
            if name_fault_type_c == "missing":
                name_json_c = None
            else:
                name_json_c = str(draw(st.integers(min_value=0, max_value=1000)))
        else:
            name_val_c = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
            if name_val_c is None:
                name_json_c = "null"
            else:
                name_json_c = json_string(name_val_c)

        # status in child
        if fault_in_child == 4:
            status_val_c = draw(st.one_of(
                st.just("null"),
                st.text(min_size=0, max_size=10).filter(lambda s: s not in ["active", "inactive", "unknown"])
            ))
            if status_val_c == "null":
                status_json_c = "null"
            else:
                status_json_c = json_string(status_val_c)
        else:
            status_json_c = draw(st.sampled_from(STATUS_VALUES))

        # tags in child
        if fault_in_child == 5:
            tags_fault_type_c = draw(st.sampled_from(["missing", "null"]))
            if tags_fault_type_c == "missing":
                tags_json_c = None
            else:
                tags_json_c = "null"
        elif fault_in_child == 6:
            n_tags_c = draw(st.integers(min_value=1, max_value=5))
            non_string_pos_c = draw(st.integers(min_value=0, max_value=n_tags_c - 1))
            tags_elems_c = []
            for i in range(n_tags_c):
                if i == non_string_pos_c:
                    non_str_json_c = draw(st.one_of(
                        st.integers(min_value=0, max_value=1000).map(str),
                        st.just("null"),
                        st.just("123.45")
                    ))
                    tags_elems_c.append(non_str_json_c)
                else:
                    s_c = draw(st.text(min_size=0, max_size=10))
                    tags_elems_c.append(json_string(s_c))
            tags_json_c = "[" + ",".join(tags_elems_c) + "]"
        else:
            n_tags_c = draw(st.integers(min_value=0, max_value=5))
            tags_elems_c = [json_string(draw(st.text(min_size=0, max_size=10))) for _ in range(n_tags_c)]
            tags_json_c = "[" + ",".join(tags_elems_c) + "]"

        # child.child is always null (no recursion)
        child_child_json = "null"

        # Compose child fields as JSON key:value pairs
        fields = []

        fields.append('"id":' + id_json_c)
        fields.append('"amount":' + amount_json_c)
        if name_json_c is not None:
            fields.append('"name":' + name_json_c)
        fields.append('"status":' + status_json_c)
        if tags_json_c is not None:
            fields.append('"tags":' + tags_json_c)
        fields.append('"child":' + child_child_json)

        return "{" + ",".join(fields) + "}"

    if fault == 7:
        # child with one fault inside
        # pick one fault for child fields from 1..6 (excluding 7,8 to avoid recursion)
        fault_in_child = draw(st.integers(min_value=1, max_value=6))
        child_json = gen_child_record(fault_in_child)
    elif fault == 8:
        # child null
        child_json = "null"
    else:
        # valid child or null
        # 50% chance null, 50% chance valid child with no fault
        if draw(st.booleans()):
            child_json = "null"
        else:
            child_json = gen_child_record(None)

    # Compose top-level fields as JSON key:value pairs
    fields = []

    fields.append('"id":' + id_json)
    fields.append('"amount":' + amount_json)
    if name_json is not None:
        fields.append('"name":' + name_json)
    fields.append('"status":' + status_json)
    if tags_json is not None:
        fields.append('"tags":' + tags_json)
    fields.append('"child":' + child_json)

    # Compose JSON object string
    json_obj = "{" + ",".join(fields) + "}"

    # Return bytes
    return json_obj.encode("utf-8")