from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for "status" allowed values
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars minimally
        # Hypothesis strings are unicode, so escape control chars and quotes
        esc = s.replace("\\", "\\\\").replace("\"", "\\\"")
        esc = esc.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        # Other control chars (U+0000..U+001F) replaced as \u00XX
        def escape_ctrl(c):
            if ord(c) < 0x20:
                return "\\u%04x" % ord(c)
            return c
        esc = "".join(escape_ctrl(c) for c in esc)
        return f"\"{esc}\""

    # Compose JSON array of strings
    def json_array_of_strings(lst):
        return "[" + ",".join(json_string(s) for s in lst) + "]"

    # Compose JSON object from dict of fieldname->jsonvalue (strings)
    def json_object(d):
        # d keys are strings, values are strings representing JSON values (already serialized)
        items = []
        for k, v in d.items():
            items.append(json_string(k) + ":" + v)
        return "{" + ",".join(items) + "}"

    # Strategy for "id" field: integer normally, but sometimes string to test rejection
    # But known: all reject if id is string, so mostly produce int, but sometimes string to try divergence
    # To maximize chance of divergence, produce mostly int, rarely string
    id_val = draw(st.one_of(st.integers(min_value=0, max_value=2**31-1).map(str),
                            st.text(min_size=1, max_size=5).filter(lambda s: not s.isdigit())))
    # id_val is string representing the JSON value (either integer digits or string literal)
    # We must produce JSON integer or JSON string accordingly
    # If id_val is digits only, emit as number, else as string literal
    if id_val.isdigit():
        id_json = id_val
    else:
        id_json = json_string(id_val)

    # "amount" must be string, but we try sometimes integer to test rejection
    # Known: all reject if amount is integer, so mostly string, rarely integer
    amount_is_string = draw(st.booleans())
    if amount_is_string:
        # amount string: decimal number string or arbitrary string
        # To maximize chance of divergence, produce strings that look like numbers or weird strings
        amount_str = draw(st.one_of(
            st.decimals(min_value=0, max_value=1e9, places=2).map(lambda d: format(d, 'f').rstrip('0').rstrip('.') if '.' in format(d, 'f') else format(d, 'f')),
            st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))
        ))
        amount_json = json_string(str(amount_str))
    else:
        # integer amount as number (known rejected by all)
        amount_int = draw(st.integers(min_value=0, max_value=2**31-1))
        amount_json = str(amount_int)

    # "name": string or null only; known all reject if non-null non-string
    # To try divergence, produce string or null only (no int)
    name_is_null = draw(st.booleans())
    if name_is_null:
        name_json = "null"
    else:
        # string name, including empty string or unicode
        name_str = draw(st.text(min_size=0, max_size=20))
        name_json = json_string(name_str)

    # "status": one of allowed strings only; known all reject if invalid or null
    # To try divergence, produce mostly valid, rarely invalid string or null
    status_choice = draw(st.one_of(
        st.sampled_from(STATUS_VALUES),
        st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES),
        st.just(None)
    ))
    if status_choice is None:
        status_json = "null"
    elif status_choice in STATUS_VALUES:
        status_json = json_string(status_choice)
    else:
        status_json = json_string(status_choice)

    # "tags": array of strings only; empty array allowed
    # To try divergence, produce mostly array of strings, rarely array with one non-string element or non-array
    tags_type = draw(st.integers(min_value=0, max_value=2))
    # 0: valid array of strings
    # 1: array with one non-string element (int or null)
    # 2: non-array (string or null)
    if tags_type == 0:
        # array of strings, length 0..5
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), max_size=5))
        tags_json = json_array_of_strings(tags_list)
    elif tags_type == 1:
        # array with one non-string element
        # produce array length 1..5, with one element replaced by int or null
        length = draw(st.integers(min_value=1, max_value=5))
        tags_list = draw(st.lists(st.text(min_size=0, max_size=10), min_size=length, max_size=length))
        # replace one random element with int or null
        idx = draw(st.integers(min_value=0, max_value=length-1))
        non_str_val = draw(st.one_of(st.integers(min_value=0, max_value=100).map(str), st.just("null")))
        # Build JSON array manually
        elems = []
        for i, s in enumerate(tags_list):
            if i == idx:
                elems.append(non_str_val)
            else:
                elems.append(json_string(s))
        tags_json = "[" + ",".join(elems) + "]"
    else:
        # non-array: string or null
        non_array_val = draw(st.one_of(st.text(min_size=0, max_size=10).map(json_string), st.just("null")))
        tags_json = non_array_val

    # "child": null or nested record (one level recursion normally)
    # To try divergence, produce:
    # - null
    # - valid nested record (one level)
    # - nested record missing one required field (known all reject)
    # - nested record with one field wrong type (known all reject)
    # - nested record with extra fields (known accepted)
    # - nested record with nested child null or valid (one level)
    child_type = draw(st.integers(min_value=0, max_value=4))
    # Helper to build nested record JSON string from fields dict (values are JSON strings)
    def build_record(fields):
        return json_object(fields)

    def gen_nested_record(allow_missing=False, allow_wrong_type=False, allow_extra=False, nested_child_null=True):
        # Fields: id, amount, name, status, tags, child
        # id: int as number
        nid = draw(st.integers(min_value=0, max_value=2**31-1))
        id_field = str(nid)
        # amount: string decimal
        namount = draw(st.decimals(min_value=0, max_value=1e6, places=2))
        amount_field = json_string(format(namount, 'f').rstrip('0').rstrip('.') if '.' in format(namount, 'f') else format(namount, 'f'))
        # name: string or null
        nname_null = draw(st.booleans())
        if nname_null:
            name_field = "null"
        else:
            name_field = json_string(draw(st.text(min_size=0, max_size=10)))
        # status: valid string only
        status_field = json_string(draw(st.sampled_from(STATUS_VALUES)))
        # tags: array of strings (0..3)
        tags_list = draw(st.lists(st.text(min_size=0, max_size=5), max_size=3))
        tags_field = json_array_of_strings(tags_list)
        # child: null or valid nested child only if nested_child_null True
        if nested_child_null:
            child_field = "null"
        else:
            # no deeper recursion here to keep bounded
            child_field = "null"

        fields = {
            "id": id_field,
            "amount": amount_field,
            "name": name_field,
            "status": status_field,
            "tags": tags_field,
            "child": child_field,
        }

        # Possibly remove one required field if allow_missing
        if allow_missing:
            # remove one random field except child (to keep recursion bounded)
            remove_field = draw(st.sampled_from(["id", "amount", "name", "status", "tags"]))
            del fields[remove_field]

        # Possibly replace one field with wrong type if allow_wrong_type
        if allow_wrong_type:
            wrong_field = draw(st.sampled_from(list(fields.keys())))
            # Replace with wrong type JSON value:
            # id: string instead of int
            # amount: int instead of string
            # name: int instead of string/null
            # status: invalid string or null
            # tags: non-array or array with non-string
            # child: non-null non-object
            if wrong_field == "id":
                # string instead of int
                fields["id"] = json_string("wrongid")
            elif wrong_field == "amount":
                # int instead of string
                fields["amount"] = str(draw(st.integers(min_value=0, max_value=1000)))
            elif wrong_field == "name":
                # int instead of string/null
                fields["name"] = str(draw(st.integers(min_value=0, max_value=1000)))
            elif wrong_field == "status":
                # invalid string or null
                invalid_status = draw(st.one_of(st.text(min_size=1, max_size=10).filter(lambda s: s not in STATUS_VALUES), st.just("null")))
                if invalid_status == "null":
                    fields["status"] = "null"
                else:
                    fields["status"] = json_string(invalid_status)
            elif wrong_field == "tags":
                # non-array or array with non-string
                choice = draw(st.integers(min_value=0, max_value=1))
                if choice == 0:
                    # non-array string
                    fields["tags"] = json_string("notarray")
                else:
                    # array with one int element
                    arr = [json_string(draw(st.text(min_size=0, max_size=5))) for _ in range(draw(st.integers(min_value=1, max_value=3)))]
                    idx = draw(st.integers(min_value=0, max_value=len(arr)-1))
                    arr[idx] = str(draw(st.integers(min_value=0, max_value=100)))
                    fields["tags"] = "[" + ",".join(arr) + "]"
            elif wrong_field == "child":
                # non-null non-object: string or int
                fields["child"] = draw(st.one_of(st.text(min_size=1, max_size=5).map(json_string), st.integers(min_value=0, max_value=100).map(str)))
        # Possibly add extra fields if allow_extra
        if allow_extra:
            extra_field_name = draw(st.text(min_size=1, max_size=5).filter(lambda s: s not in fields))
            extra_field_value = draw(st.one_of(
                st.integers(min_value=0, max_value=100).map(str),
                st.text(min_size=0, max_size=10).map(json_string),
                st.just("null")
            ))
            fields[extra_field_name] = extra_field_value

        return build_record(fields)

    if child_type == 0:
        # child null
        child_json = "null"
    elif child_type == 1:
        # valid nested record
        child_json = gen_nested_record()
    elif child_type == 2:
        # nested record missing one required field (all reject)
        child_json = gen_nested_record(allow_missing=True)
    elif child_type == 3:
        # nested record with one field wrong type (all reject)
        child_json = gen_nested_record(allow_wrong_type=True)
    else:
        # nested record with extra fields (all accept)
        child_json = gen_nested_record(allow_extra=True)

    # Compose top-level JSON object
    top_fields = {
        "id": id_json,
        "amount": amount_json,
        "name": name_json,
        "status": status_json,
        "tags": tags_json,
        "child": child_json,
    }

    json_text = json_object(top_fields)
    return json_text.encode("utf-8")