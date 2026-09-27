from hypothesis import strategies as st

# Helper: JSON string escape for a limited safe subset (no control chars, no quotes inside)
# We'll generate strings without quotes or backslashes to avoid escaping complexity.
safe_json_string = st.text(
    alphabet=st.characters(
        blacklist_characters=['\\', '"', '\b', '\f', '\n', '\r', '\t'],
        min_codepoint=0x20,
        max_codepoint=0x7E,
    ),
    min_size=0,
    max_size=10,
).map(lambda s: '"' + s + '"')

# JSON enum strings for "status"
status_enum = st.sampled_from(['"active"', '"inactive"', '"unknown"'])

# JSON null literal
json_null = st.just("null")

# JSON number as string (integer)
json_int = st.integers(min_value=0, max_value=100000).map(str)

# JSON number as number (no quotes)
json_number = st.integers(min_value=0, max_value=100000).map(str)

# JSON string or number for fields that accept both (like "amount" for some)
json_string_or_number = st.one_of(
    safe_json_string,
    json_number,
)

# JSON string or null for "name"
json_name_string_or_null = st.one_of(
    safe_json_string,
    json_null,
)

# JSON string or number or null for "name" (to test divergence)
json_name_string_number_null = st.one_of(
    safe_json_string,
    json_number,
    json_null,
)

# JSON array of strings or numbers (for "tags")
# We will generate arrays of 0 to 3 elements to keep size small
json_tags_array = st.lists(
    st.one_of(
        safe_json_string,
        json_number,
    ),
    min_size=0,
    max_size=3,
).map(lambda elems: "[" + ",".join(elems) + "]")

# JSON array of strings only (for "tags" strict)
json_tags_array_strict = st.lists(
    safe_json_string,
    min_size=0,
    max_size=3,
).map(lambda elems: "[" + ",".join(elems) + "]")

# JSON array of booleans (to test rejection by Moshi and kotlinx)
json_tags_array_bool = st.lists(
    st.sampled_from(["true", "false"]),
    min_size=0,
    max_size=3,
).map(lambda elems: "[" + ",".join(elems) + "]")

# JSON object with fields for the Record, recursive but bounded depth
# We'll define a function to generate a record JSON text with controlled recursion depth

def json_record(depth: int) -> st.SearchStrategy[str]:
    # At depth 0, child must be null or omitted (but we always include child)
    # We produce a JSON object string with all six fields always present (except child can be null)
    # We vary one or two fields to try to provoke divergence

    # id: integer or string convertible to integer
    id_field = st.one_of(
        json_int.map(lambda v: f'"id":{v}'),
        json_int.map(lambda v: f'"id":"{v}"'),
    )

    # amount: string or number (kotlinx rejects number)
    amount_field = st.one_of(
        safe_json_string.map(lambda v: f'"amount":{v}'),
        json_number.map(lambda v: f'"amount":{v}'),
    )

    # name: string, number, or null (kotlinx rejects number)
    name_field = st.one_of(
        safe_json_string.map(lambda v: f'"name":{v}'),
        json_number.map(lambda v: f'"name":{v}'),
        json_null.map(lambda v: f'"name":{v}'),
    )

    # status: exact enum strings or invalid string (Gson accepts invalid as null)
    status_field = st.one_of(
        status_enum.map(lambda v: f'"status":{v}'),
        # invalid enum string to test Gson acceptance but others reject
        safe_json_string.filter(lambda s: s not in ['"active"', '"inactive"', '"unknown"']).map(lambda v: f'"status":{v}'),
    )

    # tags: array of strings or numbers or booleans (to test Moshi rejection of booleans)
    tags_field = st.one_of(
        json_tags_array.map(lambda v: f'"tags":{v}'),
        json_tags_array_bool.map(lambda v: f'"tags":{v}'),
        # also test string instead of array (all reject)
        safe_json_string.map(lambda v: f'"tags":{v}'),
    )

    # child: null or nested record (depth-1)
    if depth <= 0:
        child_field = json_null.map(lambda v: f'"child":{v}')
    else:
        # child can be null or a nested record with depth-1
        child_field = st.one_of(
            json_null.map(lambda v: f'"child":{v}'),
            json_record(depth - 1).map(lambda v: f'"child":{v}'),
            # empty object {} accepted only by Gson
            st.just('"child":{}'),
            # object missing fields (to test Moshi, kotlinx, Jackson rejection)
            st.just('"child":{"id":1}'),
        )

    # Compose fields into JSON object string
    # We vary which fields appear in which order to test duplicate keys (last wins)
    # But always include all six fields once (except child variations above)
    # We also sometimes add duplicate keys for "id" or "amount" to test last-wins behavior

    # Compose a list of fields, possibly with duplicates
    def fields_with_duplicates():
        # base fields
        base_fields = [id_field, amount_field, name_field, status_field, tags_field, child_field]

        # We draw from base_fields strategies to get actual strings
        return st.tuples(*base_fields).flatmap(lambda fields:
            # Possibly insert duplicates of "id" or "amount" or "name" keys
            st.one_of(
                # no duplicates
                st.just(fields),
                # duplicate "id" at end (last wins)
                st.tuples(st.just(fields), id_field).map(lambda t: t[0] + (t[1],)),
                # duplicate "amount" at start
                st.tuples(amount_field, st.just(fields)).map(lambda t: (t[0],) + t[1]),
                # duplicate "name" in middle
                st.tuples(fields[:2], name_field, fields[2:]).map(lambda t: t[0] + (t[1],) + t[2]),
            )
        )

    return fields_with_duplicates().map(
        lambda fs: "{" + ",".join(fs) + "}"
    )

@st.composite
def generated_json(draw) -> bytes:
    # Generate a record JSON string with depth 1 (one nested child)
    # This will produce documents that vary one or two fields at a time,
    # including some known divergence triggers from the knowledge base.

    # Draw the JSON text
    json_text = draw(json_record(depth=1))

    # Return as bytes (UTF-8)
    return json_text.encode("utf-8")