from hypothesis import strategies as st

# Helper: JSON string escaping minimal for ASCII control chars and quotes/backslash
def json_string_escape(s: str) -> str:
    # Escape backslash and double quote, and control chars \b \f \n \r \t
    # We do not need full unicode escaping here, just minimal for valid JSON strings.
    # Hypothesis strings are unicode, but we restrict to ASCII printable for simplicity.
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\b', '\\b')
    s = s.replace('\f', '\\f')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s

# Compose a JSON string literal from a Python string
def json_string_literal(s: str) -> str:
    return '"' + json_string_escape(s) + '"'

# Compose a JSON array of strings from a list of strings
def json_array_of_strings(lst) -> str:
    # lst is list of strings (already escaped)
    return '[' + ','.join(lst) + ']'

# Compose a JSON object from list of (key, value) pairs (both strings)
def json_object(pairs) -> str:
    # pairs: list of (key, value) strings, keys must be JSON strings
    # keys are already quoted strings
    return '{' + ','.join(k + ':' + v for k, v in pairs) + '}'

@st.composite
def generated_json(draw) -> bytes:
    # We produce syntactically valid JSON objects with the record schema:
    # {
    #   "id": <integer>,
    #   "amount": <string>,
    #   "name": <string or null>,
    #   "status": <"active"|"inactive"|"unknown">,
    #   "tags": <array of strings>,
    #   "child": <Record or null>
    # }
    #
    # We want to produce documents that are almost well-formed but with
    # subtle variations to trigger divergence or undocumented exceptions.
    #
    # Strategy:
    # - id: integer normally, but sometimes boundary or large int
    # - amount: string normally, but sometimes empty string, or string with escape chars
    # - name: string or null, sometimes empty string, sometimes unicode or control chars
    # - status: one of enum, but also test boundary strings (e.g. "active " with space)
    # - tags: array of strings, sometimes empty array, sometimes strings with tricky chars,
    #         sometimes duplicate strings, sometimes empty strings
    # - child: null or nested record, but limit recursion depth to 1 (one level)
    #
    # We also try to produce subtle variations:
    # - omit optional fields? No, all fields always present per spec.
    # - duplicate keys? Known to be handled consistently, so no need to add duplicates here.
    # - subtle type boundary: e.g. "id" as int but very large, or "amount" as string "100" vs "100.0"
    # - "status" with trailing spaces or different case (should reject)
    # - "tags" with empty strings allowed, but no nulls
    # - "child" with null or valid nested record, or with one field subtly wrong (should reject)
    #
    # We produce a valid JSON string, then encode as bytes.

    # Enum values for status
    statuses = ["active", "inactive", "unknown"]

    # Draw id: integer, mostly small, sometimes large or boundary
    id_val = draw(
        st.one_of(
            st.integers(min_value=0, max_value=1000),
            st.just(0),
            st.just(2**31 - 1),
            st.just(-1),
        )
    )

    # Draw amount: string, sometimes empty, sometimes numeric string, sometimes with escapes
    amount_str = draw(
        st.one_of(
            st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])),
            st.just(""),
            st.just("100"),
            st.just("100.0"),
            st.just("0"),
            st.just("\n100"),
            st.just(" 100 "),
        )
    )

    # Draw name: string or null, sometimes empty string, sometimes unicode or control chars
    name_val = draw(
        st.one_of(
            st.none(),
            st.text(min_size=0, max_size=15, alphabet=st.characters(blacklist_characters=['"','\\'])),
            st.just(""),
            st.just("\tNameWithTab"),
            st.just("Name\nWithNewline"),
        )
    )

    # Draw status: mostly valid enum, sometimes invalid with trailing space or case change
    status_val = draw(
        st.one_of(
            st.sampled_from(statuses),
            st.just("active "),  # invalid trailing space
            st.just("Active"),  # invalid case
            st.just("inactive\n"),  # invalid newline
        )
    )

    # Draw tags: array of strings, empty allowed, strings can be empty or with spaces
    # No nulls allowed in tags (known rejection)
    tags_len = draw(st.integers(min_value=0, max_value=5))
    tags_list = []
    for _ in range(tags_len):
        tag = draw(
            st.one_of(
                st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])),
                st.just(""),
                st.just("tag with spaces"),
                st.just("tag\nwithnewline"),
            )
        )
        tags_list.append(json_string_literal(tag))

    # Compose tags JSON array string
    tags_json = json_array_of_strings(tags_list)

    # Compose child: null or nested record (one level only)
    # Nested record fields mostly valid, but sometimes subtle error in one field to cause divergence
    child_is_null = draw(st.booleans())
    if child_is_null:
        child_json = "null"
    else:
        # Nested record fields:
        # id: integer (small)
        child_id = draw(st.integers(min_value=0, max_value=1000))
        # amount: string (simple)
        child_amount = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])))
        # name: string or null
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\']))))
        # status: valid enum or subtle invalid
        child_status = draw(st.one_of(st.sampled_from(statuses), st.just("unknown "), st.just("UNKNOWN")))
        # tags: array of strings, empty allowed
        child_tags_len = draw(st.integers(min_value=0, max_value=3))
        child_tags_list = []
        for _ in range(child_tags_len):
            t = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(blacklist_characters=['"','\\'])))
            child_tags_list.append(json_string_literal(t))
        child_tags_json = json_array_of_strings(child_tags_list)

        # Compose child JSON object
        child_pairs = [
            (json_string_literal("id"), str(child_id)),
            (json_string_literal("amount"), json_string_literal(child_amount)),
            (json_string_literal("name"), "null" if child_name is None else json_string_literal(child_name)),
            (json_string_literal("status"), json_string_literal(child_status)),
            (json_string_literal("tags"), child_tags_json),
            (json_string_literal("child"), "null"),
        ]
        child_json = json_object(child_pairs)

    # Compose top-level JSON object
    pairs = [
        (json_string_literal("id"), str(id_val)),
        (json_string_literal("amount"), json_string_literal(amount_str)),
        (json_string_literal("name"), "null" if name_val is None else json_string_literal(name_val)),
        (json_string_literal("status"), json_string_literal(status_val)),
        (json_string_literal("tags"), tags_json),
        (json_string_literal("child"), child_json),
    ]

    json_text = json_object(pairs)
    return json_text.encode("utf-8")