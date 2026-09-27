from hypothesis import strategies as st

# Constants for allowed enum values
STATUS_VALUES = ['active', 'inactive', 'unknown']

# Helper to produce JSON string literals with proper escaping of " and \
# We only need to escape " and \ for JSON strings here.
def json_string_literal(s: str) -> str:
    # Escape backslash and double quote
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + s + '"'

@st.composite
def generated_json(draw) -> bytes:
    """
    Generate syntactically valid JSON objects as bytes, representing the Record schema,
    with subtle variations to provoke divergence among four Dart JSON deserializers.
    """

    # Strategy to produce a valid "id" integer
    id_val = draw(st.integers(min_value=0, max_value=10**9))

    # Strategy to produce a valid "amount" string (non-empty, numeric-ish or arbitrary)
    # Use digits and optionally a decimal point or currency symbol to look realistic
    amount_val = draw(
        st.one_of(
            st.text(alphabet='0123456789.', min_size=1, max_size=10),
            st.text(alphabet='0123456789.,$', min_size=1, max_size=10),
        )
    )
    # Sanitize amount_val to avoid invalid JSON string chars (just escape " and \)
    amount_val = amount_val.replace('\\', '\\\\').replace('"', '\\"')

    # Strategy for "name": either null or a string (possibly empty)
    # To provoke divergence, sometimes produce empty string, sometimes normal strings
    name_val = draw(
        st.one_of(
            st.none(),
            st.text(
                alphabet=(
                    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '
                    '.,-\'"'
                ),
                min_size=0,
                max_size=20,
            ),
        )
    )
    # Escape name_val if string
    if isinstance(name_val, str):
        name_val = name_val.replace('\\', '\\\\').replace('"', '\\"')

    # Strategy for "status": one of the allowed strings, but sometimes with subtle case changes
    # To provoke divergence, mostly valid, but sometimes slightly off case or whitespace
    status_val = draw(
        st.one_of(
            st.sampled_from(STATUS_VALUES),
            # subtle invalid variants that might cause different errors
            st.just('Active'),
            st.just('inactive '),
            st.just('unknown\n'),
        )
    )

    # Strategy for "tags": array of strings (possibly empty)
    # To provoke divergence, sometimes empty array, sometimes with empty strings or whitespace strings
    tags_len = draw(st.integers(min_value=0, max_value=5))
    tags_vals = []
    for _ in range(tags_len):
        tag = draw(
            st.one_of(
                st.text(
                    alphabet='abcdefghijklmnopqrstuvwxyz0123456789_- ',
                    min_size=0,
                    max_size=10,
                ),
                # edge case: empty string tag
                st.just(''),
                # whitespace string tag
                st.just(' '),
            )
        )
        tag = tag.replace('\\', '\\\\').replace('"', '\\"')
        tags_vals.append(tag)

    # Strategy for "child": either null or a nested Record (one level only)
    # To provoke divergence, sometimes produce null, sometimes valid nested record,
    # sometimes a record with one field subtly off type or missing.
    # We limit recursion depth to 1 here.

    # Define a helper to produce a nested child record JSON string (no recursion deeper than 1)
    def child_record():
        # id int
        cid = draw(st.integers(min_value=0, max_value=10**9))
        # amount string
        camount = draw(
            st.text(alphabet='0123456789.', min_size=1, max_size=10)
        ).replace('\\', '\\\\').replace('"', '\\"')
        # name string or null
        cname = draw(
            st.one_of(
                st.none(),
                st.text(
                    alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ',
                    min_size=0,
                    max_size=20,
                ),
            )
        )
        if isinstance(cname, str):
            cname = cname.replace('\\', '\\\\').replace('"', '\\"')
        # status one of allowed strings (valid only here to keep child mostly valid)
        cstatus = draw(st.sampled_from(STATUS_VALUES))
        # tags array of strings (empty or small)
        ctags_len = draw(st.integers(min_value=0, max_value=3))
        ctags = []
        for _ in range(ctags_len):
            t = draw(
                st.text(
                    alphabet='abcdefghijklmnopqrstuvwxyz0123456789_- ',
                    min_size=0,
                    max_size=10,
                )
            )
            t = t.replace('\\', '\\\\').replace('"', '\\"')
            ctags.append(t)
        # child: null only (no deeper recursion)
        cchild = 'null'

        # Compose child JSON string
        parts = [
            '"id":' + str(cid),
            '"amount":"' + camount + '"',
            '"name":' + ('null' if cname is None else json_string_literal(cname)),
            '"status":' + json_string_literal(cstatus),
            '"tags":[' + ','.join(json_string_literal(t) for t in ctags) + ']',
            '"child":' + cchild,
        ]
        return '{' + ','.join(parts) + '}'

    # Decide child field value
    child_choice = draw(st.integers(min_value=0, max_value=9))
    if child_choice == 0:
        # null child
        child_val = 'null'
    elif child_choice <= 7:
        # valid nested child record
        child_val = child_record()
    else:
        # subtle invalid child: empty object {} (known to be rejected by all)
        # or child with missing required field or wrong type to provoke divergence
        # We choose a child with missing "amount" field (should cause rejection)
        cid = draw(st.integers(min_value=0, max_value=10**9))
        cname = draw(
            st.one_of(
                st.none(),
                st.text(
                    alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ',
                    min_size=0,
                    max_size=20,
                ),
            )
        )
        if isinstance(cname, str):
            cname = cname.replace('\\', '\\\\').replace('"', '\\"')
        cstatus = draw(st.sampled_from(STATUS_VALUES))
        ctags_len = draw(st.integers(min_value=0, max_value=3))
        ctags = []
        for _ in range(ctags_len):
            t = draw(
                st.text(
                    alphabet='abcdefghijklmnopqrstuvwxyz0123456789_- ',
                    min_size=0,
                    max_size=10,
                )
            )
            t = t.replace('\\', '\\\\').replace('"', '\\"')
            ctags.append(t)
        # Compose child JSON string missing "amount" field (should cause rejection)
        parts = [
            '"id":' + str(cid),
            # '"amount":' missing
            '"name":' + ('null' if cname is None else json_string_literal(cname)),
            '"status":' + json_string_literal(cstatus),
            '"tags":[' + ','.join(json_string_literal(t) for t in ctags) + ']',
            '"child":null',
        ]
        child_val = '{' + ','.join(parts) + '}'

    # Compose top-level JSON object string with one or two subtle variations to provoke divergence:
    # 1) For "status", sometimes use invalid variants (case or whitespace)
    # 2) For "name", sometimes null or string
    # 3) For "tags", sometimes empty or with empty strings
    # 4) For "child", as above

    # Compose JSON string parts for top-level
    parts = [
        '"id":' + str(id_val),
        '"amount":"' + amount_val + '"',
        '"name":' + ('null' if name_val is None else json_string_literal(name_val)),
        '"status":' + json_string_literal(status_val),
        '"tags":[' + ','.join(json_string_literal(t) for t in tags_vals) + ']',
        '"child":' + child_val,
    ]

    # Occasionally add an extra unknown field to top-level or child to confirm ignored fields do not cause divergence
    add_extra_field = draw(st.booleans())
    if add_extra_field:
        # Add an extra field with a simple string value
        extra_key = draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=5))
        extra_key = extra_key.replace('\\', '\\\\').replace('"', '\\"')
        extra_val = draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=1, max_size=10))
        extra_val = extra_val.replace('\\', '\\\\').replace('"', '\\"')
        parts.append('"' + extra_key + '":"' + extra_val + '"')

    json_str = '{' + ','.join(parts) + '}'

    # Return as bytes
    return json_str.encode('utf-8')