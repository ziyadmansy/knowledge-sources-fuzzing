from hypothesis import strategies as st

# We build JSON text manually, carefully controlling formatting and types,
# to produce documents that trigger known divergences among Gson, Moshi,
# kotlinx.serialization, and Jackson Kotlin module.

# Known divergence points to exploit:
# - "id": int or string numeric (all accept both)
# - "amount": string normally; Gson/Moshi/Jackson accept number coercion; kotlinx rejects number
# - "name": string or null normally; Gson/Moshi/Jackson accept number/boolean coercion; kotlinx rejects non-string
# - "status": enum string ("active","inactive","unknown"); invalid string rejected by Moshi/kotlinx/Jackson, accepted as null by Gson
# - "tags": array of strings normally; non-array rejected by all; non-string elements/nulls accepted by Gson/Moshi/Jackson, rejected by kotlinx
# - "child": nested record or null; nested child with missing fields accepted only by Gson (default values), others reject
# - Extra fields: Gson/Moshi accept ignoring; kotlinx/Jackson reject
# - Null "status": Gson accepts as null; others reject
# - Empty child object: Gson accepts with defaults; others reject
# - Nested child with empty child: Gson accepts; others reject
# - Nested child with extra fields: Gson/Moshi accept; kotlinx/Jackson reject

# Strategy:
# - Generate a mostly well-formed document, then vary 1 or 2 fields to trigger divergences.
# - Use bounded recursion for child (max depth 1).
# - Use string concatenation to build JSON text.
# - Use st.one_of and st.just to produce variants that trigger known divergences.

def json_string_escape(s: str) -> str:
    # Minimal JSON string escaping for control chars and quotes/backslash
    # Only escape backslash and quote and control chars \b \f \n \r \t
    # Hypothesis strings are unicode, but we keep it simple here.
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    s = s.replace('\b', '\\b').replace('\f', '\\f').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return s

def json_string(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

def json_string_or_null(draw, base_str_strategy):
    # Sometimes null, sometimes string
    return draw(st.one_of(st.just("null"), base_str_strategy.map(json_string)))

def json_array_of_strings(draw, base_str_strategy):
    # Array of strings, or array with nulls or non-strings (to trigger divergence)
    # We produce either:
    # - all strings (normal)
    # - some nulls (accepted by Gson/Moshi/Jackson, rejected by kotlinx)
    # - some numbers or booleans (accepted by Gson/Moshi/Jackson, rejected by kotlinx)
    choice = draw(st.integers(min_value=0, max_value=2))
    if choice == 0:
        # all strings
        arr = draw(st.lists(base_str_strategy.map(json_string), min_size=0, max_size=3))
    elif choice == 1:
        # some nulls mixed with strings
        arr = draw(st.lists(st.one_of(st.just("null"), base_str_strategy.map(json_string)), min_size=0, max_size=3))
    else:
        # some numbers or booleans mixed with strings
        elems = []
        n = draw(st.integers(min_value=0, max_value=3))
        for _ in range(n):
            elem_type = draw(st.integers(min_value=0, max_value=2))
            if elem_type == 0:
                elems.append(draw(base_str_strategy).map(json_string))
            elif elem_type == 1:
                elems.append(draw(st.integers(min_value=0, max_value=10)).map(str))
            else:
                elems.append(draw(st.booleans()).map(lambda b: "true" if b else "false"))
        arr = elems
    return "[" + ",".join(arr) + "]"

def json_number_or_string(draw):
    # For "id" field: accept int or string numeric
    choice = draw(st.booleans())
    if choice:
        # number
        return str(draw(st.integers(min_value=0, max_value=1000)))
    else:
        # string numeric
        return json_string(str(draw(st.integers(min_value=0, max_value=1000))))

def json_amount(draw):
    # "amount" normally string
    # Known divergence: Gson/Moshi/Jackson accept number; kotlinx rejects number
    choice = draw(st.integers(min_value=0, max_value=2))
    if choice == 0:
        # string amount normal
        return json_string(draw(st.text(min_size=1, max_size=5, alphabet="0123456789.")))
    elif choice == 1:
        # number amount (trigger divergence)
        # Use integer or float
        if draw(st.booleans()):
            return str(draw(st.integers(min_value=0, max_value=10000)))
        else:
            # float with decimal point
            return str(draw(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)))
    else:
        # string numeric but empty or weird (still string)
        return json_string(draw(st.text(min_size=0, max_size=3, alphabet="0123456789")))

