from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for "status" allowed values
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal with proper escaping of quotes and backslashes
    def json_string_literal(s: str) -> str:
        # Minimal escaping for JSON string: backslash and double quote
        # Also escape control chars \b \f \n \r \t for safety
        replacements = {
            '\\': '\\\\',
            '"': '\\"',
            '\b': '\\b',
            '\f': '\\f',
            '\n': '\\n',
            '\r': '\\r',
            '\t': '\\t',
        }
        res = []
        for c in s:
            if c in replacements:
                res.append(replacements[c])
            elif ord(c) < 0x20:
                # Control chars as \u00XX
                res.append('\\u%04x' % ord(c))
            else:
                res.append(c)
        return '"' + ''.join(res) + '"'

    # Compose a JSON array of strings
    def json_array_of_strings(arr):
        # arr is list of strings
        return '[' + ','.join(json_string_literal(x) for x in arr) + ']'

    # Compose a JSON value for "name" field: either null or string
    # We want to sometimes produce null, sometimes string, sometimes a subtle deviation
    # But from known probes, non-null non-string is rejected by all.
    # So we only produce null or string here.
    def json_name():
        # 20% null, 80% string
        return draw(st.one_of(
            st.just("null"),
            st.text(min_size=0, max_size=20).map(json_string_literal)
        ))

    # Compose a JSON value for "status" field
    # We want to sometimes produce a valid status string,
    # sometimes an invalid string close to valid ones (e.g. case difference, extra whitespace)
    # to try to cause divergence.
    # But from probes, all reject invalid status with different error types.
    # So maybe produce valid or valid with whitespace around (which might be accepted differently)
    # or valid with unicode homoglyphs? But homoglyphs are different strings.
    # Let's produce either exact valid, or valid with leading/trailing spaces (which is invalid)
    # or valid with different case (e.g. "Active") which is invalid.
    # This might cause divergence if some trim or case-insensitive.
    def json_status():
        base = draw(st.sampled_from(statuses))
        variant = draw(st.integers(min_value=0, max_value=2))
        if variant == 0:
            # exact valid
            return json_string_literal(base)
        elif variant == 1:
            # leading/trailing spaces
            return json_string_literal(" " + base + " ")
        else:
            # different case (capitalize first letter)
            return json_string_literal(base.capitalize())

    # Compose a JSON value for "tags" field: array of strings
    # We want to produce valid arrays of strings, but also try empty array,
    # array with empty strings, array with strings containing spaces or unicode.
    # All probes say non-array or non-string elements rejected by all.
    # So only produce arrays of strings.
    def json_tags():
        # array length 0..5
        arr = draw(st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5))
        return json_array_of_strings(arr)

    # Compose a JSON value for "amount" field: string
    # We want to produce string, but also try numeric strings, empty string, strings with spaces.
    # All probes say int instead of string rejected by all.
    # So only string.
    def json_amount():
        # string with digits or empty or decimal or currency symbol
        s = draw(st.one_of(
            st.text(alphabet="0123456789", min_size=1, max_size=10),
            st.text(alphabet="0123456789.", min_size=1, max_size=10),
            st.text(min_size=0, max_size=10),
            st.just("$100.00"),
            st.just("0"),
            st.just(""),
        ))
        return json_string_literal(s)

    # Compose a JSON value for "id" field: integer
    # We want to produce int, but also try boundary values like 0, negative, large int
    # All probes say string instead of int rejected by all.
    # So only int here.
    def json_id():
        i = draw(st.integers(min_value=0, max_value=2**31-1))
        return str(i)

    # Compose a JSON value for "child" field:
    # null or a nested record (one level recursion only)
    # We want to sometimes produce null, sometimes a nested record with one level child=null
    # or nested record with child=null but with one field subtly off to cause divergence
    # or nested record with extra unknown fields (allowed)
    # or nested record with missing fields (not allowed, all reject)
    # So produce either null or valid nested record with one subtle deviation in nested record
    # or nested record with extra unknown fields
    # We do NOT produce nested child deeper than one level (all reject)
    # We do NOT produce empty object for child (all reject)
    # We want to produce subtle deviations in nested record fields to cause divergence

    # To do this, we define a helper to produce a nested record JSON string (without bytes)
    def json_record(allow_subtle_deviation: bool):
        # Compose fields for a record as JSON key:value pairs (strings)
        # allow_subtle_deviation: if True, one field may be subtly off to cause divergence
        # We pick one field at random to deviate, or none

        # Pick which field to deviate (or none)
        fields = ["id", "amount", "name", "status", "tags", "child"]
        deviate_field = None
        if allow_subtle_deviation:
            # 50% chance to deviate one field
            if draw(st.booleans()):
                deviate_field = draw(st.sampled_from(fields))

        # Compose each field
        parts = []

        # id
        if deviate_field == "id":
            # produce int as string (invalid type)
            id_val = draw(st.text(min_size=1, max_size=5))
            parts.append('"id":' + json_string_literal(id_val))
        else:
            parts.append('"id":' + json_id())

        # amount
        if deviate_field == "amount":
            # produce int instead of string
            amount_val = draw(st.integers(min_value=0, max_value=10000))
            parts.append('"amount":' + str(amount_val))
        else:
            parts.append('"amount":' + json_amount())

        # name
        if deviate_field == "name":
            # produce int instead of string or null
            name_val = draw(st.integers(min_value=0, max_value=1000))
            parts.append('"name":' + str(name_val))
        else:
            parts.append('"name":' + json_name())

        # status
        if deviate_field == "status":
            # produce invalid string not in allowed set
            invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda x: x not in statuses))
            parts.append('"status":' + json_string_literal(invalid_status))
        else:
            parts.append('"status":' + json_status())

        # tags
        if deviate_field == "tags":
            # produce array with one non-string element (int)
            parts.append('"tags":[1]')
        else:
            parts.append('"tags":' + json_tags())

        # child
        if deviate_field == "child":
            # produce empty object {} (invalid)
            parts.append('"child":{}')
        else:
            # child is either null or nested record with no deviation
            # To avoid infinite recursion, child here must have allow_subtle_deviation=False
            child_null = draw(st.booleans())
            if child_null:
                parts.append('"child":null')
            else:
                parts.append('"child":' + json_record(allow_subtle_deviation=False))

        # Compose JSON object string
        return '{' + ','.join(parts) + '}'

    # Compose top-level record, allow subtle deviation to cause divergence
    json_text = json_record(allow_subtle_deviation=True)

    # Return bytes
    return json_text.encode("utf-8")