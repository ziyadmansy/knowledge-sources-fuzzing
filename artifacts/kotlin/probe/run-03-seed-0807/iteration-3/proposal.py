from hypothesis import strategies as st

# Constants for enum status
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
INVALID_STATUS_VALUES = ['"enabled"', '"ACTIVE"', 'null', '123', 'true', 'false', '""']

# Helper to produce JSON string literal with proper escaping for simple ASCII subset
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote minimally
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON text for the record schema with controlled variations to maximize
    divergence among Gson, Moshi, kotlinx.serialization, and Jackson Kotlin module.
    """

    # --- id field ---
    # id: integer, but known to accept number or string number
    # We vary id as number or string number (always integer)
    id_int = draw(st.integers(min_value=0, max_value=1_000_000))
    id_as_string = draw(st.booleans())
    if id_as_string:
        id_json = str(id_int)
        # 50% chance to quote id as string
        if draw(st.booleans()):
            id_json = json_string_literal(str(id_int))
    else:
        id_json = str(id_int)

    # --- amount field ---
    # Known: Gson, Moshi, Jackson accept number or string; kotlinx rejects number
    # To maximize divergence, sometimes produce number, sometimes string, sometimes null (Gson accepts null)
    amount_null = draw(st.booleans())
    if amount_null:
        # Null amount to trigger Gson acceptance, others reject
        amount_json = "null"
    else:
        # number or string number
        amount_is_number = draw(st.booleans())
        if amount_is_number:
            # number, integer or float with 2 decimals
            amount_val = draw(st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False))
            # Format with 0 or 2 decimals
            if draw(st.booleans()):
                amount_json = str(int(amount_val))
            else:
                amount_json = f"{amount_val:.2f}"
        else:
            # string number, possibly with leading zeros or + sign to test parsing
            base_val = draw(st.integers(min_value=0, max_value=1_000_000))
            # Add optional + or leading zeros
            prefix = draw(st.sampled_from(['', '+', '0', '00']))
            amount_json = json_string_literal(prefix + str(base_val))

    # --- name field ---
    # Known: Gson, Moshi, Jackson accept string or number (converted to string); kotlinx rejects non-string non-null
    # name can be string, null, or number (int or float)
    name_null = draw(st.booleans())
    if name_null:
        name_json = "null"
    else:
        name_type = draw(st.sampled_from(['string', 'int', 'float']))
        if name_type == 'string':
            # simple ASCII string, possibly empty
            s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
            name_json = json_string_literal(s)
        elif name_type == 'int':
            n = draw(st.integers(min_value=-1000, max_value=1000))
            name_json = str(n)
        else:
            f = draw(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
            # format float with 1 or 2 decimals
            name_json = f"{f:.2f}"

    # --- status field ---
    # Known: Gson accepts invalid enum values and null as null; others reject
    # To maximize divergence, sometimes produce valid enum, sometimes invalid, sometimes null
    status_choice = draw(st.sampled_from(['valid', 'invalid', 'null']))
    if status_choice == 'valid':
        status_json = draw(st.sampled_from(STATUS_VALUES))
    elif status_choice == 'invalid':
        status_json = draw(st.sampled_from(INVALID_STATUS_VALUES))
    else:
        status_json = "null"

    # --- tags field ---
    # Known: must be array; Gson, Moshi, Jackson accept arrays with non-string elements and nulls; kotlinx rejects non-string and null elements
    # To maximize divergence, produce arrays with:
    # - all strings (valid)
    # - some non-string elements (int, float, bool, null)
    # - empty array
    # - null (only Gson accepts null tags in nested child, but top-level tags must be array always)
    # We produce only arrays here (never null) to avoid all rejecting
    tags_len = draw(st.integers(min_value=0, max_value=5))
    tags_elements = []
    for _ in range(tags_len):
        # element type: string (valid), int, float, bool, null
        elem_type = draw(st.sampled_from(['string', 'int', 'float', 'bool', 'null']))
        if elem_type == 'string':
            s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
            tags_elements.append(json_string_literal(s))
        elif elem_type == 'int':
            tags_elements.append(str(draw(st.integers(min_value=-1000, max_value=1000))))
        elif elem_type == 'float':
            f = draw(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
            tags_elements.append(f"{f:.2f}")
        elif elem_type == 'bool':
            tags_elements.append("true" if draw(st.booleans()) else "false")
        else:
            tags_elements.append("null")
    tags_json = "[" + ",".join(tags_elements) + "]"

    # --- child field ---
    # Known: child is Record or null (one level recursion normally)
    # Gson accepts empty object {} as child, filling defaults; others reject missing required fields
    # Gson accepts null child; others accept null child
    # Gson accepts null or invalid amount/tags in child; others reject
    # To maximize divergence, child can be:
    # - null
    # - empty object {}
    # - well-formed child with variations on amount, tags, name, status
    # - child with unknown fields (Gson, Moshi ignore; kotlinx, Jackson reject)
    # Limit recursion to one level only

    child_type = draw(st.sampled_from(['null', 'empty_object', 'well_formed', 'unknown_fields']))

    if child_type == 'null':
        child_json = "null"
    elif child_type == 'empty_object':
        # "{}" accepted by Gson only
        child_json = "{}"
    elif child_type == 'unknown_fields':
        # well-formed child plus unknown fields
        # Build a well-formed child first
        # id as number or string
        child_id_int = draw(st.integers(min_value=0, max_value=1_000_000))
        child_id_as_string = draw(st.booleans())
        if child_id_as_string:
            child_id_json = json_string_literal(str(child_id_int))
        else:
            child_id_json = str(child_id_int)

        # amount: null or string number or number (to trigger Gson acceptance of null)
        child_amount_null = draw(st.booleans())
        if child_amount_null:
            child_amount_json = "null"
        else:
            child_amount_is_number = draw(st.booleans())
            if child_amount_is_number:
                val = draw(st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False))
                child_amount_json = f"{val:.2f}"
            else:
                val = draw(st.integers(min_value=0, max_value=1_000_000))
                child_amount_json = json_string_literal(str(val))

        # name: string or null only (to avoid rejection)
        child_name_null = draw(st.booleans())
        if child_name_null:
            child_name_json = "null"
        else:
            s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
            child_name_json = json_string_literal(s)

        # status: valid enum only (to avoid rejection)
        child_status_json = draw(st.sampled_from(STATUS_VALUES))

        # tags: array of strings or null (Gson accepts null tags in child)
        child_tags_null = draw(st.booleans())
        if child_tags_null:
            child_tags_json = "null"
        else:
            # array of strings only
            tags_len = draw(st.integers(min_value=0, max_value=3))
            elems = []
            for _ in range(tags_len):
                s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
                elems.append(json_string_literal(s))
            child_tags_json = "[" + ",".join(elems) + "]"

        # child.child: null only to avoid deep recursion
        child_child_json = "null"

        # unknown fields: add one or two unknown fields with random values
        unknown_fields = []
        for _ in range(draw(st.integers(min_value=1, max_value=2))):
            key = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters=['"', '\\'])))
            # value: string, number, bool, null
            val_type = draw(st.sampled_from(['string', 'int', 'bool', 'null']))
            if val_type == 'string':
                val = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
                val_json = json_string_literal(val)
            elif val_type == 'int':
                val_json = str(draw(st.integers(min_value=-1000, max_value=1000)))
            elif val_type == 'bool':
                val_json = "true" if draw(st.booleans()) else "false"
            else:
                val_json = "null"
            unknown_fields.append(json_string_literal(key) + ":" + val_json)

        # Compose child JSON object with unknown fields appended
        child_fields = [
            '"id":' + child_id_json,
            '"amount":' + child_amount_json,
            '"name":' + child_name_json,
            '"status":' + child_status_json,
            '"tags":' + child_tags_json,
            '"child":' + child_child_json,
        ] + unknown_fields

        child_json = "{" + ",".join(child_fields) + "}"

    else:
        # well_formed child with some variations to maximize divergence
        # id as number or string
        child_id_int = draw(st.integers(min_value=0, max_value=1_000_000))
        child_id_as_string = draw(st.booleans())
        if child_id_as_string:
            child_id_json = json_string_literal(str(child_id_int))
        else:
            child_id_json = str(child_id_int)

        # amount: number or string number or null (to trigger Gson acceptance of null)
        child_amount_null = draw(st.booleans())
        if child_amount_null:
            child_amount_json = "null"
        else:
            child_amount_is_number = draw(st.booleans())
            if child_amount_is_number:
                val = draw(st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False))
                child_amount_json = f"{val:.2f}"
            else:
                val = draw(st.integers(min_value=0, max_value=1_000_000))
                child_amount_json = json_string_literal(str(val))

        # name: string or null or number (to trigger divergence)
        child_name_null = draw(st.booleans())
        if child_name_null:
            child_name_json = "null"
        else:
            name_type = draw(st.sampled_from(['string', 'int', 'float']))
            if name_type == 'string':
                s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
                child_name_json = json_string_literal(s)
            elif name_type == 'int':
                n = draw(st.integers(min_value=-1000, max_value=1000))
                child_name_json = str(n)
            else:
                f = draw(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
                child_name_json = f"{f:.2f}"

        # status: valid enum only (to avoid rejection)
        child_status_json = draw(st.sampled_from(STATUS_VALUES))

        # tags: array of strings or null (Gson accepts null tags in child)
        child_tags_null = draw(st.booleans())
        if child_tags_null:
            child_tags_json = "null"
        else:
            tags_len = draw(st.integers(min_value=0, max_value=3))
            elems = []
            for _ in range(tags_len):
                s = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"', '\\'])))
                elems.append(json_string_literal(s))
            child_tags_json = "[" + ",".join(elems) + "]"

        # child.child: null only to avoid deep recursion
        child_child_json = "null"

        child_fields = [
            '"id":' + child_id_json,
            '"amount":' + child_amount_json,
            '"name":' + child_name_json,
            '"status":' + child_status_json,
            '"tags":' + child_tags_json,
            '"child":' + child_child_json,
        ]
        child_json = "{" + ",".join(child_fields) + "}"

    # Compose top-level JSON object
    fields = [
        '"id":' + id_json,
        '"amount":' + amount_json,
        '"name":' + name_json,
        '"status":' + status_json,
        '"tags":' + tags_json,
        '"child":' + child_json,
    ]
    json_text = "{" + ",".join(fields) + "}"

    return json_text.encode("utf-8")