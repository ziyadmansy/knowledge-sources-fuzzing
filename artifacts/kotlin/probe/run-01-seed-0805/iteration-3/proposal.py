from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes, backslash, control chars minimally
def json_string_escape(s: str) -> str:
    # Minimal escaping for JSON string: backslash, double quote, control chars
    # Hypothesis strings are unicode, but we keep it simple here.
    # Replace backslash and double quote
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    # Replace control chars (U+0000 to U+001F) with \u00XX
    def esc_char(c):
        if ord(c) < 0x20:
            return '\\u%04x' % ord(c)
        return c
    return ''.join(esc_char(c) for c in s)

# Compose a JSON string literal from a Python string
def json_string(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

# Compose a JSON array of strings from a list of strings
def json_array_of_strings(lst) -> str:
    return '[' + ','.join(json_string(s) for s in lst) + ']'

# Compose a JSON object from a dict of key: json_value (already string)
def json_object(d: dict) -> str:
    # keys are always strings, no escaping needed for keys since fixed keys
    return '{' + ','.join(json_string(k) + ':' + v for k, v in d.items()) + '}'

# Compose a JSON number or string for "id"
# Known: id accepts integer or string convertible to integer
id_int = st.integers(min_value=0, max_value=2**31-1)
id_str = id_int.map(str)

# Compose "amount" as string or number
# Known: Gson, Moshi, Jackson accept string or number (converted to string)
#       kotlinx rejects number
# So we try to produce both forms to cause divergence
amount_str = st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))
# To increase chance of acceptance, restrict to ascii printable chars excluding quotes and backslash
amount_str = amount_str.filter(lambda s: all(c not in '"\\' for c in s))
amount_num = st.floats(allow_nan=False, allow_infinity=False, width=32).map(lambda f: ('%.6g' % f).rstrip('0').rstrip('.') if '.' in ('%.6g' % f) else ('%.6g' % f))
# amount_num is string of number, but we want raw number in JSON, so we keep it as string but output raw (no quotes)
# We'll generate amount as either string (quoted) or number (raw)

# Compose "name" as string, null, or number (converted to string by some)
# Known: Gson, Moshi accept string or number (converted to string)
#       kotlinx rejects number
#       Jackson accepts number converted to string
# Also null accepted by all
name_str = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s) and all(c not in '"\\' for c in s)),
    st.integers(min_value=-1000, max_value=1000),
    st.floats(allow_nan=False, allow_infinity=False, width=32)
)

# Compose "status" as enum string or invalid string
# Known: only exact enum strings accepted by Moshi, kotlinx, Jackson
#       Gson accepts invalid but decodes as null
status_enum = st.sampled_from(['active', 'inactive', 'unknown'])
status_invalid = st.text(min_size=1, max_size=10).filter(lambda s: s not in ['active', 'inactive', 'unknown'] and all(32 <= ord(c) <= 126 for c in s) and all(c not in '"\\' for c in s))
status = st.one_of(status_enum, status_invalid)

# Compose "tags" as array of strings or array with numbers or booleans
# Known: tags must be array; string instead rejected by all
#        elements must be strings or convertible
#        Gson, Moshi, Jackson accept numbers (Moshi rejects booleans)
#        kotlinx rejects non-string elements
tag_str = st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s) and all(c not in '"\\' for c in s))
tag_num = st.integers(min_value=-1000, max_value=1000).map(str)
tag_bool = st.booleans().map(lambda b: "true" if b else "false")
# Compose tags array with 0 to 3 elements, mixing strings and numbers and booleans to cause divergence
def tags_strategy():
    # Compose list of elements as strings or numbers or booleans (as raw JSON literals)
    # We produce JSON literals for elements, not Python values
    # We want to cause divergence by mixing types
    # Moshi rejects booleans, kotlinx rejects non-string elements
    # Gson accepts all
    # Jackson accepts numbers, rejects booleans?
    # We'll produce arrays with 0-3 elements, each element either string (quoted), number (raw), or boolean (raw)
    # To cause divergence, produce some with booleans, some with numbers, some with strings
    # We'll produce elements as JSON text literals
    def element():
        return st.one_of(
            tag_str.map(json_string),
            id_int.map(str),
            st.booleans().map(lambda b: "true" if b else "false")
        )
    return st.lists(element(), min_size=0, max_size=3).map(lambda lst: '[' + ','.join(lst) + ']')

