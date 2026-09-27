from hypothesis import strategies as st

# Helper: JSON string with proper escaping for " and \ only (safe subset)
def json_string(s: str) -> str:
    # Escape backslash and double quote only, minimal escaping
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

# Helper: JSON array of strings
def json_array_of_strings(lst):
    return '[' + ','.join(json_string(e) for e in lst) + ']'

# Helper: JSON null
json_null = "null"

# Helper: JSON enum for status
valid_status_values = ["active", "inactive", "unknown"]

@st.composite
def generated_json(draw) -> bytes:
    # We build a record as a dict of strings (JSON text fragments),
    # then join with commas and braces at the end.

    # We want to produce mostly well-formed documents with one or two subtle divergences:
    # - missing optional fields (name, child) or missing required fields (amount, id, status, tags)
    #   but missing required fields usually rejected by all except built_value for status/tags
    # - fields present but with wrong type (e.g. id as string, amount as int, tags as string or array with non-string)
    # - fields with boundary values (empty strings, empty arrays, null where allowed)
    # - child recursion one level deep, well-formed or malformed
    # - extra fields ignored by all, so no need to add them
    # We want to vary one or two fields per document to maximize disagreement.

    # Strategy for id:
    # id is integer required
    # We try mostly correct int, sometimes string or null or missing (missing rejected by all)
    id_choice = draw(st.one_of(
        st.integers(min_value=0, max_value=2**31-1).map(str),
        st.text(min_size=1, max_size=5).map(json_string),  # wrong type string
        st.just(json_null),  # null (wrong type)
    ))
    id_missing = draw(st.booleans())  # sometimes omit id (all reject)

    # Strategy for amount:
    # amount is string required
    # mostly string, sometimes int or null or missing
    amount_choice = draw(st.one_of(
        st.text(min_size=1, max_size=10).map(json_string),
        st.integers(min_value=0, max_value=1000).map(str),  # wrong type int
        st.just(json_null),  # null (wrong type)
    ))
    amount_missing = draw(st.booleans())

    # Strategy for name:
    # name is string or null, optional (missing treated as null)
    # so present as string, null, or missing
    name_present = draw(st.booleans())
    if name_present:
        name_choice = draw(st.one_of(
            st.text(min_size=0, max_size=10).map(json_string),
            st.just(json_null),
            st.integers(min_value=0, max_value=1000).map(str),  # wrong type int
        ))
    else:
        name_choice = None

    # Strategy for status:
    # required enum string: "active", "inactive", "unknown"
    # missing accepted only by built_value (fills tags empty)
    # invalid value rejected by all
    status_missing = draw(st.booleans())
    if not status_missing:
        status_choice = draw(st.one_of(
            st.sampled_from(valid_status_values).map(json_string),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_status_values).map(json_string),  # invalid enum
            st.just(json_null),  # null (wrong type)
        ))
    else:
        status_choice = None

    # Strategy for tags:
    # required array of strings
    # missing accepted only by built_value (fills empty array)
    # wrong type: string, int, array with non-string elements
    tags_missing = draw(st.booleans())
    if not tags_missing:
        tags_choice = draw(st.one_of(
            st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=3).map(json_array_of_strings),
            st.text(min_size=1, max_size=10).map(json_string),  # wrong type string
            st.integers(min_value=0, max_value=100).map(str),  # wrong type int
            st.lists(st.one_of(st.integers(min_value=0, max_value=100).map(str), st.text(min_size=1, max_size=5).map(json_string)), min_size=1, max_size=3).map(
                lambda lst: '[' + ','.join(lst) + ']'),  # array with mixed types (some ints as strings, some strings quoted)
            st.just(json_null),  # null (wrong type)
        ))
    else:
        tags_choice = None

    # Strategy for child:
    # optional, null or nested record (one level)
    # missing treated as null by all
    child_present = draw(st.booleans())
    if child_present:
        # Nested record: mostly well-formed, sometimes malformed (one field off)
        # We reuse the same logic but limit recursion to one level only
        # To avoid infinite recursion, we do not recurse further in child
        # So child fields are always well-formed or with one subtle error

        # child id always integer string (mostly)
        child_id = draw(st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            st.text(min_size=1, max_size=5).map(json_string),
        ))
        child_id_missing = False  # never missing in child to keep mostly well-formed

        child_amount = draw(st.one_of(
            st.text(min_size=1, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=1000).map(str),
        ))
        child_amount_missing = False

        child_name_present = draw(st.booleans())
        if child_name_present:
            child_name = draw(st.one_of(
                st.text(min_size=0, max_size=10).map(json_string),
                st.just(json_null),
                st.integers(min_value=0, max_value=1000).map(str),
            ))
        else:
            child_name = None

        child_status_missing = draw(st.booleans())
        if not child_status_missing:
            child_status = draw(st.one_of(
                st.sampled_from(valid_status_values).map(json_string),
                st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_status_values).map(json_string),
                st.just(json_null),
            ))
        else:
            child_status = None

        child_tags_missing = draw(st.booleans())
        if not child_tags_missing:
            child_tags = draw(st.one_of(
                st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=3).map(json_array_of_strings),
                st.text(min_size=1, max_size=10).map(json_string),
                st.integers(min_value=0, max_value=100).map(str),
                st.lists(st.one_of(st.integers(min_value=0, max_value=100).map(str), st.text(min_size=1, max_size=5).map(json_string)), min_size=1, max_size=3).map(
                    lambda lst: '[' + ','.join(lst) + ']'),
                st.just(json_null),
            ))
        else:
            child_tags = None

        # child.child is always null or missing (no deeper recursion)
        child_child_present = draw(st.booleans())
        if child_child_present:
            child_child = json_null
        else:
            child_child = None

        # Build child JSON object fields list
        child_fields = []
        if not child_id_missing:
            child_fields.append('"id":' + child_id)
        if not child_amount_missing:
            child_fields.append('"amount":' + child_amount)
        if child_name is not None:
            child_fields.append('"name":' + child_name)
        # else omit name (treated as null)
        if child_status is not None:
            child_fields.append('"status":' + child_status)
        # else omit status
        if child_tags is not None:
            child_fields.append('"tags":' + child_tags)
        # else omit tags
        if child_child is not None:
            child_fields.append('"child":' + child_child)
        # else omit child

        child_json = '{' + ','.join(child_fields) + '}'
    else:
        child_json = None

    # Compose top-level fields
    fields = []

    if not id_missing:
        fields.append('"id":' + id_choice)
    # else omit id (all reject)

    if not amount_missing:
        fields.append('"amount":' + amount_choice)
    # else omit amount (all reject)

    if name_choice is not None:
        fields.append('"name":' + name_choice)
    # else omit name (treated as null)

    if not status_missing:
        fields.append('"status":' + status_choice)
    # else omit status (built_value accepts, others reject)

    if not tags_missing:
        fields.append('"tags":' + tags_choice)
    # else omit tags (built_value accepts, others reject)

    if child_json is not None:
        fields.append('"child":' + child_json)
    # else omit child (treated as null)

    # Compose JSON object string
    json_obj = '{' + ','.join(fields) + '}'

    return json_obj.encode('utf-8')