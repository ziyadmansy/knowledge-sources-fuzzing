from hypothesis import strategies as st

# Helper: JSON string with proper escaping of quotes and backslashes (minimal)
def json_string(s: str) -> str:
    # Escape backslash and double quote for JSON string literal
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, matching the Record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.

    Schema:
    {
      "id": <integer>,
      "amount": <string>,
      "name": <string or null>,
      "status": <"active"|"inactive"|"unknown">,
      "tags": <array of strings>,
      "child": <Record or null, one level recursion>
    }

    Strategy:
    - Mostly well-formed, but vary one or two fields subtly:
      * sometimes null vs missing (for nullable fields)
      * sometimes empty array vs null vs missing (for tags)
      * sometimes enum boundary values or close to enum (but invalid enum rejected by all)
      * sometimes duplicate keys (last wins)
      * sometimes nested child null or present with subtle variation
      * sometimes "tags" null (built_value accepts, others reject)
      * sometimes "tags" empty array (all accept)
      * sometimes "name" null or string
      * sometimes "amount" string but empty or numeric string
      * sometimes "id" integer or boundary integer (0, large)
    """

    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]
    # We do not produce invalid enum values here because all reject them identically.

    # Generate id: integer, mostly positive, sometimes zero or large
    id_val = draw(st.one_of(
        st.integers(min_value=0, max_value=1000),
        st.just(0),
        st.integers(min_value=2**30, max_value=2**31-1),
    ))

    # Generate amount: string, non-empty numeric string or empty string (allowed)
    # amount must be string, so no numbers here
    amount_val = draw(st.one_of(
        st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in ".-" for c in s)),
        st.just("0"),
        st.just(""),
        st.just("-123.45"),
        st.just("100"),
    ))

    # Generate name: string or null
    # Occasionally null, occasionally empty string, occasionally normal string
    name_val = draw(st.one_of(
        st.none(),
        st.text(min_size=0, max_size=10),
    ))

    # Generate status: always valid enum string
    status_val = draw(st.sampled_from(STATUS_VALUES))

    # Generate tags: array of strings, or null (to trigger built_value acceptance divergence)
    # Occasionally null (built_value accepts, others reject)
    # Occasionally empty array (all accept)
    # Occasionally array with 1-3 strings
    tags_choice = draw(st.integers(min_value=0, max_value=2))
    if tags_choice == 0:
        tags_val = None  # null tags (built_value accepts, others reject)
    elif tags_choice == 1:
        tags_val = []  # empty array tags (all accept)
    else:
        # array of 1-3 strings, strings non-empty, ascii letters only
        tags_val = draw(st.lists(st.text(min_size=1, max_size=8).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), min_size=1, max_size=3))

    # Generate child: null or nested Record (one level only)
    # Nested record mostly well-formed, but vary one field subtly to provoke divergence
    # For nested record, do not nest further (child.child is always null)
    child_present = draw(st.booleans())
    if child_present:
        # Nested child fields:
        # id: integer (like top level)
        child_id = draw(st.integers(min_value=0, max_value=1000))
        # amount: string numeric
        child_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in ".-" for c in s)))
        # name: string or null
        child_name = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10)))
        # status: valid enum
        child_status = draw(st.sampled_from(STATUS_VALUES))
        # tags: array of strings or null (same logic as top level)
        child_tags_choice = draw(st.integers(min_value=0, max_value=2))
        if child_tags_choice == 0:
            child_tags = None
        elif child_tags_choice == 1:
            child_tags = []
        else:
            child_tags = draw(st.lists(st.text(min_size=1, max_size=8).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), min_size=1, max_size=3))
        # child.child always null (no deeper nesting)
        child_child = None

        # Build child JSON text
        # Use duplicate keys sometimes in child to provoke divergence (last wins)
        child_duplicate_key = draw(st.booleans())
        child_fields = []

        def json_field(k, v):
            if v is None:
                return f'{json_string(k)}:null'
            elif isinstance(v, str):
                return f'{json_string(k)}:{json_string(v)}'
            elif isinstance(v, int):
                return f'{json_string(k)}:{v}'
            elif isinstance(v, list):
                arr = "[" + ",".join(json_string(x) for x in v) + "]"
                return f'{json_string(k)}:{arr}'
            else:
                # Should not happen here
                return f'{json_string(k)}:null'

        # Add fields normally
        child_fields.append(json_field("id", child_id))
        child_fields.append(json_field("amount", child_amount))
        if child_name is None:
            child_fields.append(f'{json_string("name")}:null')
        else:
            child_fields.append(json_field("name", child_name))
        child_fields.append(json_field("status", child_status))
        if child_tags is None:
            child_fields.append(f'{json_string("tags")}:null')
        else:
            child_fields.append(json_field("tags", child_tags))
        child_fields.append(f'{json_string("child")}:null')

        if child_duplicate_key:
            # Duplicate "id" key with a different value to provoke divergence on last-wins
            dup_id_val = child_id + 1
            # Insert duplicate "id" key at random position
            pos = draw(st.integers(min_value=0, max_value=len(child_fields)))
            child_fields.insert(pos, json_field("id", dup_id_val))

        child_json = "{" + ",".join(child_fields) + "}"
    else:
        child_json = "null"

    # Build top-level JSON text similarly
    # Possibly insert duplicate keys at top level to provoke divergence
    top_duplicate_key = draw(st.booleans())

    top_fields = []

    def json_field(k, v):
        if v is None:
            return f'{json_string(k)}:null'
        elif isinstance(v, str):
            return f'{json_string(k)}:{json_string(v)}'
        elif isinstance(v, int):
            return f'{json_string(k)}:{v}'
        elif isinstance(v, list):
            arr = "[" + ",".join(json_string(x) for x in v) + "]"
            return f'{json_string(k)}:{arr}'
        else:
            # Should not happen here
            return f'{json_string(k)}:null'

    top_fields.append(json_field("id", id_val))
    top_fields.append(json_field("amount", amount_val))
    if name_val is None:
        top_fields.append(f'{json_string("name")}:null')
    else:
        top_fields.append(json_field("name", name_val))
    top_fields.append(json_field("status", status_val))
    if tags_val is None:
        top_fields.append(f'{json_string("tags")}:null')
    else:
        top_fields.append(json_field("tags", tags_val))
    top_fields.append(f'{json_string("child")}:{child_json}')

    if top_duplicate_key:
        # Duplicate "status" key with a different valid enum value (last wins)
        dup_status_val = draw(st.sampled_from([s for s in STATUS_VALUES if s != status_val]))
        pos = draw(st.integers(min_value=0, max_value=len(top_fields)))
        top_fields.insert(pos, json_field("status", dup_status_val))

    json_text = "{" + ",".join(top_fields) + "}"

    return json_text.encode("utf-8")