from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslash only (minimal)
def json_string_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')

# Compose JSON string literal from Python string
def json_string_literal(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

# Compose JSON array from list of JSON text elements
def json_array_literal(elements) -> str:
    return '[' + ','.join(elements) + ']'

# Compose JSON object from list of (key, value) JSON text pairs
def json_object_literal(pairs) -> str:
    # pairs: list of (key_json_string, value_json_string)
    return '{' + ','.join(k + ':' + v for k, v in pairs) + '}'

# Compose JSON null literal
json_null = 'null'

# Compose JSON boolean literals
json_true = 'true'
json_false = 'false'

# Compose JSON number literal from int or float or string representing number
def json_number_literal(n) -> str:
    # n is int or float or string representing number
    if isinstance(n, str):
        return n
    else:
        return str(n)

# Compose JSON enum literal (string)
def json_enum_literal(s: str) -> str:
    # s is one of "active", "inactive", "unknown"
    return json_string_literal(s)

# Compose JSON field: key (string) and value (json text)
def json_field(key: str, value: str) -> (str, str):
    return (json_string_literal(key), value)

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate JSON documents as bytes, with bounded recursion and
    variations designed to trigger divergences between Gson, Moshi,
    kotlinx.serialization, and Jackson Kotlin module, per the known probes.
    """

    # Constants for enum values
    enum_values = ["active", "inactive", "unknown"]

    # Strategy for "id" field:
    # Known: accepts int or string convertible to int.
    # Let's sometimes produce int, sometimes string int, sometimes invalid string.
    id_int = st.integers(min_value=0, max_value=10**6)
    id_str_int = id_int.map(str)
    id_invalid_str = st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit())
    id_field_strategy = st.one_of(
        id_int.map(json_number_literal),
        id_str_int.map(json_string_literal),
        id_invalid_str.map(json_string_literal),
    )

    # Strategy for "amount" field:
    # Known: Gson, Moshi, Jackson accept number coercing to string; kotlinx rejects number.
    # Also accepts string.
    # Let's produce either string, number, or invalid type (bool/null).
    amount_str = st.text(min_size=1, max_size=10).map(json_string_literal)
    amount_num = st.one_of(
        st.integers(min_value=0, max_value=10**6),
        st.floats(allow_infinity=False, allow_nan=False, width=32)
    ).map(json_number_literal)
    amount_invalid = st.one_of(
        st.booleans().map(lambda b: json_true if b else json_false),
        st.just(json_null)
    )
    amount_field_strategy = st.one_of(amount_str, amount_num, amount_invalid)

    # Strategy for "name" field:
    # Known: string or null normally.
    # Gson, Moshi, Jackson accept number coercing to string; kotlinx rejects number.
    # Let's produce string, null, number, or invalid bool.
    name_str = st.one_of(st.none(), st.text(min_size=0, max_size=10)).map(
        lambda v: json_null if v is None else json_string_literal(v)
    )
    name_num = st.one_of(
        st.integers(min_value=-1000, max_value=1000),
        st.floats(allow_infinity=False, allow_nan=False, width=32)
    ).map(json_number_literal)
    name_bool = st.booleans().map(lambda b: json_true if b else json_false)
    name_field_strategy = st.one_of(name_str, name_num, name_bool)

    # Strategy for "status" field:
    # Known: enum string values accepted by all.
    # Invalid enum string rejected by Moshi, kotlinx, Jackson; Gson accepts with null.
    # Null rejected by Moshi, kotlinx, Jackson; Gson accepts with null.
    # Let's produce valid enum string, invalid string, null.
    status_valid = st.sampled_from(enum_values).map(json_string_literal)
    status_invalid_str = st.text(min_size=1, max_size=10).filter(lambda s: s not in enum_values).map(json_string_literal)
    status_null = st.just(json_null)
    status_field_strategy = st.one_of(status_valid, status_invalid_str, status_null)

    # Strategy for "tags" field:
    # Known: must be array.
    # String instead of array rejected by all.
    # Array elements: strings normally.
    # Gson, Moshi, Jackson accept numeric elements coercing to string; kotlinx rejects.
    # Gson, Moshi, Jackson accept null elements; kotlinx rejects.
    # Gson, Moshi, Jackson accept mixed types; kotlinx rejects.
    # Let's produce:
    # - valid array of strings
    # - array with numeric elements
    # - array with null elements
    # - array with mixed elements (string, number, null)
    # - invalid: string instead of array
    tag_str_elem = st.text(min_size=0, max_size=10).map(json_string_literal)
    tag_num_elem = st.one_of(
        st.integers(min_value=-1000, max_value=1000),
        st.floats(allow_infinity=False, allow_nan=False, width=32)
    ).map(json_number_literal)
    tag_null_elem = st.just(json_null)
    tag_mixed_elem = st.one_of(tag_str_elem, tag_num_elem, tag_null_elem)

    # Array strategies
    tags_array_strings = st.lists(tag_str_elem, min_size=0, max_size=5).map(json_array_literal)
    tags_array_numbers = st.lists(tag_num_elem, min_size=0, max_size=5).map(json_array_literal)
    tags_array_nulls = st.lists(tag_null_elem, min_size=0, max_size=5).map(json_array_literal)
    tags_array_mixed = st.lists(tag_mixed_elem, min_size=0, max_size=5).map(json_array_literal)
    tags_invalid_string = st.text(min_size=1, max_size=10).map(json_string_literal)

    tags_field_strategy = st.one_of(
        tags_array_strings,
        tags_array_numbers,
        tags_array_nulls,
        tags_array_mixed,
        tags_invalid_string,
    )

    # Recursive strategy for "child" field:
    # Known: null accepted by all.
    # Empty object accepted only by Gson; others reject.
    # Nested one-level recursion accepted by all.
    # Gson, Moshi accept extra unknown fields at root; kotlinx, Jackson reject.
    # Gson accepts empty object for child filling missing fields with defaults/nulls; others reject.
    # We'll limit recursion depth to 1.

    # To avoid infinite recursion, define a helper inner function with depth param.

    def child_strategy(depth=0):
        if depth > 1:
            # At max depth, only null or well-formed object with no child
            # Compose well-formed child object with no child (child=null)
            return well_formed_object_strategy(depth=depth)
        else:
            # Compose child as one of:
            # - null
            # - well-formed object with child (depth+1)
            # - empty object "{}" (accepted only by Gson)
            # - object with extra unknown fields (accepted by Gson, Moshi)
            # We'll produce these as JSON text strings.

            # well-formed child object with child field (recursive)
            well_formed = well_formed_object_strategy(depth=depth+1)

            empty_obj = st.just('{}')

            # extra unknown fields: add one unknown field with string value
            def add_extra_field(obj_json: str) -> str:
                # obj_json is JSON object string like {"k1":v1,...}
                # Insert extra field "extra_field":"extra_value"
                # Insert before last }
                if obj_json.endswith('}'):
                    return obj_json[:-1] + ',"extra_field":"extra_value"}'
                else:
                    return obj_json

            extra_field_obj = well_formed.map(add_extra_field)

            return st.one_of(
                st.just(json_null),
                well_formed,
                empty_obj,
                extra_field_obj,
            )

    # Compose well-formed object with all fields, optionally with child (depth param)
    def well_formed_object_strategy(depth=0):
        # Compose all fields with well-formed types:
        # id: int or string int
        # amount: string (not number, to avoid kotlinx rejection)
        # name: string or null
        # status: valid enum string
        # tags: array of strings
        # child: null or well-formed child (depth+1)

        id_val = st.one_of(
            st.integers(min_value=0, max_value=10**6).map(json_number_literal),
            st.integers(min_value=0, max_value=10**6).map(lambda i: json_string_literal(str(i)))
        )
        amount_val = st.text(min_size=1, max_size=10).map(json_string_literal)
        name_val = st.one_of(
            st.none().map(lambda _: json_null),
            st.text(min_size=0, max_size=10).map(json_string_literal)
        )
        status_val = st.sampled_from(enum_values).map(json_string_literal)
        tags_val = st.lists(st.text(min_size=0, max_size=10).map(json_string_literal), min_size=0, max_size=5).map(json_array_literal)
        child_val = child_strategy(depth=depth)

        return st.tuples(id_val, amount_val, name_val, status_val, tags_val, child_val).map(
            lambda t: json_object_literal([
                json_field("id", t[0]),
                json_field("amount", t[1]),
                json_field("name", t[2]),
                json_field("status", t[3]),
                json_field("tags", t[4]),
                json_field("child", t[5]),
            ])
        )

    # Compose the root object with variations to trigger divergences:
    # We'll pick one or two fields to be "off" from well-formed, others well-formed.
    # This matches the hint to vary one or two things at a time.

    # Strategy to pick one or two fields to mutate (from the 6 fields)
    fields = ["id", "amount", "name", "status", "tags", "child"]

    # Generate a set of 0,1 or 2 fields to mutate (0 means all well-formed)
    mutate_count = st.integers(min_value=0, max_value=2)
    mutate_fields_strategy = mutate_count.flatmap(
        lambda n: st.lists(st.sampled_from(fields), min_size=n, max_size=n, unique=True)
    )

    # Generate a well-formed base object
    base_obj = well_formed_object_strategy(depth=0)

    # For each field, generate a mutated value or base value depending on mutate_fields
    def build_obj(mutate_fields, base_json_text):
        # base_json_text is JSON string of well-formed object
        # We'll parse base_json_text to dict-like structure? No, we can't import json.
        # Instead, we regenerate fields from base_obj tuple, so better to generate fields separately.

        # Instead, we generate fields separately here.

        # For each field, if in mutate_fields, generate mutated value from field-specific strategy,
        # else generate well-formed value from base_obj fields.

        # We'll generate all fields independently here.

        # id
        if "id" in mutate_fields:
            id_val = draw(id_field_strategy)
        else:
            id_val = draw(st.one_of(
                st.integers(min_value=0, max_value=10**6).map(json_number_literal),
                st.integers(min_value=0, max_value=10**6).map(lambda i: json_string_literal(str(i)))
            ))

        # amount
        if "amount" in mutate_fields:
            amount_val = draw(amount_field_strategy)
        else:
            amount_val = draw(st.text(min_size=1, max_size=10).map(json_string_literal))

        # name
        if "name" in mutate_fields:
            name_val = draw(name_field_strategy)
        else:
            name_val = draw(st.one_of(
                st.none().map(lambda _: json_null),
                st.text(min_size=0, max_size=10).map(json_string_literal)
            ))

        # status
        if "status" in mutate_fields:
            status_val = draw(status_field_strategy)
        else:
            status_val = draw(st.sampled_from(enum_values).map(json_string_literal))

        # tags
        if "tags" in mutate_fields:
            tags_val = draw(tags_field_strategy)
        else:
            tags_val = draw(st.lists(st.text(min_size=0, max_size=10).map(json_string_literal), min_size=0, max_size=5).map(json_array_literal))

        # child
        if "child" in mutate_fields:
            child_val = draw(child_strategy(depth=0))
        else:
            child_val = draw(st.one_of(
                st.just(json_null),
                well_formed_object_strategy(depth=1)
            ))

        obj = json_object_literal([
            json_field("id", id_val),
            json_field("amount", amount_val),
            json_field("name", name_val),
            json_field("status", status_val),
            json_field("tags", tags_val),
            json_field("child", child_val),
        ])

        return obj

    mutate_fields = draw(mutate_fields_strategy)
    # base_json_text unused, but required by build_obj signature, pass None
    json_text = build_obj(mutate_fields, None)

    return json_text.encode('utf-8')