def json_name(draw):
    # "name": string or null normally
    # Known divergence: Gson/Moshi/Jackson accept number/boolean coercion; kotlinx rejects non-string
    choice = draw(st.integers(min_value=0, max_value=3))
    if choice == 0:
        # string or null normal
        if draw(st.booleans()):
            return "null"
        else:
            return json_string(draw(st.text(min_size=1, max_size=10)))
    elif choice == 1:
        # number (int or float)
        if draw(st.booleans()):
            return str(draw(st.integers(min_value=0, max_value=1000)))
        else:
            return str(draw(st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)))
    elif choice == 2:
        # boolean
        return "true" if draw(st.booleans()) else "false"
    else:
        # empty string
        return json_string("")

def json_status(draw):
    # "status": one of "active", "inactive", "unknown"
    # Known divergence: invalid enum string rejected by Moshi/kotlinx/Jackson; Gson accepts with null
    # Also null rejected by Moshi/kotlinx/Jackson; Gson accepts null
    choice = draw(st.integers(min_value=0, max_value=4))
    if choice == 0:
        return json_string(draw(st.sampled_from(["active", "inactive", "unknown"])))
    elif choice == 1:
        # invalid enum string
        return json_string(draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in ["active", "inactive", "unknown"])))
    elif choice == 2:
        # null
        return "null"
    elif choice == 3:
        # empty string
        return json_string("")
    else:
        # number (invalid type)
        return str(draw(st.integers(min_value=0, max_value=10)))

def json_tags(draw):
    # "tags": array of strings normally
    # Known divergence: non-array rejected by all
    # non-string elements/nulls accepted by Gson/Moshi/Jackson, rejected by kotlinx
    choice = draw(st.integers(min_value=0, max_value=3))
    if choice == 0:
        # normal array of strings
        arr = draw(st.lists(st.text(min_size=1, max_size=5), min_size=0, max_size=3))
        return "[" + ",".join(json_string(s) for s in arr) + "]"
    elif choice == 1:
        # array with nulls and strings
        arr = draw(st.lists(st.one_of(st.just("null"), st.text(min_size=1, max_size=5).map(json_string)), min_size=0, max_size=3))
        return "[" + ",".join(arr) + "]"
    elif choice == 2:
        # array with numbers/booleans and strings
        elems = []
        n = draw(st.integers(min_value=0, max_value=3))
        for _ in range(n):
            t = draw(st.integers(min_value=0, max_value=2))
            if t == 0:
                elems.append(json_string(draw(st.text(min_size=1, max_size=5))))
            elif t == 1:
                elems.append(str(draw(st.integers(min_value=0, max_value=10))))
            else:
                elems.append("true" if draw(st.booleans()) else "false")
        return "[" + ",".join(elems) + "]"
    else:
        # non-array (string)
        return json_string(draw(st.text(min_size=1, max_size=5)))

def json_child(draw, depth=0):
    # "child": either null or nested record (one level recursion max)
    # Known divergence:
    # - empty child object accepted only by Gson (default values), others reject
    # - nested child with empty child inside rejected by Moshi/kotlinx/Jackson; Gson accepts
    # - nested child with extra fields accepted by Gson/Moshi; rejected by kotlinx/Jackson
    # - extra fields at top level cause divergence (Gson/Moshi accept; kotlinx/Jackson reject)
    if depth > 1:
        # limit recursion depth
        return "null"
    choice = draw(st.integers(min_value=0, max_value=5))
    if choice == 0:
        # null child
        return "null"
    elif choice == 1:
        # well-formed child with all fields correct types
        return json_record(draw, depth + 1, extra_fields=False, empty_child=False)
    elif choice == 2:
        # empty child object {}
        return "{}"
    elif choice == 3:
        # child with empty child inside
        inner = "{}"
        inner_field = '"child":' + inner
        # build child with all fields + child empty
        id_field = '"id":' + json_number_or_string(draw)
        amount_field = '"amount":' + json_amount(draw)
        name_field = '"name":' + json_name(draw)
        status_field = '"status":' + json_status(draw)
        tags_field = '"tags":' + json_tags(draw)
        fields = [id_field, amount_field, name_field, status_field, tags_field, inner_field]
        return "{" + ",".join(fields) + "}"
    else:
        # child with extra fields
        base = json_record(draw, depth + 1, extra_fields=False, empty_child=False)
        # insert extra field before closing }
        # extra field: "extra_field": 123
        if base.endswith("}"):
            base = base[:-1] + ',"extra_field":123}'
        return base

