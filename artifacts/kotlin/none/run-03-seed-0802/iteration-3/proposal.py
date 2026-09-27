from hypothesis import strategies as st

# Constants for the schema
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']

@st.composite
def generated_json(draw, _depth=0):
    # Limit recursion depth to 1 for "child" field
    max_depth = 1

    # Helper to produce a JSON string value or null
    def json_string_or_null():
        # Sometimes null, sometimes string (including empty and special chars)
        return st.one_of(
            st.just("null"),
            st.text(min_size=0, max_size=10).map(lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"')
        )

    # Helper to produce a JSON array of strings (tags)
    def json_string_array():
        # Array of 0 to 3 strings, each string 0-8 chars, escaped
        return st.lists(
            st.text(min_size=0, max_size=8).map(lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'),
            min_size=0, max_size=3
        ).map(lambda lst: '[' + ','.join(lst) + ']')

    # Helper to produce a JSON number or string for "amount"
    # amount is string in schema, but try some edge cases to cause divergence:
    # - valid decimal strings
    # - empty string
    # - strings with spaces
    # - strings that look like numbers but with trailing spaces or signs
    # - strings with unicode digits or escapes
    def json_amount_string():
        # Choose among:
        # - decimal number string (e.g. "123.45")
        # - empty string ""
        # - string with spaces " 123 "
        # - string with signs "+123", "-0.99"
        # - string with unicode escapes (e.g. "\u0031\u0032")
        # - string with invalid number chars "12a3"
        options = [
            st.floats(min_value=0, max_value=1e6, allow_infinity=False, allow_nan=False).map(lambda f: '"' + format(f, 'f') + '"'),
            st.just('""'),
            st.text(min_size=1, max_size=5).map(lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'),
            st.sampled_from(['"+123"', '"-0.99"', '" 123 "', '"12a3"', '"\u0031\u0032"']),
        ]
        return st.one_of(*options)

    # Helper to produce a JSON integer for "id"
    # Try to cause divergence by using:
    # - normal integers
    # - numbers with leading zeros (e.g. 007)
    # - numbers as strings (should be rejected)
    # - negative numbers (should be rejected by schema but maybe accepted by some)
    def json_id():
        # We want the field to be integer (not string), but try some edge cases:
        # - normal int
        # - int with leading zeros (as number, e.g. 007 is 7 in JSON, so no effect)
        # - negative int
        # - float (should be rejected)
        # - string (should be rejected)
        # We'll produce only numbers here, but sometimes negative or float to cause divergence
        choice = draw(st.integers(min_value=-10, max_value=1000))
        # 10% chance to produce float instead of int
        if draw(st.booleans()):
            # float with zero fractional part to look like int but float type
            val = float(choice)
            # format without scientific notation
            s = str(val)
            # JSON number literal
            return s
        else:
            # integer literal, possibly negative
            return str(choice)

    # Helper to produce "status" field, sometimes invalid to cause divergence
    def json_status():
        # 80% valid, 20% invalid string or wrong type
        valid = st.sampled_from(STATUS_VALUES)
        invalid = st.one_of(
            st.just('"Active"'),  # case difference
            st.just('"inactive "'),  # trailing space
            st.just('"unknown?"'),  # extra char
            st.just('null'),
            st.integers(min_value=0, max_value=2).map(str),
            st.just('true'),
            st.just('""'),
        )
        return st.one_of(valid, invalid)

    # Compose the record JSON text
    # We produce fields in order: id, amount, name, status, tags, child
    # We vary one or two fields at a time to cause divergence

    # id field
    id_field = json_id()

    # amount field
    amount_field = json_amount_string()

    # name field
    name_field = json_string_or_null()

    # status field
    status_field = json_status()

    # tags field
    tags_field = json_string_array()

    # child field: either null or a nested record (one level only)
    if _depth < max_depth:
        # 50% chance null, 50% chance nested record (depth+1)
        child_field = draw(st.one_of(
            st.just("null"),
            generated_json(_depth=_depth + 1)
        ))
    else:
        child_field = "null"

    # Build JSON text with possible small variations to cause divergence
    # We vary presence of whitespace around colons and commas to test leniency
    # Also vary order of fields sometimes (some libs may be sensitive)
    # But mostly keep order fixed for simplicity and focus on value variations

    # Randomly choose whitespace style around colons and commas
    colon_ws = draw(st.sampled_from([':', ': ', ' :', ' : ']))
    comma_ws = draw(st.sampled_from([',', ', ', ' ,', ' , ']))

    # Build fields as strings
    fields = [
        '"id"' + colon_ws + id_field,
        '"amount"' + colon_ws + amount_field,
        '"name"' + colon_ws + name_field,
        '"status"' + colon_ws + status_field,
        '"tags"' + colon_ws + tags_field,
        '"child"' + colon_ws + child_field,
    ]

    # Sometimes shuffle fields order to test order sensitivity (10% chance)
    if draw(st.booleans()):
        fields = draw(st.permutations(fields))

    json_text = '{' + comma_ws.join(fields) + '}'

    return json_text.encode('utf-8')