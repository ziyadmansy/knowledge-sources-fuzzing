from hypothesis import strategies as st

# Helper: JSON string escaping for simple ASCII subset (no control chars, no unicode escapes)
# We generate strings from a safe subset of chars to avoid complex escaping.
_json_string_chars = st.characters(
    whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs'),
    blacklist_characters='"\\'
).filter(lambda c: c not in '\b\f\n\r\t')

_json_string = st.text(_json_string_chars, min_size=0, max_size=10).map(
    lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
)

# JSON null literal
_json_null = st.just("null")

# JSON boolean literals (not used in schema but useful for malformed probes)
_json_bool = st.sampled_from(["true", "false"])

# JSON number as string (no leading zeros except zero itself)
_json_int_str = st.integers(min_value=0, max_value=1000).map(str)

# JSON number as number text (no leading zeros except zero itself)
def int_to_json_number(n: int) -> str:
    return str(n)

_json_int = st.integers(min_value=0, max_value=1000).map(int_to_json_number)

# JSON enum values for "status"
_status_values = ["\"active\"", "\"inactive\"", "\"unknown\""]

# Known enum values as strings (quoted)
_json_status_known = st.sampled_from(_status_values)

# Unknown enum values (quoted strings not in known set)
_json_status_unknown = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8
).filter(lambda s: f'"{s}"' not in _status_values).map(lambda s: f'"{s}"')

# Nullable enum: known values or null
_json_status_nullable = st.one_of(_json_status_known, _json_null)

# Tags array: array of strings (strings coerced from ints allowed by Gson, Moshi, Jackson)
# We will generate arrays with elements either strings or ints (as numbers)
# to trigger coercion differences.
def json_string_or_int_element():
    # 70% strings, 30% ints to explore coercion
    return st.one_of(
        _json_string,
        _json_int
    )

_json_tags_array = st.lists(json_string_or_int_element(), min_size=0, max_size=5).map(
    lambda elems: "[" + ",".join(elems) + "]"
)

# "name" field: string or null
_json_name = st.one_of(_json_string, _json_null)

# "amount" field: string normally, but known coercions:
# - Gson, Moshi, Jackson accept numeric JSON values coerced to string
# - kotlinx.serialization rejects numeric for string
# So we generate either string or number here.
_json_amount = st.one_of(_json_string, _json_int)

# "id" field: integer, but known coercion: integer as string accepted by all four
# So generate either integer number or integer as string
_json_id = st.one_of(_json_int, _json_int_str)

# "child" field: nullable Record or null or empty object (empty object accepted only by Gson)
# We limit recursion depth to 1 (one level of child)
# We generate either:
# - null
# - well-formed child record (depth=1)
# - empty object "{}" (to trigger Gson acceptance, others reject)
# - missing child field (handled outside)
def json_child(depth=0):
    if depth >= 1:
        # At max depth, only null or empty object or missing
        return st.one_of(
            _json_null,
            st.just("{}"),
        )
    else:
        # Compose a child record (depth=1)
        return generated_record(depth=depth + 1).map(lambda s: s)

# Compose a record JSON text, depth limited
def generated_record(depth=0):
    # Compose fields with possible variations to trigger divergences
    # We produce a dict of fieldname: json_value (string)
    # Then join with commas and braces

    # id field (int or string)
    id_field = _json_id.map(lambda v: '"id":' + v)

    # amount field (string or number)
    amount_field = _json_amount.map(lambda v: '"amount":' + v)

    # name field (string or null)
    name_field = _json_name.map(lambda v: '"name":' + v)

    # status field:
    # To maximize divergence, sometimes use unknown enum, sometimes null, sometimes known
    # We pick from known, unknown, null with weights to explore divergences
    status_field = st.one_of(
        _json_status_known,
        _json_status_unknown,
        _json_null
    ).map(lambda v: '"status":' + v)

    # tags field: array of strings or ints (to trigger coercion differences)
    tags_field = _json_tags_array.map(lambda v: '"tags":' + v)

    # child field: null, empty object, or nested record (depth limited)
    # Also sometimes omit child field to test missing field behavior
    child_field = st.one_of(
        _json_null,
        st.just("{}"),
        generated_record(depth=depth + 1),
    ).map(lambda v: '"child":' + v)

    # Compose fields into a dict, sometimes omit child field to test missing
    # We generate a dict of fields, then join with commas
    # To maximize divergence, sometimes omit child field (only 20% chance)
    def assemble(fields):
        id_f, amount_f, name_f, status_f, tags_f, child_f = fields
        # 20% omit child field
        import random
        omit_child = random.random() < 0.2
        parts = [id_f, amount_f, name_f, status_f, tags_f]
        if not omit_child:
            parts.append(child_f)
        return "{" + ",".join(parts) + "}"

    # Compose tuple of fields
    return st.tuples(id_field, amount_field, name_field, status_field, tags_field, child_field).map(assemble)

@st.composite
def generated_json(draw) -> bytes:
    # Generate a record JSON text with depth=0
    json_text = draw(generated_record(depth=0))
    # Return as bytes (UTF-8)
    return json_text.encode("utf-8")