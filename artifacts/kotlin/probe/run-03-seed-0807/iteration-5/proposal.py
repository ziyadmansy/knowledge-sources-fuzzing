from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars)
def json_string(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping for test
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: serialize JSON array of strings
def json_array_of_strings(arr):
    return "[" + ",".join(json_string(e) for e in arr) + "]"

# Helper: serialize JSON enum string (always quoted)
def json_enum(s):
    return json_string(s)

# Helper: serialize JSON null or string or number (as string)
def json_value(v):
    if v is None:
        return "null"
    if isinstance(v, str):
        return json_string(v)
    if isinstance(v, int):
        return str(v)
    raise ValueError("Unsupported json_value type")

# Compose a record JSON text from components (all fields present)
# id_val: int or str (number or string)
# amount_val: str or int or None (amount accepts string or number or null)
# name_val: str or int or None (name accepts string or number or null)
# status_val: str or None (enum or null)
# tags_val: list of str or list with null or non-string elements or None
# child_val: JSON text or None or empty object "{}"
def compose_record(
    id_val,
    amount_val,
    name_val,
    status_val,
    tags_val,
    child_val,
):
    parts = []
    # id: number or string
    if isinstance(id_val, int):
        parts.append('"id":' + str(id_val))
    else:
        parts.append('"id":' + json_string(id_val))
    # amount: string or number or null
    if amount_val is None:
        parts.append('"amount":null')
    elif isinstance(amount_val, int):
        parts.append('"amount":' + str(amount_val))
    else:
        parts.append('"amount":' + json_string(amount_val))
    # name: string or number or null
    if name_val is None:
        parts.append('"name":null')
    elif isinstance(name_val, int):
        parts.append('"name":' + str(name_val))
    else:
        parts.append('"name":' + json_string(name_val))
    # status: string or null or invalid string
    if status_val is None:
        parts.append('"status":null')
    else:
        parts.append('"status":' + json_string(status_val))
    # tags: array or null or invalid (not array)
    if tags_val is None:
        parts.append('"tags":null')
    elif isinstance(tags_val, str):
        # invalid: tags as string (not array)
        parts.append('"tags":' + json_string(tags_val))
    else:
        # tags_val is list (possibly empty)
        # elements can be string, null, or non-string (int)
        arr_elems = []
        for e in tags_val:
            if e is None:
                arr_elems.append("null")
            elif isinstance(e, int):
                arr_elems.append(str(e))
            else:
                arr_elems.append(json_string(e))
        parts.append('"tags":[' + ",".join(arr_elems) + "]")
    # child: JSON text or null
    if child_val is None:
        parts.append('"child":null')
    else:
        parts.append('"child":' + child_val)
    return "{" + ",".join(parts) + "}"

# Strategy for id: int or stringified int (known accepted by all)
id_strategy = st.one_of(
    st.integers(min_value=0, max_value=1000),
    st.integers(min_value=0, max_value=1000).map(str),
)

# Strategy for amount: string or int or null
# Known: kotlinx rejects number amount, others accept number or string
amount_strategy = st.one_of(
    st.text(min_size=1, max_size=10),  # string amount
    st.integers(min_value=0, max_value=10000),  # number amount
    st.none(),  # null amount (Gson accepts, others reject)
)

# Strategy for name: string or int or null
# Known: Gson, Moshi, Jackson accept string or number; kotlinx rejects non-string non-null
name_strategy = st.one_of(
    st.text(min_size=0, max_size=10),
    st.integers(min_value=-1000, max_value=1000),
    st.none(),
)

# Strategy for status: valid enum or invalid enum or null
# Known: Gson accepts invalid or null as null; others reject invalid or null
valid_status = st.sampled_from(["active", "inactive", "unknown"])
invalid_status = st.sampled_from(["enabled", "ACTIVE", "disabled", ""])
status_strategy = st.one_of(
    valid_status,
    invalid_status,
    st.none(),
)

# Strategy for tags:
# Known: all reject if not array
# Gson, Moshi, Jackson accept arrays with non-string elements or null; kotlinx rejects
# So tags can be:
# - valid array of strings
# - array with nulls
# - array with ints (non-string)
# - null (Gson accepts in child, others reject)
# - invalid: string instead of array
tags_valid_strings = st.lists(st.text(min_size=0, max_size=5), max_size=5)
tags_with_nulls = st.lists(st.one_of(st.text(min_size=0, max_size=5), st.none()), max_size=5)
tags_with_ints = st.lists(st.one_of(st.text(min_size=0, max_size=5), st.integers(min_value=-10, max_value=10), st.none()), max_size=5)
tags_invalid_string = st.text(min_size=1, max_size=10)

tags_strategy = st.one_of(
    tags_valid_strings,
    tags_with_nulls,
    tags_with_ints,
    st.none(),
    tags_invalid_string,
)

# Recursive child record strategy, bounded depth 1 (one level)
# child can be:
# - null
# - well-formed record (all fields present)
# - empty object "{}" (Gson accepts, others reject)
# - object missing required fields (not generated here to keep near well-formed)
def child_strategy():
    # To avoid infinite recursion, child record does not recurse further
    # Compose child record from components, but no nested child inside child (child=null)
    return st.deferred(lambda: record_strategy(depth=1))

# record_strategy with depth control
def record_strategy(depth=0):
    # At depth 1, child must be null or empty object or null child (to avoid deep recursion)
    if depth >= 1:
        child_val_strat = st.one_of(
            st.just("null"),
            st.just("{}"),
        )
    else:
        child_val_strat = st.one_of(
            st.just("null"),
            child_strategy(),
            st.just("{}"),
        )

    return st.tuples(
        id_strategy,
        amount_strategy,
        name_strategy,
        status_strategy,
        tags_strategy,
        child_val_strat,
    ).map(
        lambda tpl: compose_record(*tpl)
    )

@st.composite
def generated_json(draw) -> bytes:
    # Generate one record JSON text with near well-formed structure,
    # varying one or two fields to trigger divergences.
    # Compose record with depth 0 (child can recurse once)
    json_text = draw(record_strategy(depth=0))
    return json_text.encode("utf-8")