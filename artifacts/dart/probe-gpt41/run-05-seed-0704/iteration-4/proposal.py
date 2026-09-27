from hypothesis import strategies as st

# Constants for "status" field allowed values
STATUS_VALUES = ["active", "inactive", "unknown"]

# Helper to produce a JSON string literal from a Python string,
# escaping backslash and double quotes minimally for valid JSON.
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote
    s_esc = s.replace("\\", "\\\\").replace('"', '\\"')
    # Also escape control characters minimally (e.g. \n, \r, \t)
    s_esc = s_esc.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return '"' + s_esc + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to trigger behavioral divergence between four Dart JSON deserializers:
    manual, json_serializable, freezed, built_value.

    Strategy:
    - id: integer (always correct)
    - amount: string (always correct)
    - name: string or null or missing (missing interpreted as null by all)
    - status: one of allowed strings, or null, or missing (to test rejection modes)
    - tags: array of strings, or missing, or object (to test built_value acceptance vs others)
    - child: null or nested record or missing or empty object (to test rejection modes)
    - Introduce exactly one or two subtle deviations per document to maximize divergence.
    """

    # Recursive depth limit for child records
    max_depth = 1

    # Internal recursive builder for record JSON text (string)
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # id: always integer
        id_val = st.integers(min_value=0, max_value=1000000)

        # amount: always string (decimal-ish)
        amount_val = st.text(min_size=1, max_size=10).map(lambda s: s if s.strip() else "0").map(lambda s: s.replace('"', ''))  # no quotes inside

        # name: string or null or missing (missing interpreted as null)
        # To induce divergence, sometimes omit "name" field
        name_field = st.one_of(
            st.none().map(lambda _: None),  # null
            st.text(min_size=0, max_size=20).map(lambda s: s if s != "" else "n"),  # string
            st.just("missing")  # omit field
        )

        # status: allowed strings, or null, or missing, or invalid string to test rejection
        status_field = st.one_of(
            st.sampled_from(STATUS_VALUES),
            st.none(),
            st.just("missing"),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES)  # invalid string
        )

        # tags: array of strings, or missing, or object (to test built_value acceptance)
        # To induce divergence, sometimes produce object instead of array
        tags_field = st.one_of(
            st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5),
            st.just("missing"),
            st.dictionaries(st.text(min_size=1, max_size=5), st.text(min_size=1, max_size=5), max_size=3)
        )

        # child: null, nested record, empty object, or missing
        # empty object is {} (invalid child)
        # missing child field to test behavior
        if depth < max_depth:
            child_field = st.one_of(
                st.none(),
                record_json(depth + 1),
                st.just("{}"),
                st.just("missing")
            )
        else:
            # At max depth, no further nesting
            child_field = st.one_of(
                st.none(),
                st.just("missing"),
                st.just("{}")
            )

        # Compose all fields together, then build JSON string with exactly one or two subtle deviations
        @st.composite
        def build_record(draw):
            id_v = draw(id_val)
            amount_v = draw(amount_val)
            name_v = draw(name_field)
            status_v = draw(status_field)
            tags_v = draw(tags_field)
            child_v = draw(child_field)

            # Build JSON fields as strings
            fields = []

            # id: always present and integer
            fields.append('"id":' + str(id_v))

            # amount: always present and string
            fields.append('"amount":' + json_string_literal(amount_v))

            # name: string or null or missing
            if name_v != "missing":
                if name_v is None:
                    fields.append('"name":null')
                else:
                    fields.append('"name":' + json_string_literal(name_v))
            # else omit "name"

            # status: string from allowed, null, missing, or invalid string
            if status_v != "missing":
                if status_v is None:
                    fields.append('"status":null')
                else:
                    fields.append('"status":' + json_string_literal(status_v))
            # else omit "status"

            # tags: list of strings, missing, or object
            if tags_v != "missing":
                if isinstance(tags_v, dict):
                    # object as tags field
                    # Build JSON object string
                    obj_items = []
                    for k, v in tags_v.items():
                        obj_items.append(json_string_literal(k) + ":" + json_string_literal(v))
                    obj_str = "{" + ",".join(obj_items) + "}"
                    fields.append('"tags":' + obj_str)
                else:
                    # list of strings
                    arr_items = [json_string_literal(s) for s in tags_v]
                    arr_str = "[" + ",".join(arr_items) + "]"
                    fields.append('"tags":' + arr_str)
            # else omit "tags"

            # child: null, nested record string, empty object, or missing
            if child_v != "missing":
                if child_v is None:
                    fields.append('"child":null')
                elif child_v == "{}":
                    fields.append('"child":{}')
                else:
                    # nested record string (already JSON object string)
                    fields.append('"child":' + child_v)
            # else omit "child"

            # Shuffle fields order to avoid positional bias
            import random
            random.shuffle(fields)

            # Join fields with commas
            json_obj = "{" + ",".join(fields) + "}"

            return json_obj

        return build_record()

    # Draw the top-level record JSON string
    json_str = draw(record_json(0))

    # Return as bytes
    return json_str.encode("utf-8")