from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Helper to produce a JSON string literal from a Python string,
    # escaping backslash and double quote minimally for valid JSON.
    def json_string(s: str) -> str:
        # Minimal escaping for JSON string literals:
        # Replace \ with \\, " with \"
        # No control chars or unicode escaping for simplicity (Hypothesis strings are safe)
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

    # id field: to maximize divergence on id parsing:
    # Manual requires int JSON number (no fraction),
    # json_serializable/freezed accept integral doubles (e.g. 1.0),
    # built_value likely rejects fractional numbers.
    # So produce either:
    # - int JSON number (e.g. 1)
    # - float JSON number that is integral (e.g. 1.0)
    # - float JSON number that is fractional (e.g. 1.5)
    # - string (to cause manual cast failure)
    id_type = draw(st.sampled_from(['int', 'float_integral', 'float_fractional', 'string']))
    if id_type == 'int':
        id_val = str(draw(st.integers(min_value=0, max_value=1000)))
    elif id_type == 'float_integral':
        # e.g. 1.0, 42.0
        v = draw(st.integers(min_value=0, max_value=1000))
        id_val = f"{v}.0"
    elif id_type == 'float_fractional':
        # e.g. 1.5, 42.7
        v_int = draw(st.integers(min_value=0, max_value=999))
        v_frac = draw(st.integers(min_value=1, max_value=9))
        id_val = f"{v_int}.{v_frac}"
    else:  # string
        id_val = json_string(draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"\\'))))

    # amount: always string, valid decimal-ish string
    amount_val = json_string(draw(st.decimals(min_value=0, max_value=10000, places=2).map(lambda d: format(d, 'f'))))

    # name: null or string (no divergence expected)
    name_val = draw(st.one_of(st.just("null"), st.text(min_size=0, max_size=10).map(json_string)))

    # status: enum string or unknown string or wrong type to cause divergence
    # Manual: ArgumentError on unknown string (undocumented)
    # json_serializable/freezed: CheckedFromJsonException on unknown string
    # built_value: ArgumentError wrapped in built_value error
    # So unknown enum strings cause divergence in error types.
    # Also try wrong type (number or null) to cause manual cast error.
    status_choice = draw(st.sampled_from([
        '"active"', '"inactive"', '"unknown"',  # valid enum strings
        '"invalid"', '"Active"', '"INACTIVE"',  # invalid enum strings (case sensitive)
        'null', '123', 'true'  # wrong types as JSON literals
    ]))

    # tags: array of strings normally
    # Manual and json_serializable/freezed cast elements as String, so non-string causes TypeError
    # built_value likely similar
    # To cause divergence, produce:
    # - empty array []
    # - array of strings
    # - array with one non-string element (number, null, bool)
    tags_type = draw(st.sampled_from(['empty', 'strings', 'mixed']))
    if tags_type == 'empty':
        tags_val = "[]"
    elif tags_type == 'strings':
        # 1 to 3 strings
        strs = draw(st.lists(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"\\')), min_size=1, max_size=3))
        tags_val = "[" + ",".join(json_string(s) for s in strs) + "]"
    else:  # mixed
        # 1 to 3 elements, at least one non-string
        n = draw(st.integers(min_value=1, max_value=3))
        elems = []
        for _ in range(n):
            elem_type = draw(st.sampled_from(['string', 'number', 'null', 'bool']))
            if elem_type == 'string':
                s = draw(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"\\')))
                elems.append(json_string(s))
            elif elem_type == 'number':
                # integer or float
                if draw(st.booleans()):
                    elems.append(str(draw(st.integers(min_value=0, max_value=100))))
                else:
                    elems.append(str(draw(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))))
            elif elem_type == 'null':
                elems.append("null")
            else:  # bool
                elems.append(draw(st.sampled_from(["true", "false"])))
        tags_val = "[" + ",".join(elems) + "]"

    # child: null or nested record (one level only)
    # To keep complexity bounded, child is either null or a well-formed record with no child (child=null)
    child_present = draw(st.booleans())
    if not child_present:
        child_val = "null"
    else:
        # Nested record with no child (child=null)
        # Use valid fields only to isolate divergence to top-level fields
        # id: int only to avoid nested divergence
        nested_id = str(draw(st.integers(min_value=0, max_value=1000)))
        nested_amount = json_string(draw(st.decimals(min_value=0, max_value=10000, places=2).map(lambda d: format(d, 'f'))))
        nested_name = draw(st.one_of(st.just("null"), st.text(min_size=0, max_size=10).map(json_string)))
        nested_status = draw(st.sampled_from(['"active"', '"inactive"', '"unknown"']))
        nested_tags = "[]"
        nested_child = "null"
        child_val = (
            "{" +
            f'"id":{nested_id},' +
            f'"amount":{nested_amount},' +
            f'"name":{nested_name},' +
            f'"status":{nested_status},' +
            f'"tags":{nested_tags},' +
            f'"child":{nested_child}' +
            "}"
        )

    # Compose full JSON object
    json_text = (
        "{" +
        f'"id":{id_val},' +
        f'"amount":{amount_val},' +
        f'"name":{name_val},' +
        f'"status":{status_choice},' +
        f'"tags":{tags_val},' +
        f'"child":{child_val}' +
        "}"
    )

    return json_text.encode('utf-8')