def json_record(draw, depth=0, extra_fields=False, empty_child=False):
    # Build a record JSON text with fields:
    # id, amount, name, status, tags, child
    # extra_fields: if True, add extra top-level fields (trigger divergence)
    # empty_child: if True, child is empty object ({}), else normal child or null
    id_field = '"id":' + json_number_or_string(draw)
    amount_field = '"amount":' + json_amount(draw)
    name_field = '"name":' + json_name(draw)
    status_field = '"status":' + json_status(draw)
    tags_field = '"tags":' + json_tags(draw)
    if empty_child:
        child_field = '"child":{}'
    else:
        child_field = '"child":' + json_child(draw, depth)
    fields = [id_field, amount_field, name_field, status_field, tags_field, child_field]
    if extra_fields:
        # add extra fields at top level (trigger divergence)
        fields.append('"extra_top_level":123')
    return "{" + ",".join(fields) + "}"

@st.composite
def generated_json(draw) -> bytes:
    # Compose document with 1 or 2 divergence triggers:
    # - extra_fields top-level
    # - empty_child
    # - invalid status enum or null status
    # - amount number vs string
    # - name number/boolean vs string/null
    # - tags non-string elements or non-array
    # - child variations (empty, nested empty child, extra fields)
    # We pick one or two of these to maximize disagreement.

    # Choose flags for divergence triggers
    extra_fields = draw(st.booleans())
    empty_child = draw(st.booleans())
    # To avoid too many malformed at once, limit to max 2 triggers
    triggers = [extra_fields, empty_child]
    if sum(triggers) > 2:
        # reduce triggers if too many
        if extra_fields and empty_child:
            # randomly disable one
            if draw(st.booleans()):
                extra_fields = False
            else:
                empty_child = False

    # Build base record with chosen flags
    json_text = json_record(draw, extra_fields=extra_fields, empty_child=empty_child)

    # Further tweak 1 or 2 fields to trigger divergences
    # We do this by parsing the JSON text into fields (string manipulation),
    # but since we cannot import json, we rebuild with controlled randomness.

    # Instead, we rebuild the record with controlled fields:
    # We pick one or two fields to replace with divergent variants.

    # Pick fields to tweak (0,1 or 2 fields)
    fields_to_tweak = draw(st.lists(st.sampled_from(["amount", "name", "status", "tags", "child"]), max_size=2, unique=True))

    # Build fields individually with tweaks
    id_field = '"id":' + json_number_or_string(draw)

    # amount
    if "amount" in fields_to_tweak:
        amount_field = json_amount(draw)
    else:
        # normal string amount
        amount_field = json_string(draw(st.text(min_size=1, max_size=5, alphabet="0123456789.")))

    # name
    if "name" in fields_to_tweak:
        name_field = json_name(draw)
    else:
        # string or null normal
        if draw(st.booleans()):
            name_field = "null"
        else:
            name_field = json_string(draw(st.text(min_size=1, max_size=10)))

    # status
    if "status" in fields_to_tweak:
        status_field = json_status(draw)
    else:
        status_field = json_string(draw(st.sampled_from(["active", "inactive", "unknown"])))

    # tags
    if "tags" in fields_to_tweak:
        tags_field = json_tags(draw)
    else:
        arr = draw(st.lists(st.text(min_size=1, max_size=5), min_size=0, max_size=3))
        tags_field = "[" + ",".join(json_string(s) for s in arr) + "]"

    # child
    if "child" in fields_to_tweak:
        child_field = json_child(draw, depth=0)
    else:
        if empty_child:
            child_field = "{}"
        else:
            # normal child or null
            if draw(st.booleans()):
                child_field = "null"
            else:
                child_field = json_record(draw, depth=1, extra_fields=False, empty_child=False)

    fields = [
        id_field,
        '"amount":' + amount_field,
        '"name":' + name_field,
        '"status":' + status_field,
        '"tags":' + tags_field,
        '"child":' + child_field,
    ]

    if extra_fields:
        fields.append('"extra_top_level":123')

    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")