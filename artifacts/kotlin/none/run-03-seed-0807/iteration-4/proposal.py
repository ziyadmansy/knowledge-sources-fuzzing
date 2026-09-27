from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum
    statuses = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (no escapes except \")
    # We avoid importing json, so do minimal escaping for quotes and backslashes.
    def json_string(s: str) -> str:
        # Escape backslash and double quote
        s = s.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{s}\""

    # Helper: produce JSON array of strings
    def json_array_of_strings(lst):
        # lst is list of strings or possibly non-strings (to cause divergence)
        # We assume elements are already JSON text fragments
        return "[" + ",".join(lst) + "]"

    # Helper: produce JSON object from dict of key->value (value is JSON text)
    def json_object(d):
        # keys are strings, values are JSON text fragments
        # keys must be JSON strings
        items = []
        for k, v in d.items():
            items.append(json_string(k) + ":" + v)
        return "{" + ",".join(items) + "}"

    # We will produce a record as JSON text (string), with bounded recursion depth
    # We produce "almost valid" records with one or two fields slightly off:
    # - wrong type (e.g. amount as number instead of string)
    # - missing field (to test missing vs present)
    # - null vs string or object
    # - enum with invalid string
    # - tags array with wrong element types or empty
    # - child null or nested record (depth 1 only)

    # To keep recursion bounded, we allow child to be null or a record with no child

    # Strategy for id: normally integer, but sometimes string or float to cause divergence
    id_strategy = st.one_of(
        st.integers(min_value=0, max_value=10**9).map(str),
        st.floats(allow_nan=False, allow_infinity=False).map(lambda f: str(f)),
        st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit()),  # invalid string
    )

    # Strategy for amount: normally string representing a decimal number, but sometimes number or null
    amount_strategy = st.one_of(
        # valid decimal strings
        st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789.-" for c in s)).map(json_string),
        # number (int or float)
        st.one_of(
            st.integers(min_value=-1000, max_value=1000).map(str),
            st.floats(allow_nan=False, allow_infinity=False).map(lambda f: str(f)),
        ),
        # null literal
        st.just("null"),
        # invalid string (non-numeric)
        st.text(min_size=1, max_size=5).filter(lambda s: any(c not in "0123456789.-" for c in s)).map(json_string),
    )

    # Strategy for name: string or null or number (to cause divergence)
    name_strategy = st.one_of(
        st.none().map(lambda _: "null"),
        st.text(min_size=0, max_size=10).map(json_string),
        st.integers(min_value=0, max_value=1000).map(str),
    )

    # Strategy for status: valid enum string or invalid string or null
    status_strategy = st.one_of(
        st.sampled_from(statuses).map(json_string),
        st.text(min_size=1, max_size=7).filter(lambda s: s not in statuses).map(json_string),
        st.just("null"),
    )

    # Strategy for tags: array of strings, or array with non-string elements, or null
    # Elements can be valid strings or numbers or null to cause divergence
    tag_element_strategy = st.one_of(
        st.text(min_size=0, max_size=5).map(json_string),
        st.integers(min_value=0, max_value=100).map(str),
        st.just("null"),
    )
    tags_strategy = st.one_of(
        st.lists(tag_element_strategy, min_size=0, max_size=5).map(json_array_of_strings),
        st.just("null"),
    )

    # Recursive strategy for child: either null or a record with no child (to keep depth 1)
    # We produce a record with child=null only here to avoid deep recursion
    # We reuse the same field strategies but child is always null here
    def child_record_strategy():
        # id as integer string only (to keep child simpler)
        child_id = st.integers(min_value=0, max_value=10**9).map(str)
        child_amount = st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789.-" for c in s)).map(json_string)
        child_name = st.one_of(st.none().map(lambda _: "null"), st.text(min_size=0, max_size=10).map(json_string))
        child_status = st.sampled_from(statuses).map(json_string)
        child_tags = st.lists(st.text(min_size=0, max_size=5).map(json_string), min_size=0, max_size=5).map(json_array_of_strings)
        child_child = st.just("null")

        return st.tuples(child_id, child_amount, child_name, child_status, child_tags, child_child).map(
            lambda t: json_object({
                "id": t[0],
                "amount": t[1],
                "name": t[2],
                "status": t[3],
                "tags": t[4],
                "child": t[5],
            })
        )

    # Strategy for child field: null or child record
    child_strategy = st.one_of(
        st.just("null"),
        child_record_strategy(),
    )

    # Now combine all fields into a record, but with a small chance to omit one field (to test missing)
    # We produce a dict of field -> JSON text or omit field
    # We omit at most one field per record to keep "almost well-formed"
    # We also allow one field to be replaced by a wrong type or null as above

    # Draw all fields first
    id_val = draw(id_strategy)
    amount_val = draw(amount_strategy)
    name_val = draw(name_strategy)
    status_val = draw(status_strategy)
    tags_val = draw(tags_strategy)
    child_val = draw(child_strategy)

    fields = {
        "id": id_val,
        "amount": amount_val,
        "name": name_val,
        "status": status_val,
        "tags": tags_val,
        "child": child_val,
    }

    # Decide if we omit one field (10% chance)
    omit_field = draw(st.one_of(st.none(), st.sampled_from(list(fields.keys()))))
    if omit_field is not None:
        del fields[omit_field]

    # Compose JSON object text
    json_text = json_object(fields)

    # Return bytes
    return json_text.encode("utf-8")