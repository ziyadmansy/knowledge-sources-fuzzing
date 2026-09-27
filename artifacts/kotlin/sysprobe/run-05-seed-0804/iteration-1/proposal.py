from hypothesis import strategies as st

# Helper: JSON string escape for double quotes and backslash only (minimal)
def json_string_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    # To keep recursion bounded, pass depth parameter internally
    def record(draw, depth=0):
        # id: integer or null or missing (to explore divergence)
        # amount: string or integer (coerced to string by some), null, missing
        # name: string or null or missing
        # status: enum string or unknown string or null or missing
        # tags: array of strings or null or missing
        # child: record or null or missing (only one level recursion normally)
        # We produce a dict of fields, then serialize manually.

        # Control missingness and nullness per known divergence hints:
        # id: Gson and Jackson accept null or missing as 0; Moshi and kotlinx reject null/missing
        id_choice = draw(st.sampled_from([
            ("present_int", st.integers(min_value=0, max_value=10000)),
            ("present_null", st.just(None)),
            ("missing", st.just("missing")),
        ]))
        if id_choice[0] == "present_int":
            id_val = draw(id_choice[1])
        elif id_choice[0] == "present_null":
            id_val = None
        else:
            id_val = "missing"

        # amount: string or integer (coerced by Gson/Jackson/Moshi), null (only Gson accepts), missing (Gson/Jackson accept missing?)
        # Known: Gson accepts null amount, others reject; Gson/Jackson/Moshi accept integer coerced to string; kotlinx rejects integer or null
        amount_choice = draw(st.sampled_from([
            ("present_string", st.text(min_size=0, max_size=10)),
            ("present_int", st.integers(min_value=0, max_value=100000)),
            ("present_null", st.just(None)),
            ("missing", st.just("missing")),
        ]))
        if amount_choice[0] == "present_string":
            amount_val = draw(amount_choice[1])
        elif amount_choice[0] == "present_int":
            amount_val = draw(amount_choice[1])
        elif amount_choice[0] == "present_null":
            amount_val = None
        else:
            amount_val = "missing"

        # name: string or null or missing
        name_choice = draw(st.sampled_from([
            ("present_string", st.text(min_size=0, max_size=10)),
            ("present_null", st.just(None)),
            ("missing", st.just("missing")),
        ]))
        if name_choice[0] == "present_string":
            name_val = draw(name_choice[1])
        elif name_choice[0] == "present_null":
            name_val = None
        else:
            name_val = "missing"

        # status: enum string ("active", "inactive", "unknown"), unknown string, null, missing
        # Gson accepts unknown enum as null; others reject unknown or case variant; Gson rejects missing? Known: Moshi/kotlinx reject missing; Gson/Jackson accept missing?
        status_enum = ["active", "inactive", "unknown"]
        status_choice = draw(st.sampled_from([
            ("present_enum", st.sampled_from(status_enum)),
            ("present_unknown", st.text(min_size=1, max_size=10).filter(lambda s: s.lower() not in status_enum)),
            ("present_null", st.just(None)),
            ("missing", st.just("missing")),
        ]))
        if status_choice[0] == "present_enum":
            status_val = draw(status_choice[1])
        elif status_choice[0] == "present_unknown":
            status_val = draw(status_choice[1])
        elif status_choice[0] == "present_null":
            status_val = None
        else:
            status_val = "missing"

        # tags: array of strings or null or missing
        # Known: Gson/Jackson accept missing or null; Moshi/kotlinx reject missing; Moshi accepts null? Known: Moshi rejects missing tags; Gson/Jackson accept missing or null
        tags_choice = draw(st.sampled_from([
            ("present_array", st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=3)),
            ("present_null", st.just(None)),
            ("missing", st.just("missing")),
        ]))
        if tags_choice[0] == "present_array":
            tags_val = draw(tags_choice[1])
        elif tags_choice[0] == "present_null":
            tags_val = None
        else:
            tags_val = "missing"

        # child: record or null or missing; only one level recursion normally
        # Known: Gson/Jackson accept missing or null child; Moshi/kotlinx reject missing child
        # Also known: nested fields behave like top-level for null/missing
        if depth == 0:
            child_choice = draw(st.sampled_from([
                ("present_record", st.just(True)),
                ("present_null", st.just(None)),
                ("missing", st.just("missing")),
            ]))
            if child_choice[0] == "present_record":
                child_val = record(draw, depth=depth+1)
            elif child_choice[0] == "present_null":
                child_val = None
            else:
                child_val = "missing"
        else:
            # At depth 1, no further recursion; child must be null or missing or absent
            child_choice = draw(st.sampled_from([
                ("present_null", st.just(None)),
                ("missing", st.just("missing")),
            ]))
            if child_choice[0] == "present_null":
                child_val = None
            else:
                child_val = "missing"

        # Compose JSON text manually
        # Helper to serialize a JSON value (string, int, null, array, object, or missing)
        def serialize_json_value(v):
            if v == "missing":
                return None
            if v is None:
                return "null"
            if isinstance(v, str):
                return '"' + json_string_escape(v) + '"'
            if isinstance(v, int):
                return str(v)
            if isinstance(v, list):
                items = []
                for item in v:
                    items.append('"' + json_string_escape(item) + '"')
                return "[" + ",".join(items) + "]"
            if isinstance(v, dict):
                # v is a dict of fields, serialize with keys sorted for determinism
                items = []
                for k in sorted(v.keys()):
                    sv = serialize_json_value(v[k])
                    if sv is not None:
                        items.append('"' + k + '":' + sv)
                return "{" + ",".join(items) + "}"
            raise ValueError("Unexpected type in serialize_json_value")

        # Compose top-level dict
        top = {}

        if id_val != "missing":
            top["id"] = id_val
        if amount_val != "missing":
            top["amount"] = amount_val
        if name_val != "missing":
            top["name"] = name_val
        if status_val != "missing":
            top["status"] = status_val
        if tags_val != "missing":
            top["tags"] = tags_val
        if child_val != "missing":
            top["child"] = child_val

        json_text = serialize_json_value(top)
        return json_text.encode("utf-8")

    return record(draw)