# Compose "child" as null or nested Record (one level recursion)
# Known: child can be null or full Record
#        empty object {} accepted only by Gson (with defaults), rejected by others
#        missing fields inside child cause rejection by Moshi, kotlinx, Jackson; Gson fills with defaults
# We produce child as null or full record, or empty object to cause divergence
# Limit recursion depth to 1 (child's child is null)
# To keep generation simple, we produce child as null or full record or empty object

# Forward declaration for record_json
def record_json(depth=0):
    # depth 0 means top-level, depth 1 means child level, no further recursion
    # Compose fields:
    # "id": integer or string convertible to integer
    # "amount": string or number (stringified)
    # "name": string or null or number
    # "status": enum string or invalid string
    # "tags": array of strings or mixed types
    # "child": null or record (depth=1) or empty object (to cause divergence)
    # To cause divergence, vary one or two fields at a time from well-formed base

    # Compose id field: integer or string
    id_field = st.one_of(
        id_int.map(str),
        id_str.map(json_string)
    )

    # Compose amount field: string or number (raw)
    amount_field = st.one_of(
        amount_str.map(json_string),
        amount_num
    )

    # Compose name field: null, string, or number (int or float)
    def name_to_json(x):
        if x is None:
            return "null"
        elif isinstance(x, int):
            # number as raw number or string? Known: Gson, Moshi accept number converted to string; kotlinx rejects number; Jackson accepts number converted to string
            # To cause divergence, output number raw (no quotes)
            return str(x)
        elif isinstance(x, float):
            # float raw number
            return ('%.6g' % x).rstrip('0').rstrip('.') if '.' in ('%.6g' % x) else ('%.6g' % x)
        else:
            # string
            return json_string(x)
    name_field = name_str.map(name_to_json)

    # Compose status field: enum or invalid string
    def status_to_json(s):
        return json_string(s)
    status_field = status.map(status_to_json)

    # Compose tags field: array of strings or mixed types
    tags_field = tags_strategy()

    # Compose child field: null, empty object, or nested record (depth=1 max)
    if depth == 0:
        # child can be null, empty object, or nested record (depth=1)
        child_null = st.just("null")
        child_empty_obj = st.just("{}")
        child_nested = record_json(depth=1)
        child_field = st.one_of(child_null, child_empty_obj, child_nested)
    else:
        # depth=1: child must be null (no further recursion)
        child_field = st.just("null")

    # Compose the record fields as JSON text
    # To cause divergence, vary one or two fields at a time from well-formed base
    # We'll produce a base well-formed record, then randomly replace one or two fields with "off" values

    # Base well-formed record fields
    base_fields = st.tuples(id_field, amount_field, name_field, status_field, tags_field, child_field)

    # Strategy to produce a dict of fields with possible one or two fields replaced by "off" values
    def build_record(t):
        idv, amountv, namev, statusv, tagsv, childv = t
        fields = {
            "id": idv,
            "amount": amountv,
            "name": namev,
            "status": statusv,
            "tags": tagsv,
            "child": childv
        }
        # We pick 0,1 or 2 fields to "corrupt" or "alter" to cause divergence
        # For each chosen field, replace with a value that triggers known divergence patterns

        # Known divergence triggers per field:
        # id: integer or string convertible to int accepted by all; no divergence known here, so skip corrupting id
        # amount: string or number accepted by Gson, Moshi, Jackson; kotlinx rejects number -> replace amount with number or string accordingly
        # name: string or null accepted by all; number accepted by Gson, Moshi, Jackson; kotlinx rejects number -> replace name with number or string accordingly
        # status: only exact enum strings accepted by Moshi, kotlinx, Jackson; Gson accepts invalid but decodes as null -> replace status with invalid string to cause divergence
        # tags: must be array; elements must be strings or convertible; Gson, Moshi, Jackson accept numbers; Moshi rejects booleans; kotlinx rejects non-string -> produce tags with booleans or numbers to cause divergence
        # child: null, full record, empty object; empty object accepted only by Gson -> produce empty object or missing fields in child to cause divergence

        # We'll define possible corruptions per field:
        corruptions = {
            "amount": [
                # force amount as number (raw) or string
                amount_num,
                amount_str.map(json_string)
            ],
            "name": [
                # null, string, number (int or float)
                st.none().map(lambda _: "null"),
                st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 for c in s) and all(c not in '"\\' for c in s)).map(json_string),
                st.integers(min_value=-1000, max_value=1000).map(str),
                st.floats(allow_nan=False, allow_infinity=False, width=32).map(lambda f: ('%.6g' % f).rstrip('0').rstrip('.') if '.' in ('%.6g' % f) else ('%.6g' % f))
            ],
            "status": [
                # valid enum strings
                st.sampled_from(['active', 'inactive', 'unknown']).map(json_string),
                # invalid strings
                st.text(min_size=1, max_size=5).filter(lambda s: s not in ['active', 'inactive', 'unknown'] and all(32 <= ord(c) <= 126 for c in s) and all(c not in '"\\' for c in s)).map(json_string)
            ],
            "tags": [
                # array of strings
                st.lists(st.text(min_size=1, max_size=5).filter(lambda s: all(32 <= ord(c) <= 126 for c in s) and all(c not in '"\\' for c in s)), min_size=0, max_size=3).map(json_array_of_strings),
                # array with numbers (raw)
                st.lists(st.integers(min_value=-1000, max_value=1000).map(str), min_size=0, max_size=3).map(lambda lst: '[' + ','.join(lst) + ']'),
                # array with booleans (raw)
                st.lists(st.booleans().map(lambda b: "true" if b else "false"), min_size=0, max_size=3).map(lambda lst: '[' + ','.join(lst) + ']'),
                # empty array
                st.just("[]")
            ],
            "child": [
                # null
                st.just("null"),
                # empty object
                st.just("{}"),
                # full nested record (depth=1)
                record_json(depth=1)
            ]
        }

        # We do not corrupt "id" because no known divergence on id field type

        # Choose how many fields to corrupt: 0,1 or 2 (favor 1 or 2)
        import random
        # We cannot use random here, so use Hypothesis to choose number of corruptions and fields
        # We'll do this outside build_record, so here just return fields as is
        return fields

    # We need to do the corruption outside build_record because we cannot use random
    # So we define a strategy that picks 0,1 or 2 fields to corrupt, then picks corruptions for those fields

    # Fields eligible for corruption (exclude "id")
    corruptible_fields = ["amount", "name", "status", "tags", "child"]

    # Strategy to pick number of corruptions: 0 (rare), 1 or 2 (common)
    corrupt_count = st.integers(min_value=0, max_value=2)

    # Strategy to pick which fields to corrupt
    def corrupt_fields(n):
        if n == 0:
            return st.just([])
        else:
            return st.lists(st.sampled_from(corruptible_fields), min_size=n, max_size=n, unique=True)

    # Compose final strategy
    def final_strategy():
        return st.tuples(base_fields, corrupt_count).flatmap(
            lambda bc: corrupt_fields(bc[1]).flatmap(
                lambda fields_to_corrupt: st.tuples(*[corruptions[f] for f in fields_to_corrupt]).map(
                    lambda corrupt_values: (bc[0], fields_to_corrupt, corrupt_values)
                )
            )
        )

    # Compose JSON text from base fields and corruptions
    def compose_json(data):
        base_vals, fields_to_corrupt, corrupt_vals = data
        idv, amountv, namev, statusv, tagsv, childv = base_vals
        fields = {
            "id": idv,
            "amount": amountv,
            "name": namev,
            "status": statusv,
            "tags": tagsv,
            "child": childv
        }
        for f, v in zip(fields_to_corrupt, corrupt_vals):
            fields[f] = v
        return json_object(fields)

    return final_strategy().map(compose_json)

@st.composite
def generated_json(draw) -> bytes:
    # Produce a JSON document as bytes
    # Use record_json(depth=0)
    s = draw(record_json(depth=0))
    return s.encode('utf-8')