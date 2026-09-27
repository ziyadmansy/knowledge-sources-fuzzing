from hypothesis import strategies as st

# Helper: JSON string escape for Hypothesis-generated strings (minimal, escapes only backslash and quote)
def json_string_escape(s: str) -> str:
    # Escape backslash and double quote for JSON string literal
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.
    """

    # Constants for enum status
    valid_statuses = ["active", "inactive", "unknown"]

    # --- Recursive record generator with bounded depth ---
    # Depth limit to avoid infinite recursion
    MAX_DEPTH = 2

    def gen_record(depth: int) -> st.SearchStrategy[str]:
        # id field:
        # Manual requires int exactly
        # json_serializable/freezed accept any num and convert via toInt()
        # built_value expects int and likely rejects non-int types
        # So try ints and floats that are integral, and floats that are non-integral
        # Also try strings that look like numbers (should cause rejection)
        id_int = st.integers(min_value=-2**31, max_value=2**31-1).map(str)
        id_float_integral = st.floats(allow_infinity=False, allow_nan=False).filter(lambda f: f.is_integer()).map(lambda f: str(int(f)))
        id_float_non_integral = st.floats(allow_infinity=False, allow_nan=False).filter(lambda f: not f.is_integer()).map(str)
        id_str_num = st.text(min_size=1, max_size=5).filter(lambda s: s.isdigit()).map(lambda s: f'"{s}"')
        # Compose id choices:
        # - int as number (no quotes)
        # - float integral as number (no quotes)
        # - float non-integral as number (no quotes)
        # - string numeric (quoted)
        id_choice = st.one_of(
            id_int,
            id_float_integral,
            id_float_non_integral,
            id_str_num,
        )

        # amount field: must be string exactly
        # Generate strings, but also try some non-string values to provoke rejection
        # But mostly strings to keep document almost valid
        amount_str = st.text(min_size=0, max_size=10).map(json_string_escape).map(lambda s: f'"{s}"')
        amount_non_str = st.one_of(
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.floats(allow_infinity=False, allow_nan=False).map(str),
            st.booleans().map(lambda b: "true" if b else "false"),
            st.just("null"),
            st.just("[]"),
            st.just("{}"),
        )
        # Bias towards string but sometimes non-string
        amount_choice = st.one_of(
            amount_str,
            amount_non_str,
        )

        # name field: string or null
        # Generate either null or string (escaped)
        name_choice = st.one_of(
            st.just("null"),
            st.text(min_size=0, max_size=10).map(json_string_escape).map(lambda s: f'"{s}"'),
        )

        # status field: one of valid_statuses exactly, or near misses (typos, case variants)
        # Manual and built_value throw raw ArgumentError on unknown enum strings (Tier B)
        # json_serializable/freezed throw documented CheckedFromJsonException
        # So generate mostly valid, sometimes invalid with subtle typos or case changes
        # Also try numeric or null to provoke rejection
        def near_miss_status():
            # Insert a typo or case change
            base = draw(st.sampled_from(valid_statuses))
            # Change one char or case
            if len(base) > 1:
                i = draw(st.integers(min_value=0, max_value=len(base)-1))
                c = base[i]
                # Change case if alpha
                if c.isalpha():
                    c2 = c.upper() if c.islower() else c.lower()
                else:
                    c2 = c
                # Replace char at i
                s = base[:i] + c2 + base[i+1:]
                return s
            else:
                # single char, just uppercase
                return base.upper()

        status_choice = st.one_of(
            st.sampled_from(valid_statuses),
            st.just("null"),  # invalid but JSON valid
            st.just(""),      # empty string invalid
            st.text(min_size=1, max_size=7).filter(lambda s: s not in valid_statuses).map(lambda s: s),
            st.builds(lambda: near_miss_status()),
        ).map(lambda s: f'"{s}"')

        # tags field: array of strings
        # Manual casts to List then maps elements as String
        # json_serializable/freezed cast to List<dynamic> then map to String
        # built_value expects BuiltList<String> and rejects non-list or lists with non-string elements
        # So generate mostly list of strings, sometimes list with non-string elements, sometimes non-list (e.g. string or null)
        # To provoke divergence, try empty list, list with null, list with int, list with float, list with bool, list with nested array
        # Also try non-list values (string, null, number)
        def gen_tags_list():
            # Elements mostly strings, sometimes non-string
            elem_str = st.text(min_size=0, max_size=5).map(json_string_escape).map(lambda s: f'"{s}"')
            elem_non_str = st.one_of(
                st.integers(min_value=-10, max_value=10).map(str),
                st.floats(allow_infinity=False, allow_nan=False).map(str),
                st.just("null"),
                st.just("true"),
                st.just("false"),
                st.just("[]"),
                st.just("{}"),
            )
            # Mix elements with bias towards strings
            elems = st.lists(st.one_of(elem_str, elem_non_str), min_size=0, max_size=5)
            return elems.map(lambda lst: "[" + ",".join(lst) + "]")

        tags_choice = st.one_of(
            gen_tags_list(),
            # Non-list values for tags
            st.text(min_size=0, max_size=10).map(json_string_escape).map(lambda s: f'"{s}"'),
            st.just("null"),
            st.integers(min_value=-10, max_value=10).map(str),
            st.floats(allow_infinity=False, allow_nan=False).map(str),
        )

        # child field: null or nested record (one level recursion)
        # To keep bounded recursion, only recurse if depth < MAX_DEPTH
        if depth >= MAX_DEPTH:
            child_choice = st.just("null")
        else:
            # Sometimes null, sometimes nested record
            child_choice = st.one_of(
                st.just("null"),
                gen_record(depth + 1),
            )

        # Compose the JSON object string with all fields in fixed order
        # id: as number or string (no quotes for numbers, quotes for string)
        # amount: string (quoted) or non-string (unquoted)
        # name: string or null
        # status: string (quoted)
        # tags: array or non-array
        # child: null or nested record

        # Draw all fields
        id_val = draw(id_choice)
        amount_val = draw(amount_choice)
        name_val = draw(name_choice)
        status_val = draw(status_choice)
        tags_val = draw(tags_choice)
        child_val = draw(child_choice)

        # Build JSON object string
        # All keys quoted, colon, values as drawn (already JSON fragments)
        json_obj = (
            '{'
            f'"id":{id_val},'
            f'"amount":{amount_val},'
            f'"name":{name_val},'
            f'"status":{status_val},'
            f'"tags":{tags_val},'
            f'"child":{child_val}'
            '}'
        )
        return json_obj

    # Generate top-level record at depth 0
    json_text = draw(gen_record(0))

    # Return bytes
    return json_text.encode("utf-8")