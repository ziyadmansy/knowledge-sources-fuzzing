from hypothesis import strategies as st

@st.composite
def generated_json(draw, _depth=0):
    # Limit recursion depth to 1 for "child" field
    max_depth = 1

    # Basic field generators
    id_str = draw(st.integers(min_value=-(2**31), max_value=2**31-1).map(str))
    # amount: normally string, but try also numbers or null as edge cases
    # to provoke divergence, but mostly strings that look like numbers or weird strings
    amount_choice = draw(st.integers(min_value=0, max_value=9))
    if amount_choice == 0:
        # valid string number
        amount_str = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Nd',))))
    elif amount_choice == 1:
        # string with spaces or signs
        amount_str = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')))
    elif amount_choice == 2:
        # empty string
        amount_str = ""
    elif amount_choice == 3:
        # string "null" (not JSON null)
        amount_str = "null"
    elif amount_choice == 4:
        # string with unicode escapes (will be literal backslash-u)
        amount_str = "\\u1234"
    else:
        # normal numeric string
        amount_str = draw(st.integers(min_value=0, max_value=100000).map(str))

    # name: string or null or missing (simulate missing by empty string and omit later)
    # But missing fields break "well-formed" doc, so only null or string here
    # To provoke divergence, sometimes use JSON null, sometimes string "null"
    name_null_prob = draw(st.floats(min_value=0, max_value=1))
    if name_null_prob < 0.2:
        name_val = "null"  # string "null"
        name_json = '"name":"null"'
    elif name_null_prob < 0.4:
        name_val = None
        name_json = '"name":null'
    else:
        # normal string or empty string or string with escapes
        name_str = draw(st.text(min_size=0, max_size=15, alphabet=st.characters(blacklist_characters='"\\')))
        name_json = '"name":"' + name_str + '"'

    # status: one of "active", "inactive", "unknown" or sometimes invalid string or null
    status_choice = draw(st.integers(min_value=0, max_value=6))
    if status_choice == 0:
        status_json = '"status":"active"'
    elif status_choice == 1:
        status_json = '"status":"inactive"'
    elif status_choice == 2:
        status_json = '"status":"unknown"'
    elif status_choice == 3:
        # invalid string (to provoke rejection divergence)
        status_json = '"status":"actve"'  # typo
    elif status_choice == 4:
        # null instead of string
        status_json = '"status":null'
    elif status_choice == 5:
        # number instead of string
        status_json = '"status":123'
    else:
        # empty string
        status_json = '"status":""'

    # tags: array of strings, but sometimes empty array, sometimes array with null, sometimes array with numbers
    tags_choice = draw(st.integers(min_value=0, max_value=5))
    if tags_choice == 0:
        tags_json = '"tags":[]'
    elif tags_choice == 1:
        # array of normal strings
        tag_list = draw(st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')), max_size=5))
        tags_json = '"tags":[' + ",".join('"' + t + '"' for t in tag_list) + ']'
    elif tags_choice == 2:
        # array with null inside
        tag_list = draw(st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(blacklist_characters='"\\')), max_size=3))
        tags_json = '"tags":[' + ",".join('"' + t + '"' for t in tag_list) + ',null]'
    elif tags_choice == 3:
        # array with numbers inside (invalid)
        tag_list = draw(st.lists(st.integers(min_value=0, max_value=100), max_size=3))
        tags_json = '"tags":[' + ",".join(str(t) for t in tag_list) + ']'
    elif tags_choice == 4:
        # array with mixed strings and numbers
        tag_list_str = draw(st.lists(st.text(min_size=1, max_size=5, alphabet=st.characters(blacklist_characters='"\\')), max_size=2))
        tag_list_num = draw(st.lists(st.integers(min_value=0, max_value=10), max_size=2))
        mixed = []
        for i in range(max(len(tag_list_str), len(tag_list_num))):
            if i < len(tag_list_str):
                mixed.append('"' + tag_list_str[i] + '"')
            if i < len(tag_list_num):
                mixed.append(str(tag_list_num[i]))
        tags_json = '"tags":[' + ",".join(mixed) + ']'
    else:
        # array with empty string
        tags_json = '"tags":[""]'

    # child: either null or a nested record (one level only)
    if _depth < max_depth:
        child_choice = draw(st.integers(min_value=0, max_value=3))
        if child_choice == 0:
            child_json = '"child":null'
        else:
            # recursively generate child record with _depth+1
            child_record = draw(generated_json(_depth=_depth+1))
            child_json = '"child":' + child_record.decode('utf-8')
    else:
        child_json = '"child":null'

    # Compose all fields in a random order to provoke divergence on field order sensitivity
    fields = [
        '"id":' + id_str,
        '"amount":"' + amount_str + '"',
        name_json,
        status_json,
        tags_json,
        child_json,
    ]
    # Shuffle fields order
    draw(st.randoms())  # consume randomness
    import random
    random.shuffle(fields)

    json_text = "{" + ",".join(fields) + "}"
    return json_text.encode("utf-8")