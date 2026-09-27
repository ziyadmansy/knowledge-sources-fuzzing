from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for "status" field
    statuses = ["active", "inactive", "unknown"]

    # Strategy for "id": integer
    id_strat = st.integers(min_value=0, max_value=10**9)

    # Strategy for "amount": any string (including numeric-looking)
    # Use ascii letters, digits, punctuation, spaces, length 1-10
    amount_strat = st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd", "Zs", "Po", "Sm", "Sc"),
            blacklist_characters=['"', '\\']
        ),
        min_size=1,
        max_size=10,
    )

    # Strategy for "name": string or null
    name_strat = st.one_of(
        st.none(),
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd", "Zs"),
                blacklist_characters=['"', '\\']
            ),
            min_size=0,
            max_size=10,
        ),
    )

    # Strategy for "status": one of the three valid strings only
    status_strat = st.sampled_from(statuses)

    # Strategy for "tags":
    # To maximize divergence:
    # - built_value accepts null or object (decoded as empty list)
    # - others reject null or object
    # - all reject string or array with non-string elements
    # So we produce mostly valid arrays of strings, but sometimes null or object
    # to trigger divergence.
    # We'll produce one of:
    # - valid array of strings (including empty)
    # - null
    # - object (empty or with string keys/values)
    # We do NOT produce string or array with non-string elements (all reject)
    tags_array_strat = st.lists(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd", "Zs"),
                blacklist_characters=['"', '\\']
            ),
            min_size=0,
            max_size=10,
        ),
        max_size=5,
    )
    tags_object_strat = st.dictionaries(
        keys=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd", "Zs"),
                blacklist_characters=['"', '\\']
            ),
            min_size=1,
            max_size=5,
        ),
        values=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd", "Zs"),
                blacklist_characters=['"', '\\']
            ),
            min_size=0,
            max_size=5,
        ),
        max_size=3,
    )
    tags_strat = st.one_of(
        tags_array_strat,
        st.none(),
        tags_object_strat,
    )

    # Forward declaration for recursion
    # We'll limit recursion depth to 1 (child can be null or record with child=null)
    # To avoid infinite recursion, we define a helper function that takes depth
    def record_strat(depth):
        # If depth > 1, child must be null
        if depth > 1:
            child_strat = st.none()
        else:
            # child is null or a record with depth+1
            child_strat = st.one_of(st.none(), record_strat(depth + 1))

        # "name" is optional: missing or present with null/string
        # To produce missing "name" sometimes, we produce a dict without "name" key
        # But we must produce JSON text, so we must encode missing keys by omitting them from output
        # We'll handle missing "name" by producing a dict with or without "name" key

        # We produce a dict with all keys except "name" optional
        # We'll produce a dict of keys to JSON text fragments, then build JSON text

        # Draw fields
        id_v = draw(id_strat)
        amount_v = draw(amount_strat)
        # name: either missing or present (null or string)
        name_present = draw(st.booleans())
        if name_present:
            name_v = draw(name_strat)
        else:
            name_v = None  # means missing

        status_v = draw(status_strat)
        tags_v = draw(tags_strat)
        child_v = draw(child_strat)

        # Build JSON text for each field
        # Helper to JSON-encode string (escape quotes and backslashes)
        def json_str(s):
            # Escape backslash and quote
            s = s.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{s}"'

        # id: integer
        id_json = f'"id":{id_v}'

        # amount: string
        amount_json = f'"amount":{json_str(amount_v)}'

        # name: optional
        if name_present:
            if name_v is None:
                name_json = '"name":null'
            else:
                name_json = f'"name":{json_str(name_v)}'
        else:
            name_json = None  # omit

        # status: string
        status_json = f'"status":{json_str(status_v)}'

        # tags: can be null, array, or object
        if tags_v is None:
            tags_json = '"tags":null'
        elif isinstance(tags_v, list):
            # array of strings
            arr_items = ",".join(json_str(s) for s in tags_v)
            tags_json = f'"tags":[{arr_items}]'
        else:
            # object
            obj_items = ",".join(f'{json_str(k)}:{json_str(v)}' for k, v in tags_v.items())
            tags_json = f'"tags":{{{obj_items}}}'

        # child: null or record
        if child_v is None:
            child_json = '"child":null'
        else:
            # child_v is JSON text of a record (already serialized)
            child_json = f'"child":{child_v}'

        # Compose fields, omit name if missing
        fields = [id_json, amount_json]
        if name_json is not None:
            fields.append(name_json)
        fields.extend([status_json, tags_json, child_json])

        json_text = "{" + ",".join(fields) + "}"
        return json_text

    # Draw top-level record with depth 0
    json_text = record_strat(0)

    # Return bytes
    return json_text.encode("utf-8")