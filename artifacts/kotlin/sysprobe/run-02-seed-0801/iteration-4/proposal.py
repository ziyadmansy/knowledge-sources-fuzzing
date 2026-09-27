from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum values and max recursion depth
    STATUS_VALUES = ["active", "inactive", "unknown"]
    MAX_DEPTH = 1  # one level of recursion normally

    # Strategy for JSON string with proper escaping for quotes and backslashes
    def json_string():
        # Use ascii letters, digits, space, and some punctuation, avoiding control chars and quotes/backslash
        safe_chars = st.characters(
            whitelist_categories=('Ll', 'Lu', 'Nd', 'Zs', 'Po'),
            blacklist_characters='"\\'
        )
        # At least empty string allowed
        return st.text(safe_chars, max_size=20).map(
            lambda s: '"' + s.replace('\n', ' ').replace('\r', ' ') + '"'
        )

    # Strategy for JSON string or null (for nullable fields)
    def json_string_or_null():
        return st.one_of(json_string(), st.just("null"))

    # Strategy for JSON integer (id)
    # Gson treats missing or null as 0, so 0 is a good boundary value
    # Also try negative and large values
    json_int = st.integers(min_value=-1000, max_value=1000).map(str)

    # Strategy for JSON string for amount (but can be number convertible)
    # To trigger type divergences, sometimes produce numbers as numbers (no quotes)
    # or strings as strings (quoted)
    def json_amount():
        # 70% string, 30% number (int or float)
        str_val = json_string()
        num_val = st.one_of(
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: format(f, '.2f'))
        )
        # Also allow null to test nullability (Gson accepts null for non-nullable)
        return st.one_of(str_val, num_val, st.just("null"))

    # Strategy for enum field "status"
    # To trigger divergences:
    # - sometimes missing
    # - sometimes null
    # - sometimes unknown enum value (e.g. "Active", "invalid", "UNKNOWN")
    # - sometimes correct enum value
    def json_status():
        # Correct enum values quoted
        correct = st.sampled_from(STATUS_VALUES).map(lambda s: '"' + s + '"')
        # Unknown enum values (case variants or invalid)
        unknown = st.sampled_from(["\"Active\"", "\"INVALID\"", "\"UNKNOWN\"", "\"inactiv\"", "\"actve\""])
        # null literal
        null_lit = st.just("null")
        # Compose with weights to get variety
        return st.one_of(correct, unknown, null_lit)

    # Strategy for tags: array of strings (possibly empty)
    # To trigger divergences:
    # - sometimes null (not allowed, non-nullable)
    # - sometimes empty array
    # - sometimes array with strings
    # - sometimes array with wrong types (numbers)
    def json_tags():
        # string elements
        str_elem = json_string()
        # number elements as strings (to test type confusion)
        num_elem = st.integers(min_value=-1000, max_value=1000).map(str)
        # element can be string or number (unquoted)
        elem = st.one_of(str_elem, num_elem)
        arr = st.lists(elem, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
        # null literal
        null_lit = st.just("null")
        # Compose with weights: mostly array, sometimes null
        return st.one_of(arr, null_lit)

    # Strategy for name: nullable string
    # To trigger divergences:
    # - string or null
    # - sometimes number (wrong type)
    def json_name():
        str_val = json_string_or_null()
        num_val = st.integers(min_value=-1000, max_value=1000).map(str)
        # Compose with weights: mostly string or null, sometimes number
        return st.one_of(str_val, num_val)

    # Recursive strategy for child record or null
    # To avoid deep recursion, limit depth to MAX_DEPTH
    def json_record(depth=0):
        # Compose fields with possibility of missing or null to trigger divergences

        # id: integer, non-nullable
        # Sometimes missing or null to trigger divergences
        id_field = st.one_of(
            json_int.map(lambda v: '"id":' + v),
            st.just(""),  # missing field
            st.just('"id":null')
        )

        # amount: string, non-nullable
        amount_field = st.one_of(
            json_amount().map(lambda v: '"amount":' + v),
            st.just(""),  # missing
            st.just('"amount":null')
        )

        # name: string or null (nullable)
        name_field = st.one_of(
            json_name().map(lambda v: '"name":' + v),
            st.just(""),  # missing allowed (nullable)
            st.just('"name":null')
        )

        # status: enum, non-nullable
        status_field = st.one_of(
            json_status().map(lambda v: '"status":' + v),
            st.just(""),  # missing
            st.just('"status":null')
        )

        # tags: array of strings, non-nullable
        tags_field = st.one_of(
            json_tags().map(lambda v: '"tags":' + v),
            st.just(""),  # missing
            st.just('"tags":null')
        )

        # child: nullable record or null
        if depth < MAX_DEPTH:
            child_field = st.one_of(
                json_record(depth + 1).map(lambda v: '"child":' + v),
                st.just('"child":null'),
                st.just(""),  # missing
                # Also try wrong types for child (string or number)
                st.integers(min_value=-1000, max_value=1000).map(lambda v: f'"child":{v}'),
                json_string().map(lambda v: f'"child":{v}')
            )
        else:
            # At max depth, no recursion
            child_field = st.one_of(
                st.just('"child":null'),
                st.just(""),
                st.integers(min_value=-1000, max_value=1000).map(lambda v: f'"child":{v}'),
                json_string().map(lambda v: f'"child":{v}')
            )

        # Draw all fields
        fields = draw(st.tuples(id_field, amount_field, name_field, status_field, tags_field, child_field))

        # Filter out empty strings (missing fields)
        present_fields = [f for f in fields if f != ""]

        # Shuffle fields to vary order
        present_fields = draw(st.permutations(present_fields))

        # Compose JSON object text
        json_obj = "{" + ",".join(present_fields) + "}"

        return json_obj

    # Draw top-level record JSON text
    json_text = draw(json_record())

    # Return as bytes
    return json_text.encode("utf-8")