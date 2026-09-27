from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum status
    statuses = ["active", "inactive", "unknown"]
    # We allow one "almost valid" enum string to trigger manual vs others divergence:
    # e.g. a valid enum plus one invalid string close to valid (typo or case difference)
    enum_almost_valid = st.one_of(
        st.sampled_from(statuses),
        st.just("Active"),  # case difference, manual rejects, others reject differently
        st.just("inactiv"), # typo, manual throws raw ArgumentError, others CheckedFromJsonException
        st.just("unknown "), # trailing space
    )

    # id field: manual requires int exactly, others accept float like 1.0
    # So generate int or float with .0 to trigger divergence
    id_int = st.integers(min_value=0, max_value=1000)
    id_float = st.floats(min_value=0, max_value=1000, allow_infinity=False, allow_nan=False).filter(lambda f: f.is_integer())
    id_choice = st.one_of(
        id_int,
        id_float.map(lambda f: float(int(f)))  # float with .0 fractional part
    )

    # amount: manual requires string exactly, others same
    # To trigger divergence, try string or int (int will cause manual reject)
    amount_str = st.text(min_size=1, max_size=10)
    amount_choice = st.one_of(
        amount_str,
        st.integers(min_value=0, max_value=1000).map(str),  # stringified int, safe
        st.integers(min_value=0, max_value=1000),  # int, manual rejects
    )

    # name: nullable string or null
    # built_value accepts missing or null, manual/json_serializable/freezed accept null explicitly
    # To trigger divergence, sometimes omit name field or set to null or string
    name_value = st.one_of(
        st.none(),
        st.text(min_size=1, max_size=10),
    )
    # We'll decide later if to omit or include name

    # tags: list of strings normally
    # To trigger divergence, try list of strings, list with one non-string, or empty list
    tag_str = st.text(min_size=1, max_size=5)
    tags_valid = st.lists(tag_str, min_size=0, max_size=5)
    tags_invalid = st.lists(st.one_of(tag_str, st.integers()), min_size=1, max_size=5).filter(lambda lst: any(not isinstance(x, str) for x in lst))
    tags_choice = st.one_of(tags_valid, tags_invalid)

    # child: null or nested record (one level recursion)
    # To keep bounded recursion, child can be null or a record with no child (child=null)
    # To trigger divergence, child can be malformed (e.g. missing fields or wrong types)
    # We'll generate child as either null or a record with all fields valid except one small divergence

    # Helper to build a record JSON string from fields (all fields present)
    def build_record_json(id_val, amount_val, name_val_opt, status_val, tags_val, child_val_opt):
        # id_val: int or float or int (as int or float literal)
        # amount_val: string or int (if int, emit as number)
        # name_val_opt: None means omit field, else string or null
        # status_val: string
        # tags_val: list of strings or mixed
        # child_val_opt: None means null, else JSON string of child record

        # id field
        if isinstance(id_val, int):
            id_str = str(id_val)
        else:
            # float with .0 fractional part, emit with decimal point
            id_str = f"{id_val:.1f}"

        # amount field
        if isinstance(amount_val, str):
            amount_str = '"' + amount_val.replace('"', '\\"') + '"'
        else:
            # int, emit as number (not string)
            amount_str = str(amount_val)

        # name field
        if name_val_opt is None:
            name_str = None  # omit field
        elif name_val_opt is None:
            name_str = '"name":null'
        else:
            # string or null
            if name_val_opt is None:
                name_str = '"name":null'
            else:
                name_str = '"name":"' + name_val_opt.replace('"', '\\"') + '"'

        # status field
        status_str = '"' + status_val + '"'

        # tags field
        # tags_val is list, elements can be strings or ints (to trigger divergence)
        tags_elems = []
        for t in tags_val:
            if isinstance(t, str):
                tags_elems.append('"' + t.replace('"', '\\"') + '"')
            else:
                # int or other type, emit as number
                tags_elems.append(str(t))
        tags_str = "[" + ",".join(tags_elems) + "]"

        # child field
        if child_val_opt is None:
            child_str = "null"
        else:
            child_str = child_val_opt

        # Compose fields in order: id, amount, name (optional), status, tags, child
        fields = []
        fields.append('"id":' + id_str)
        fields.append('"amount":' + amount_str)
        if name_str is not None:
            fields.append(name_str)
        fields.append('"status":' + status_str)
        fields.append('"tags":' + tags_str)
        fields.append('"child":' + child_str)

        return "{" + ",".join(fields) + "}"

    # Compose child record (one level, child.child always null)
    def gen_child_record():
        # child record fields mostly valid, but we can inject one divergence in child:
        # e.g. id as float vs int, status almost valid enum, tags with one non-string, etc.
        id_c = draw(id_choice)
        amount_c = draw(amount_choice)
        name_c = draw(name_value)
        status_c = draw(enum_almost_valid)
        tags_c = draw(tags_choice)
        # child.child is always null to keep bounded recursion
        child_c = None
        # name field: sometimes omit to trigger built_value difference
        omit_name_c = draw(st.booleans())
        name_c_opt = None if omit_name_c else name_c

        return build_record_json(id_c, amount_c, name_c_opt, status_c, tags_c, child_c)

    # Now draw top-level fields
    id_v = draw(id_choice)
    amount_v = draw(amount_choice)
    name_v = draw(name_value)
    omit_name = draw(st.booleans())
    name_opt = None if omit_name else name_v
    status_v = draw(enum_almost_valid)
    tags_v = draw(tags_choice)
    # child: null or nested record
    child_present = draw(st.booleans())
    if child_present:
        child_v = gen_child_record()
    else:
        child_v = None

    json_str = build_record_json(id_v, amount_v, name_opt, status_v, tags_v, child_v)
    return json_str.encode("utf-8")