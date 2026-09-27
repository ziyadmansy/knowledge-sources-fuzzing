from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper: generate a valid or near-valid "status" string
    # Manual and built_value require exact enum strings or throw ArgumentError (undocumented)
    # json_serializable/freezed throw documented CheckedFromJsonException
    # We produce mostly valid enum strings, but sometimes an unknown string to trigger divergence.
    valid_statuses = ["active", "inactive", "unknown"]
    # 80% valid, 20% unknown string (random ascii letters)
    status = draw(
        st.one_of(
            st.sampled_from(valid_statuses),
            st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_statuses),
        )
    )

    # Helper: generate "id" with subtle type variations:
    # manual requires int exactly (json['id'] as int)
    # json_serializable/freezed accept any num and convert via toInt()
    # built_value expects int and likely rejects non-int types
    # So try int, float with integral value, float non-integral, string number, string non-number
    id_type = draw(st.sampled_from(["int", "float_int", "float_nonint", "str_int", "str_nonint"]))
    if id_type == "int":
        id_val = draw(st.integers(min_value=0, max_value=1_000_000))
        id_json = str(id_val)
    elif id_type == "float_int":
        # float with integral value, e.g. 42.0
        id_val = float(draw(st.integers(min_value=0, max_value=1_000_000)))
        id_json = str(id_val)
    elif id_type == "float_nonint":
        # float with fractional part, e.g. 42.5
        id_val = draw(st.floats(min_value=0, max_value=1_000_000, allow_infinity=False, allow_nan=False))
        # force fractional part nonzero
        if id_val == int(id_val):
            id_val += 0.5
        id_json = str(id_val)
    elif id_type == "str_int":
        id_val = draw(st.integers(min_value=0, max_value=1_000_000))
        id_json = '"' + str(id_val) + '"'
    else:  # str_nonint
        id_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: not s.isdigit()))
        id_json = '"' + id_val + '"'

    # amount: all require string exactly; produce valid string or non-string to trigger rejection
    # 90% string, 10% non-string (int or null)
    amount_type = draw(st.one_of(st.just("string"), st.just("int"), st.just("null")))
    if amount_type == "string":
        amount_val = draw(st.text(min_size=1, max_size=20))
        amount_json = '"' + amount_val.replace('"', '\\"') + '"'
    elif amount_type == "int":
        amount_val = draw(st.integers(min_value=0, max_value=1_000_000))
        amount_json = str(amount_val)
    else:
        amount_json = "null"

    # name: string or null only, no divergence expected here, but vary anyway
    # 80% string, 20% null
    name_type = draw(st.one_of(st.just("string"), st.just("null")))
    if name_type == "string":
        name_val = draw(st.text(min_size=0, max_size=20))
        name_json = '"' + name_val.replace('"', '\\"') + '"'
    else:
        name_json = "null"

    # tags: array of strings normally
    # manual casts to List then maps elements as String
    # json_serializable/freezed cast to List<dynamic> then map to String
    # built_value expects BuiltList<String> and rejects non-list or lists with non-string elements
    # We produce mostly valid lists of strings, but sometimes:
    # - empty list
    # - list with one non-string element (int or null)
    # - non-list (string or null)
    tags_type = draw(
        st.one_of(
            st.just("valid_list"),
            st.just("empty_list"),
            st.just("list_with_nonstring"),
            st.just("string"),
            st.just("null"),
        )
    )
    if tags_type == "valid_list":
        # list of 1-5 strings
        tag_list = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=5))
        tags_json = "[" + ",".join('"' + t.replace('"', '\\"') + '"' for t in tag_list) + "]"
    elif tags_type == "empty_list":
        tags_json = "[]"
    elif tags_type == "list_with_nonstring":
        # list with 1-3 strings and 1 non-string element (int or null)
        n_strings = draw(st.integers(min_value=0, max_value=3))
        strings = draw(st.lists(st.text(min_size=1, max_size=10), min_size=n_strings, max_size=n_strings))
        nonstring = draw(st.one_of(st.integers(min_value=0, max_value=100), st.just(None)))
        elements = [f'"{s.replace("\"", "\\\"")}"' for s in strings]
        if nonstring is None:
            elements.append("null")
        else:
            elements.append(str(nonstring))
        # shuffle elements to randomize position
        import random
        random.shuffle(elements)
        tags_json = "[" + ",".join(elements) + "]"
    elif tags_type == "string":
        # tags as a string (invalid type)
        tags_val = draw(st.text(min_size=1, max_size=10))
        tags_json = '"' + tags_val.replace('"', '\\"') + '"'
    else:
        tags_json = "null"

    # child: null or nested record (one level recursion)
    # To keep size bounded, child can be null or a record with all fields valid except:
    # - vary one field in child similarly to top-level to trigger divergence
    # 70% null, 30% nested record
    has_child = draw(st.booleans())
    if not has_child:
        child_json = "null"
    else:
        # Nested record with mostly valid fields, but vary one field to trigger divergence
        # We reuse the same logic but restrict recursion depth to 1
        # To avoid infinite recursion, child's child is always null
        # We vary only one field in child to be off, others valid

        # Pick one field to vary in child: id, amount, status, name, tags
        child_field_to_vary = draw(st.sampled_from(["id", "amount", "status", "name", "tags"]))

        # id in child
        if child_field_to_vary == "id":
            # vary id type as above
            id_type_c = draw(st.sampled_from(["int", "float_int", "float_nonint", "str_int", "str_nonint"]))
            if id_type_c == "int":
                id_val_c = draw(st.integers(min_value=0, max_value=1_000_000))
                id_json_c = str(id_val_c)
            elif id_type_c == "float_int":
                id_val_c = float(draw(st.integers(min_value=0, max_value=1_000_000)))
                id_json_c = str(id_val_c)
            elif id_type_c == "float_nonint":
                id_val_c = draw(st.floats(min_value=0, max_value=1_000_000, allow_infinity=False, allow_nan=False))
                if id_val_c == int(id_val_c):
                    id_val_c += 0.5
                id_json_c = str(id_val_c)
            elif id_type_c == "str_int":
                id_val_c = draw(st.integers(min_value=0, max_value=1_000_000))
                id_json_c = '"' + str(id_val_c) + '"'
            else:
                id_val_c = draw(st.text(min_size=1, max_size=10).filter(lambda s: not s.isdigit()))
                id_json_c = '"' + id_val_c + '"'
            # other fields valid
            amount_val_c = draw(st.text(min_size=1, max_size=20))
            amount_json_c = '"' + amount_val_c.replace('"', '\\"') + '"'
            status_c = draw(st.sampled_from(["active", "inactive", "unknown"]))
            name_val_c = draw(st.one_of(st.text(min_size=0, max_size=20), st.just(None)))
            if name_val_c is None:
                name_json_c = "null"
            else:
                name_json_c = '"' + name_val_c.replace('"', '\\"') + '"'
            tags_list_c = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=3))
            tags_json_c = "[" + ",".join('"' + t.replace('"', '\\"') + '"' for t in tags_list_c) + "]"
            child_json = (
                "{" +
                f'"id":{id_json_c},'
                f'"amount":{amount_json_c},'
                f'"status":"{status_c}",'
                f'"name":{name_json_c},'
                f'"tags":{tags_json_c},'
                f'"child":null'
                "}"
            )
        elif child_field_to_vary == "amount":
            # vary amount type: string or int or null
            amount_type_c = draw(st.one_of(st.just("string"), st.just("int"), st.just("null")))
            if amount_type_c == "string":
                amount_val_c = draw(st.text(min_size=1, max_size=20))
                amount_json_c = '"' + amount_val_c.replace('"', '\\"') + '"'
            elif amount_type_c == "int":
                amount_val_c = draw(st.integers(min_value=0, max_value=1_000_000))
                amount_json_c = str(amount_val_c)
            else:
                amount_json_c = "null"
            # other fields valid
            id_val_c = draw(st.integers(min_value=0, max_value=1_000_000))
            id_json_c = str(id_val_c)
            status_c = draw(st.sampled_from(["active", "inactive", "unknown"]))
            name_val_c = draw(st.one_of(st.text(min_size=0, max_size=20), st.just(None)))
            if name_val_c is None:
                name_json_c = "null"
            else:
                name_json_c = '"' + name_val_c.replace('"', '\\"') + '"'
            tags_list_c = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=3))
            tags_json_c = "[" + ",".join('"' + t.replace('"', '\\"') + '"' for t in tags_list_c) + "]"
            child_json = (
                "{" +
                f'"id":{id_json_c},'
                f'"amount":{amount_json_c},'
                f'"status":"{status_c}",'
                f'"name":{name_json_c},'
                f'"tags":{tags_json_c},'
                f'"child":null'
                "}"
            )
        elif child_field_to_vary == "status":
            # vary status: valid or unknown string
            valid_statuses_c = ["active", "inactive", "unknown"]
            status_c = draw(
                st.one_of(
                    st.sampled_from(valid_statuses_c),
                    st.text(min_size=1, max_size=10).filter(lambda s: s not in valid_statuses_c),
                )
            )
            # other fields valid
            id_val_c = draw(st.integers(min_value=0, max_value=1_000_000))
            id_json_c = str(id_val_c)
            amount_val_c = draw(st.text(min_size=1, max_size=20))
            amount_json_c = '"' + amount_val_c.replace('"', '\\"') + '"'
            name_val_c = draw(st.one_of(st.text(min_size=0, max_size=20), st.just(None)))
            if name_val_c is None:
                name_json_c = "null"
            else:
                name_json_c = '"' + name_val_c.replace('"', '\\"') + '"'
            tags_list_c = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=3))
            tags_json_c = "[" + ",".join('"' + t.replace('"', '\\"') + '"' for t in tags_list_c) + "]"
            child_json = (
                "{" +
                f'"id":{id_json_c},'
                f'"amount":{amount_json_c},'
                f'"status":"{status_c}",'
                f'"name":{name_json_c},'
                f'"tags":{tags_json_c},'
                f'"child":null'
                "}"
            )
        elif child_field_to_vary == "name":
            # vary name: string or null only (no divergence expected, but vary anyway)
            name_val_c = draw(st.one_of(st.text(min_size=0, max_size=20), st.just(None)))
            if name_val_c is None:
                name_json_c = "null"
            else:
                name_json_c = '"' + name_val_c.replace('"', '\\"') + '"'
            # other fields valid
            id_val_c = draw(st.integers(min_value=0, max_value=1_000_000))
            id_json_c = str(id_val_c)
            amount_val_c = draw(st.text(min_size=1, max_size=20))
            amount_json_c = '"' + amount_val_c.replace('"', '\\"') + '"'
            status_c = draw(st.sampled_from(["active", "inactive", "unknown"]))
            tags_list_c = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=3))
            tags_json_c = "[" + ",".join('"' + t.replace('"', '\\"') + '"' for t in tags_list_c) + "]"
            child_json = (
                "{" +
                f'"id":{id_json_c},'
                f'"amount":{amount_json_c},'
                f'"status":"{status_c}",'
                f'"name":{name_json_c},'
                f'"tags":{tags_json_c},'
                f'"child":null'
                "}"
            )
        else:  # tags
            # vary tags similarly to top-level tags
            tags_type_c = draw(
                st.one_of(
                    st.just("valid_list"),
                    st.just("empty_list"),
                    st.just("list_with_nonstring"),
                    st.just("string"),
                    st.just("null"),
                )
            )
            if tags_type_c == "valid_list":
                tag_list_c = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=5))
                tags_json_c = "[" + ",".join('"' + t.replace('"', '\\"') + '"' for t in tag_list_c) + "]"
            elif tags_type_c == "empty_list":
                tags_json_c = "[]"
            elif tags_type_c == "list_with_nonstring":
                n_strings_c = draw(st.integers(min_value=0, max_value=3))
                strings_c = draw(st.lists(st.text(min_size=1, max_size=10), min_size=n_strings_c, max_size=n_strings_c))
                nonstring_c = draw(st.one_of(st.integers(min_value=0, max_value=100), st.just(None)))
                elements_c = [f'"{s.replace("\"", "\\\"")}"' for s in strings_c]
                if nonstring_c is None:
                    elements_c.append("null")
                else:
                    elements_c.append(str(nonstring_c))
                import random
                random.shuffle(elements_c)
                tags_json_c = "[" + ",".join(elements_c) + "]"
            elif tags_type_c == "string":
                tags_val_c = draw(st.text(min_size=1, max_size=10))
                tags_json_c = '"' + tags_val_c.replace('"', '\\"') + '"'
            else:
                tags_json_c = "null"
            # other fields valid
            id_val_c = draw(st.integers(min_value=0, max_value=1_000_000))
            id_json_c = str(id_val_c)
            amount_val_c = draw(st.text(min_size=1, max_size=20))
            amount_json_c = '"' + amount_val_c.replace('"', '\\"') + '"'
            status_c = draw(st.sampled_from(["active", "inactive", "unknown"]))
            name_val_c = draw(st.one_of(st.text(min_size=0, max_size=20), st.just(None)))
            if name_val_c is None:
                name_json_c = "null"
            else:
                name_json_c = '"' + name_val_c.replace('"', '\\"') + '"'
            child_json = (
                "{" +
                f'"id":{id_json_c},'
                f'"amount":{amount_json_c},'
                f'"status":"{status_c}",'
                f'"name":{name_json_c},'
                f'"tags":{tags_json_c},'
                f'"child":null'
                "}"
            )

    # Compose top-level JSON object
    json_text = (
        "{" +
        f'"id":{id_json},'
        f'"amount":{amount_json},'
        f'"status":"{status}",'
        f'"name":{name_json},'
        f'"tags":{tags_json},'
        f'"child":{child_json}'
        "}"
    )
    return json_text.encode("utf-8")