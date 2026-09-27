from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Allowed status strings
    statuses = ["active", "inactive", "unknown"]

    # Base valid field strategies
    id_strat = st.integers(min_value=0, max_value=2**31-1)
    amount_strat = st.text(min_size=1)  # nonempty string for amount
    # name can be string or null or missing (missing treated as null by all)
    name_strat = st.one_of(st.none(), st.text())
    # tags normally list of strings, but to trigger divergences:
    # - missing tags (D_built_value accepts, others reject)
    # - tags as object (D_built_value accepts as empty list, others reject)
    # - tags as list of strings (normal)
    # - tags as list with null or non-string (all reject)
    # We'll produce mostly valid tags or missing or object to trigger divergences.
    # We'll produce only valid tags or missing or object, no invalid element types inside list,
    # because invalid element types cause all to reject with _TypeError or DeserializationError.
    tags_valid = st.lists(st.text(), min_size=0, max_size=3)
    tags_object = st.fixed_dictionaries({"not": st.just("a list")})
    tags_choice = st.one_of(
        tags_valid,
        st.just(None),  # missing tags encoded as missing field (handle later)
        tags_object,
    )

    # status normally one of allowed strings, but can be null or invalid string to trigger divergences
    status_choice = st.one_of(
        st.sampled_from(statuses),
        st.none(),  # null status triggers different errors
        st.text().filter(lambda s: s not in statuses and s != ""),  # invalid string
    )

    # child is either null or a nested record (one level recursion)
    # We'll limit recursion depth to 1 (child.child always null)
    # To trigger divergences, child can be:
    # - null (normal)
    # - valid nested record (recursive call)
    # - invalid types (string, array, empty object) to trigger rejection differences
    # We'll produce mostly valid or null or invalid types to trigger divergences.
    # empty object {} is invalid child (all reject but with different exceptions)
    # string or array also invalid child
    def child_strategy():
        # valid nested record with child=null
        base_record = st.deferred(lambda: record_strategy(allow_missing_tags=True, allow_tags_object=True, allow_invalid_child=False, depth=1))
        invalid_child = st.one_of(
            st.text(),
            st.lists(st.integers(), max_size=2),
            st.just({}),  # empty object
        )
        return st.one_of(
            st.none(),
            base_record,
            invalid_child,
        )

    # To produce a record with controlled fields:
    # allow_missing_tags: if True, tags can be missing (encoded by omitting field)
    # allow_tags_object: if True, tags can be an object (not list)
    # allow_invalid_child: if True, child can be invalid type (string, array, empty object)
    # depth: recursion depth, 0 means no child field or child always null
    def record_strategy(allow_missing_tags, allow_tags_object, allow_invalid_child, depth):
        # id always integer
        id_val = id_strat
        # amount always string
        amount_val = amount_strat
        # name string or null
        name_val = name_strat
        # status from status_choice
        status_val = status_choice
        # tags: if allow_missing_tags True, tags can be missing (None)
        # if allow_tags_object True, tags can be object
        # else tags always list of strings
        if allow_missing_tags and allow_tags_object:
            tags_val = tags_choice
        elif allow_missing_tags:
            tags_val = st.one_of(tags_valid, st.just(None))
        elif allow_tags_object:
            tags_val = st.one_of(tags_valid, tags_object)
        else:
            tags_val = tags_valid

        # child field
        if depth <= 0:
            # no recursion, child always null or invalid if allowed
            if allow_invalid_child:
                child_val = st.one_of(
                    st.none(),
                    st.text(),
                    st.lists(st.integers(), max_size=2),
                    st.just({}),
                )
            else:
                child_val = st.none()
        else:
            # depth > 0: child can be nested record or null or invalid if allowed
            if allow_invalid_child:
                child_val = child_strategy()
            else:
                child_val = st.one_of(
                    st.none(),
                    record_strategy(allow_missing_tags, allow_tags_object, False, depth - 1),
                )

        # Compose dictionary fields, omitting tags if tags_val is None (to simulate missing)
        def make_obj(id_, amount_, name_, status_, tags_, child_):
            fields = []
            # id
            fields.append('"id":' + str(id_))
            # amount (string, JSON escaped)
            amount_js = json_escape(amount_)
            fields.append('"amount":"' + amount_js + '"')
            # name: null or string or missing (missing not tested here, always present)
            if name_ is None:
                fields.append('"name":null')
            else:
                fields.append('"name":"' + json_escape(name_) + '"')
            # status: string or null or invalid string
            if status_ is None:
                fields.append('"status":null')
            else:
                fields.append('"status":"' + json_escape(status_) + '"')
            # tags: if None, omit field (missing)
            if tags_ is not None:
                if isinstance(tags_, list):
                    # list of strings
                    tags_js = '[' + ','.join('"' + json_escape(t) + '"' for t in tags_) + ']'
                    fields.append('"tags":' + tags_js)
                elif isinstance(tags_, dict):
                    # object tags (only one fixed dict)
                    # keys and values are strings, so encode as JSON object
                    obj_fields = []
                    for k,v in tags_.items():
                        obj_fields.append('"' + json_escape(k) + '":"' + json_escape(v) + '"')
                    fields.append('"tags":{' + ','.join(obj_fields) + '}')
                else:
                    # should not happen, but fallback to null
                    fields.append('"tags":null')
            # child: null or nested object or invalid type
            if child_ is None:
                fields.append('"child":null')
            elif isinstance(child_, dict):
                # nested record encoded as JSON object string
                # child_ is dict with keys id, amount, name, status, tags, child
                # We must encode it recursively
                child_js = dict_to_json(child_)
                fields.append('"child":' + child_js)
            elif isinstance(child_, str):
                # string child (invalid)
                fields.append('"child":"' + json_escape(child_) + '"')
            elif isinstance(child_, list):
                # array child (invalid)
                arr_js = '[' + ','.join(str(x) for x in child_) + ']'
                fields.append('"child":' + arr_js)
            elif isinstance(child_, dict):
                # empty object child (invalid)
                fields.append('"child":{}')
            else:
                # fallback null
                fields.append('"child":null')
            return '{' + ','.join(fields) + '}'

        # We cannot use json module, so we build JSON strings manually.
        # To do this, we convert child_ dict to JSON string recursively.
        # We'll convert child_ dict to JSON string here:
        def dict_to_json(d):
            # d is dict with keys id, amount, name, status, tags, child
            # all fields present
            parts = []
            # id int
            parts.append('"id":' + str(d["id"]))
            # amount string
            parts.append('"amount":"' + json_escape(d["amount"]) + '"')
            # name string or null
            if d["name"] is None:
                parts.append('"name":null')
            else:
                parts.append('"name":"' + json_escape(d["name"]) + '"')
            # status string or null or invalid string
            if d["status"] is None:
                parts.append('"status":null')
            else:
                parts.append('"status":"' + json_escape(d["status"]) + '"')
            # tags list or object or missing (missing not possible here)
            tags_val = d["tags"]
            if tags_val is None:
                # missing tags not possible here, encode empty list to be safe
                parts.append('"tags":[]')
            elif isinstance(tags_val, list):
                parts.append('"tags":[' + ','.join('"' + json_escape(t) + '"' for t in tags_val) + ']')
            elif isinstance(tags_val, dict):
                obj_fields = []
                for k,v in tags_val.items():
                    obj_fields.append('"' + json_escape(k) + '":"' + json_escape(v) + '"')
                parts.append('"tags":{' + ','.join(obj_fields) + '}')
            else:
                # fallback null
                parts.append('"tags":null')
            # child field
            child_val = d["child"]
            if child_val is None:
                parts.append('"child":null')
            elif isinstance(child_val, dict):
                parts.append('"child":' + dict_to_json(child_val))
            elif isinstance(child_val, str):
                parts.append('"child":"' + json_escape(child_val) + '"')
            elif isinstance(child_val, list):
                parts.append('"child":[' + ','.join(str(x) for x in child_val) + ']')
            else:
                parts.append('"child":null')
            return '{' + ','.join(parts) + '}'

        # Compose final dict for child if child is nested record
        # We must draw all fields for nested record if child is dict
        # So we draw child fields recursively if child is dict
        # We'll draw child fields here if child is dict
        # But since child_val is a strategy, we must draw it first
        # So we must draw all fields here, then build dict or invalid type

        # Actually, since this is a composite strategy, we must draw values now
        id_v = draw(id_val)
        amount_v = draw(amount_val)
        name_v = draw(name_val)
        status_v = draw(status_val)
        tags_v = draw(tags_val)
        # Draw child value
        child_v = draw(child_val)

        # If child_v is dict, ensure it has all fields (id, amount, name, status, tags, child)
        # If child_v is a nested record strategy, it returns JSON string, not dict
        # So we must build child dict here, not JSON string
        # To do this, we must draw child fields recursively
        # We must detect if child_v is a dict or JSON string
        # But child_strategy returns either None, dict, or invalid types
        # We must build child dict here if child_v is dict
        # So we must draw child fields recursively here

        # To avoid complexity, we change child_strategy to produce dicts, not JSON strings
        # So we redefine child_strategy here to produce dicts

        # We must rewrite child_strategy and record_strategy to produce dicts, then encode JSON here once

        # So let's rewrite record_strategy to produce dicts, then encode JSON once at the end

        # We stop here and rewrite the whole function to produce dicts, then encode JSON string once

        raise NotImplementedError("Refactor to produce dicts then encode JSON string once")

    # Because of the complexity of building JSON strings with recursion and optional fields,
    # we refactor to produce dicts first, then encode JSON string once at the end.

    # So we define a helper recursive strategy producing dicts with the schema,
    # allowing missing tags (by omitting key), tags as object, invalid child types, etc.

    # Then we encode dict to JSON string manually.

    # Helper: escape JSON string
    def json_escape(s):
        # minimal escaping for JSON string: backslash, quote, control chars
        # Hypothesis text can contain any unicode, so escape properly
        # We'll escape backslash, quote, and control chars < 0x20
        res = []
        for c in s:
            o = ord(c)
            if c == '\\':
                res.append('\\\\')
            elif c == '"':
                res.append('\\"')
            elif o < 0x20:
                res.append('\\u%04x' % o)
            else:
                res.append(c)
        return ''.join(res)

    # Recursive dict-producing strategy
    def dict_record_strategy(allow_missing_tags, allow_tags_object, allow_invalid_child, depth):
        # id int
        id_ = id_strat
        # amount string
        amount_ = amount_strat
        # name string or null
        name_ = name_strat
        # status string or null or invalid string
        status_ = status_choice

        # tags: list of strings, or object, or missing (missing by omitting key)
        if allow_missing_tags and allow_tags_object:
            tags_ = tags_choice
        elif allow_missing_tags:
            tags_ = st.one_of(tags_valid, st.just(None))
        elif allow_tags_object:
            tags_ = st.one_of(tags_valid, tags_object)
        else:
            tags_ = tags_valid

        # child field
        if depth <= 0:
            if allow_invalid_child:
                child_ = st.one_of(
                    st.none(),
                    st.text(),
                    st.lists(st.integers(), max_size=2),
                    st.just({}),
                )
            else:
                child_ = st.none()
        else:
            if allow_invalid_child:
                # child can be null, nested record, or invalid type
                child_ = st.one_of(
                    st.none(),
                    dict_record_strategy(allow_missing_tags, allow_tags_object, False, depth - 1),
                    st.text(),
                    st.lists(st.integers(), max_size=2),
                    st.just({}),
                )
            else:
                child_ = st.one_of(
                    st.none(),
                    dict_record_strategy(allow_missing_tags, allow_tags_object, False, depth - 1),
                )

        return st.builds(
            lambda i,a,n,s,t,c: dict_filter_none({
                "id": i,
                "amount": a,
                "name": n,
                "status": s,
                **({} if t is None else {"tags": t}),
                "child": c,
            }),
            id_, amount_, name_, status_, tags_, child_
        )

    # Helper to remove keys with value None (simulate missing fields)
    def dict_filter_none(d):
        return {k:v for k,v in d.items() if v is not None}

    # Encode dict to JSON string manually
    def encode_json(d):
        # d is dict with keys id, amount, name, status, optional tags, child
        parts = []
        # id int
        parts.append('"id":' + str(d["id"]))
        # amount string
        parts.append('"amount":"' + json_escape(d["amount"]) + '"')
        # name string or null or missing (missing not possible here)
        if "name" not in d or d["name"] is None:
            parts.append('"name":null')
        else:
            parts.append('"name":"' + json_escape(d["name"]) + '"')
        # status string or null
        if "status" not in d or d["status"] is None:
            parts.append('"status":null')
        else:
            parts.append('"status":"' + json_escape(d["status"]) + '"')
        # tags: list or object or missing
        if "tags" in d:
            t = d["tags"]
            if isinstance(t, list):
                parts.append('"tags":[' + ','.join('"' + json_escape(x) + '"' for x in t) + ']')
            elif isinstance(t, dict):
                obj_fields = []
                for k,v in t.items():
                    obj_fields.append('"' + json_escape(k) + '":"' + json_escape(v) + '"')
                parts.append('"tags":{' + ','.join(obj_fields) + '}')
            else:
                # fallback null
                parts.append('"tags":null')
        # child: null or dict or invalid type
        if "child" not in d or d["child"] is None:
            parts.append('"child":null')
        else:
            c = d["child"]
            if isinstance(c, dict):
                parts.append('"child":' + encode_json(c))
            elif isinstance(c, str):
                parts.append('"child":"' + json_escape(c) + '"')
            elif isinstance(c, list):
                parts.append('"child":[' + ','.join(str(x) for x in c) + ']')
            elif isinstance(c, dict):
                parts.append('"child":{}')
            else:
                parts.append('"child":null')
        return '{' + ','.join(parts) + '}'

    # Draw a record dict with controlled options to maximize divergences:
    # allow missing tags and tags as object to trigger D_built_value acceptance differences
    # allow invalid child types to trigger different exceptions
    # depth=1 to allow one level recursion
    record_dict = draw(dict_record_strategy(
        allow_missing_tags=True,
        allow_tags_object=True,
        allow_invalid_child=True,
        depth=1,
    ))

    # Encode to JSON string
    json_str = encode_json(record_dict)

    # Return bytes
    return json_str.encode("utf-8")