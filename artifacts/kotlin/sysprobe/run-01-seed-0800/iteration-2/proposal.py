from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for enum and nullability
    STATUS_VALUES = ["active", "inactive", "unknown"]
    # We will produce JSON text manually, carefully controlling spacing and quotes.

    # Helper: produce JSON string literal with proper escaping for simple ASCII alphanum + space + punctuation safe chars
    # We restrict generated strings to safe chars to avoid escaping complexity.
    safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_."

    def json_string(s: str) -> str:
        # Escape backslash and quote only (minimal escaping)
        s = s.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{s}\""

    # Strategy for JSON string values (for "amount", "name", and tags)
    # "amount" is string but can be number or null in some implementations, so we vary that.
    # "name" nullable string or null.
    # "tags" array of strings (empty or non-empty)
    # "status" enum string or invalid string or null (to trigger divergences)
    # "id" integer (required)
    # "child" either null or nested record (one level recursion max)

    # To control recursion depth, pass depth param
    def record_strategy(depth: int):
        # id: integer, required, but we will sometimes omit or null it to trigger divergences
        # amount: string required, but can be number or null to trigger divergences
        # name: nullable string or null
        # status: enum string required, but can be invalid string or null to trigger divergences
        # tags: array of strings required, but can be missing or null to trigger divergences
        # child: nullable record or null or missing (to trigger divergences)

        # id field: integer or null or missing (simulate missing by omitting field)
        # We produce a tuple (field_name, field_value_or_None_for_missing)
        # To produce missing fields, we omit them from JSON text.

        # We produce a dict of fields (field_name -> value or None for missing)
        # Then serialize to JSON text.

        # id field: mostly integer, sometimes null or missing
        id_val = draw(st.one_of(
            st.integers(min_value=0, max_value=1000),
            st.just(None),  # null
            st.just("missing")  # omit field
        ))

        # amount field: string normally, but sometimes number, null, or missing
        # To trigger divergences:
        # Gson accepts number or null for amount string field
        # kotlinx rejects number for string field
        # Gson accepts null for non-nullable string, others reject null
        # Moshi rejects null or missing
        amount_val = draw(st.one_of(
            st.text(alphabet=safe_chars, min_size=1, max_size=10),
            st.integers(min_value=0, max_value=1000).map(str),  # number as string (valid)
            st.integers(min_value=0, max_value=1000),  # number (not string)
            st.just(None),
            st.just("missing")
        ))

        # name field: nullable string or null or missing
        name_val = draw(st.one_of(
            st.none(),
            st.text(alphabet=safe_chars, min_size=0, max_size=10),
            st.just("missing")
        ))

        # status field: enum string or invalid string or null or missing
        status_val = draw(st.one_of(
            st.sampled_from(STATUS_VALUES),
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10).filter(lambda x: x not in STATUS_VALUES),
            st.none(),
            st.just("missing")
        ))

        # tags field: array of strings or null or missing
        # tags required non-null array normally
        # Gson accepts null or missing as null
        # Moshi, kotlinx reject null or missing
        tags_val = draw(st.one_of(
            st.lists(st.text(alphabet=safe_chars, min_size=1, max_size=10), max_size=3),
            st.none(),
            st.just("missing")
        ))

        # child field: nullable record or null or missing
        # To avoid deep recursion, only recurse if depth < 1
        if depth < 1:
            child_val = draw(st.one_of(
                record_strategy(depth + 1),
                st.none(),
                st.just("missing")
            ))
        else:
            child_val = draw(st.one_of(
                st.none(),
                st.just("missing")
            ))

        # Compose fields dict with possible missing fields (value == "missing" means omit)
        fields = {}

        if id_val != "missing":
            # id: if None, output null; else integer
            fields["id"] = id_val
        if amount_val != "missing":
            fields["amount"] = amount_val
        if name_val != "missing":
            fields["name"] = name_val
        if status_val != "missing":
            fields["status"] = status_val
        if tags_val != "missing":
            fields["tags"] = tags_val
        if child_val != "missing":
            fields["child"] = child_val

        # Serialize fields to JSON text
        # Helper to serialize a value to JSON text
        def serialize_json_value(v):
            if v is None:
                return "null"
            elif isinstance(v, str):
                # Could be a number string or normal string
                # We must distinguish number vs string for amount field
                # But we do not know field here, so treat all strings as JSON strings
                return json_string(v)
            elif isinstance(v, int):
                return str(v)
            elif isinstance(v, list):
                # list of strings
                items = ",".join(serialize_json_value(x) for x in v)
                return f"[{items}]"
            elif isinstance(v, dict):
                # nested record
                items = []
                for k, val in v.items():
                    items.append(json_string(k) + ":" + serialize_json_value(val))
                return "{" + ",".join(items) + "}"
            else:
                # Should not happen
                return "null"

        # Compose JSON object text
        items = []
        for k, v in fields.items():
            # Special case: amount field can be int (number) or string
            # We want to output number without quotes if int
            # But if string, output with quotes
            if k == "amount":
                if isinstance(v, int):
                    val_text = str(v)
                elif v is None:
                    val_text = "null"
                else:
                    val_text = json_string(str(v))
            else:
                val_text = serialize_json_value(v)
            items.append(json_string(k) + ":" + val_text)

        json_text = "{" + ",".join(items) + "}"

        return json_text.encode("utf-8")

    return record_strategy(0)