from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum "status"
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (no escapes beyond quotes and backslash)
    def json_string(s: str) -> str:
        # minimal escaping: backslash and double quote
        esc = s.replace("\\", "\\\\").replace('"', '\\"')
        return '"' + esc + '"'

    # Helper: produce JSON array of strings
    def json_string_array(arr):
        return "[" + ",".join(json_string(e) for e in arr) + "]"

    # Recursive record generator, bounded depth 0 or 1
    def record(depth=0):
        # id: integer (required, non-null)
        # amount: string (required, non-null)
        # name: string or null, missing treated as null by all
        # status: enum string (required, non-null)
        # tags: array of strings (required, non-null), but built_value accepts null as empty list
        # child: record or null (nullable), one level recursion normally

        # We produce a dict of fields as strings (JSON fragments), then join with commas

        # id: integer, always present, but we will sometimes produce null or wrong type to test divergence
        # amount: string, always present, but sometimes null or wrong type
        # name: string or null or missing (missing treated as null by all)
        # status: enum string, always present, but sometimes invalid enum or null
        # tags: array of strings, always present, but sometimes null (only built_value accepts null)
        # child: record or null, sometimes missing (?), but spec says always present, so always present but can be null

        # Strategy for id field:
        # Mostly valid int, sometimes null or string to test type errors
        id_field = draw(st.one_of(
            st.integers(min_value=0, max_value=2**31-1).map(str),
            st.just("null"),  # null for required field (all reject)
            st.text(min_size=1, max_size=5).map(json_string),  # string instead of int (all reject)
        ))

        # amount field: string normally, sometimes int or null
        amount_field = draw(st.one_of(
            st.text(min_size=1, max_size=10).map(json_string),
            st.integers(min_value=0, max_value=10000).map(str),  # int instead of string (all reject)
            st.just("null"),  # null for required (all reject)
        ))

        # name field: string or null or missing
        # To test missing, we produce either field or omit it
        name_present = draw(st.booleans())
        if name_present:
            name_field_val = draw(st.one_of(
                st.text(min_size=0, max_size=10).map(json_string),
                st.just("null"),
            ))
            name_field = '"name":' + name_field_val
        else:
            name_field = None  # omitted

        # status field: enum string, sometimes invalid enum or null
        # valid enums:
        valid_status = st.sampled_from(statuses)
        invalid_status = st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses)
        status_val = draw(st.one_of(
            valid_status.map(json_string),
            invalid_status.map(json_string),
            st.just("null"),
        ))
        status_field = '"status":' + status_val

        # tags field: array of strings normally, sometimes null (only built_value accepts null)
        # array of strings: empty or small list of short strings
        tags_val = draw(st.one_of(
            st.lists(st.text(min_size=0, max_size=5), max_size=3).map(json_string_array),
            st.just("null"),
            # also try wrong types to confirm all reject
            st.integers(min_value=0, max_value=10).map(str),
            st.text(min_size=1, max_size=5).map(json_string),
        ))
        tags_field = '"tags":' + tags_val

        # child field: record or null
        # To keep recursion bounded, only recurse once (depth 0 or 1)
        # Also try null or wrong types (string, int) to test rejection
        if depth == 0:
            child_choice = draw(st.one_of(
                st.just("null"),
                record(depth=1),
                st.text(min_size=1, max_size=5).map(json_string),  # string instead of object
                st.integers(min_value=0, max_value=10).map(str),  # int instead of object
            ))
        else:
            # at depth 1, do not recurse further, only null or valid record with no child
            child_choice = draw(st.one_of(
                st.just("null"),
                # record with child=null at depth 2 (stop recursion)
                st.builds(lambda id_, amount, name, status, tags:
                          '{'
                          + '"id":' + str(id_)
                          + ',"amount":' + json_string(amount)
                          + (',"name":' + json_string(name) if name is not None else '')
                          + ',"status":' + json_string(status)
                          + ',"tags":' + json_string_array(tags)
                          + ',"child":null'
                          + '}',
                          st.integers(min_value=0, max_value=1000),
                          st.text(min_size=1, max_size=10),
                          st.one_of(st.none(), st.text(min_size=0, max_size=10)),
                          st.sampled_from(statuses),
                          st.lists(st.text(min_size=0, max_size=5), max_size=3)
                          ),
                st.just("null"),
            ))
        child_field = '"child":' + child_choice

        # Compose fields
        fields = [
            '"id":' + id_field,
            '"amount":' + amount_field,
        ]
        if name_field is not None:
            fields.append(name_field)
        fields.append(status_field)
        fields.append(tags_field)
        fields.append(child_field)

        # Shuffle fields to test tolerance of extra fields and order
        fields = draw(st.permutations(fields))

        obj = "{" + ",".join(fields) + "}"
        return obj

    # Generate top-level record as JSON string, then encode as bytes
    json_text = record(depth=0)
    return draw(st.just(json_text)).encode("utf-8")