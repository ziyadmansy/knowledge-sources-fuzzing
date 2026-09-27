from hypothesis import strategies as st

# Helper: JSON string escaping for double quotes and backslashes only,
# minimal escaping to keep JSON valid.
def json_escape(s: str) -> str:
    # Escape backslash and double quote only (minimal JSON escaping)
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.

    Schema:
    {
      "id": <integer or near-integer number, sometimes float 1.0>,
      "amount": <string>,
      "name": <string or null>,
      "status": <string enum or near-enum string>,
      "tags": <array of strings, or array with one non-string element>,
      "child": <null or nested record, one level recursion>
    }

    Variations introduced:
    - id: integer, or float with .0 (accepted by json_serializable/freezed but not manual/built_value),
          or string (causes manual to fail on cast, others may reject differently)
    - status: exact enum strings or unknown strings (to provoke different exception types)
    - tags: all strings or one element non-string (to provoke cast errors)
    - name: string or null (no divergence expected, but included for completeness)
    - child: null or nested record (one level only)
    """

    # Constants for enum values
    valid_statuses = ["active", "inactive", "unknown"]
    # Near enum strings to provoke manual and built_value ArgumentError, but json_serializable throws CheckedFromJsonException
    near_enum_statuses = ["Active", "inactive ", "unknownx", "actve", "UNKNOWN"]

    # id strategies:
    # - integer (always accepted)
    # - float with .0 (accepted by json_serializable/freezed, rejected by manual/built_value)
    # - stringified integer (causes manual to fail cast)
    id_int = st.integers(min_value=0, max_value=1000)
    id_float_int = id_int.map(lambda x: float(x))  # e.g. 1.0
    id_str_int = id_int.map(str)

    # Choose id variant with weighted probabilities to maximize divergence:
    # 50% int, 30% float int, 20% string int
    id_choice = st.one_of(
        id_int,
        id_float_int,
        id_str_int,
    ).filter(lambda v: True)  # no filter, just placeholder

    # amount: always string, non-empty, ascii printable except quotes and backslash for simplicity
    amount_str = st.text(
        alphabet=st.characters(
            whitelist_categories=('Ll', 'Lu', 'Nd', 'Zs', 'Po'),
            blacklist_characters=['"', '\\']
        ),
        min_size=1,
        max_size=10,
    )

    # name: string or null
    name_str = st.one_of(
        st.none(),
        st.text(
            alphabet=st.characters(
                whitelist_categories=('Ll', 'Lu', 'Nd', 'Zs', 'Po'),
                blacklist_characters=['"', '\\']
            ),
            min_size=1,
            max_size=10,
        )
    )

    # status: valid or near enum string
    status_str = st.one_of(
        st.sampled_from(valid_statuses),
        st.sampled_from(near_enum_statuses)
    )

    # tags: mostly all strings, sometimes one element non-string (int or bool)
    tag_str = st.text(
        alphabet=st.characters(
            whitelist_categories=('Ll', 'Lu', 'Nd', 'Zs', 'Po'),
            blacklist_characters=['"', '\\']
        ),
        min_size=1,
        max_size=8,
    )
    tags_all_str = st.lists(tag_str, min_size=0, max_size=5)
    # One element non-string: int or bool
    tags_one_non_str = st.lists(tag_str, min_size=0, max_size=4).flatmap(
        lambda lst: st.one_of(
            st.tuples(st.just(lst), st.integers(min_value=0, max_value=len(lst))),
            st.tuples(st.just(lst), st.just(len(lst)))  # append at end
        )
    ).map(lambda pair: pair[0][:pair[1]] + [True] + pair[0][pair[1]:] if pair[1] <= len(pair[0]) else pair[0] + [True])

    tags_choice = st.one_of(tags_all_str, tags_one_non_str)

    # Recursive child record: either null or nested record (one level only)
    # To avoid infinite recursion, child record has child=null always.
    # We'll generate child record with same logic but child=null.

    # Helper to build JSON text for a record dict
    def record_to_json(d: dict) -> str:
        # d keys: id, amount, name, status, tags, child (json text or null)
        # id: number or string (emit accordingly)
        id_val = d["id"]
        if isinstance(id_val, int):
            id_json = str(id_val)
        elif isinstance(id_val, float):
            # emit float with .0
            id_json = f"{id_val:.1f}"
        else:
            # string id: emit quoted string with escaping
            id_json = '"' + json_escape(id_val) + '"'

        amount_json = '"' + json_escape(d["amount"]) + '"'

        if d["name"] is None:
            name_json = "null"
        else:
            name_json = '"' + json_escape(d["name"]) + '"'

        status_json = '"' + json_escape(d["status"]) + '"'

        # tags: list of strings or mixed
        tags_json_items = []
        for t in d["tags"]:
            if isinstance(t, str):
                tags_json_items.append('"' + json_escape(t) + '"')
            elif isinstance(t, bool):
                tags_json_items.append("true" if t else "false")
            elif isinstance(t, int):
                tags_json_items.append(str(t))
            else:
                # fallback, emit as string
                tags_json_items.append('"' + json_escape(str(t)) + '"')
        tags_json = "[" + ",".join(tags_json_items) + "]"

        # child: null or nested JSON string
        child_json = d["child"] if d["child"] is not None else "null"

        # Compose full JSON object string
        json_obj = (
            '{'
            f'"id":{id_json},'
            f'"amount":{amount_json},'
            f'"name":{name_json},'
            f'"status":{status_json},'
            f'"tags":{tags_json},'
            f'"child":{child_json}'
            '}'
        )
        return json_obj

    # Compose child record with child=null always
    def gen_child_record():
        # id: int or float int only (avoid string id in child to reduce complexity)
        child_id = draw(st.one_of(id_int, id_float_int))
        child_amount = draw(amount_str)
        child_name = draw(name_str)
        child_status = draw(st.sampled_from(valid_statuses))  # child status always valid to reduce noise
        child_tags = draw(tags_all_str)  # child tags all strings to reduce noise
        child_child = None  # no recursion beyond one level

        child_dict = {
            "id": child_id,
            "amount": child_amount,
            "name": child_name,
            "status": child_status,
            "tags": child_tags,
            "child": child_child,
        }
        return record_to_json(child_dict)

    # Draw main record fields
    id_val = draw(id_choice)
    amount_val = draw(amount_str)
    name_val = draw(name_str)
    status_val = draw(status_str)
    tags_val = draw(tags_choice)
    # child: null or nested record
    child_val = draw(st.one_of(st.just(None), st.deferred(gen_child_record)))

    record_dict = {
        "id": id_val,
        "amount": amount_val,
        "name": name_val,
        "status": status_val,
        "tags": tags_val,
        "child": child_val,
    }

    json_text = record_to_json(record_dict)
    return json_text.encode("utf-8")