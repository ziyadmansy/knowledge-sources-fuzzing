from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status enum and nullability
    STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
    # We allow null for name and child, but not for status except Gson accepts null (probe 11)
    # We'll produce mostly valid status, sometimes unknown string or null to trigger divergence.
    # For id: integer or string containing integer
    # For amount: string or number (kotlinx rejects number)
    # For name: string, null, or number (kotlinx rejects number)
    # For tags: array of strings normally, but sometimes with non-string elements (kotlinx rejects non-string)
    # For child: null or nested record or empty object (Gson accepts empty object as child, others reject)
    # Also test unknown fields presence (Gson, Moshi accept; kotlinx, Jackson reject)
    # Duplicate keys: last wins, so we can add duplicates for id or others to see if they differ.

    # Helper to produce id field value (int or string containing int)
    def id_value():
        val = draw(st.integers(min_value=0, max_value=10**9))
        as_string = draw(st.booleans())
        if as_string:
            return '"' + str(val) + '"'
        else:
            return str(val)

    # Helper to produce amount field value (string or number)
    def amount_value():
        # 70% string, 30% number to trigger kotlinx rejection on number
        use_number = draw(st.booleans())
        if use_number:
            # number as int or float string (float triggers rejection too)
            if draw(st.booleans()):
                # int number
                return str(draw(st.integers(min_value=0, max_value=10**6)))
            else:
                # float number with decimal point
                f = draw(st.floats(min_value=0, max_value=10**6, allow_infinity=False, allow_nan=False))
                # format float with minimal decimal places
                return repr(f)
        else:
            # string containing number or arbitrary string
            # 80% numeric string, 20% arbitrary string
            if draw(st.booleans()):
                return '"' + str(draw(st.integers(min_value=0, max_value=10**6))) + '"'
            else:
                # arbitrary string (non-numeric)
                s = draw(st.text(min_size=1, max_size=10))
                # escape quotes and backslashes
                s = s.replace('\\', '\\\\').replace('"', '\\"')
                return '"' + s + '"'

    # Helper to produce name field value (string, null, or number)
    def name_value():
        choice = draw(st.integers(min_value=0, max_value=3))
        if choice == 0:
            # null
            return "null"
        elif choice == 1:
            # string
            s = draw(st.text(min_size=0, max_size=20))
            s = s.replace('\\', '\\\\').replace('"', '\\"')
            return '"' + s + '"'
        else:
            # number (int or float)
            if draw(st.booleans()):
                return str(draw(st.integers(min_value=-1000, max_value=1000)))
            else:
                f = draw(st.floats(min_value=-1000, max_value=1000, allow_infinity=False, allow_nan=False))
                return repr(f)

    # Helper to produce status field value
    def status_value():
        # 80% valid enum string, 10% unknown string, 10% null
        p = draw(st.integers(min_value=1, max_value=100))
        if p <= 80:
            return draw(st.sampled_from(STATUS_VALUES))
        elif p <= 90:
            # unknown string (not in enum)
            s = draw(st.text(min_size=1, max_size=10))
            # ensure not one of the enum values
            while s in ['active', 'inactive', 'unknown']:
                s = draw(st.text(min_size=1, max_size=10))
            s = s.replace('\\', '\\\\').replace('"', '\\"')
            return '"' + s + '"'
        else:
            return "null"

    # Helper to produce tags array
    def tags_value():
        # 70% all strings, 30% some non-string elements (int, null)
        all_strings = draw(st.booleans())
        length = draw(st.integers(min_value=0, max_value=5))
        elements = []
        for _ in range(length):
            if all_strings:
                s = draw(st.text(min_size=0, max_size=10))
                s = s.replace('\\', '\\\\').replace('"', '\\"')
                elements.append('"' + s + '"')
            else:
                # non-string element: int, null, bool
                choice = draw(st.integers(min_value=0, max_value=3))
                if choice == 0:
                    # string
                    s = draw(st.text(min_size=0, max_size=10))
                    s = s.replace('\\', '\\\\').replace('"', '\\"')
                    elements.append('"' + s + '"')
                elif choice == 1:
                    elements.append(str(draw(st.integers(min_value=-1000, max_value=1000))))
                elif choice == 2:
                    elements.append("null")
                else:
                    elements.append("true" if draw(st.booleans()) else "false")
        return "[" + ",".join(elements) + "]"

    # Recursive child record generator with bounded depth
    def child_value(depth):
        if depth <= 0:
            # only null or empty object (to trigger Gson acceptance of empty object)
            choice = draw(st.integers(min_value=0, max_value=2))
            if choice == 0:
                return "null"
            elif choice == 1:
                # empty object {}
                return "{}"
            else:
                # valid nested record with minimal fields
                return nested_record(depth - 1)
        else:
            # 50% null, 40% valid nested record, 10% empty object
            p = draw(st.integers(min_value=1, max_value=100))
            if p <= 50:
                return "null"
            elif p <= 90:
                return nested_record(depth - 1)
            else:
                return "{}"

    # Nested record generator (no unknown fields here, unknown fields added only at top level)
    def nested_record(depth):
        # id, amount, name, status, tags, child
        idv = id_value()
        amountv = amount_value()
        namev = name_value()
        statusv = status_value()
        tagsv = tags_value()
        childv = child_value(depth)
        fields = [
            '"id":' + idv,
            '"amount":' + amountv,
            '"name":' + namev,
            '"status":' + statusv,
            '"tags":' + tagsv,
            '"child":' + childv,
        ]
        return "{" + ",".join(fields) + "}"

    # Compose top-level record
    idv = id_value()
    amountv = amount_value()
    namev = name_value()
    statusv = status_value()
    tagsv = tags_value()
    childv = child_value(depth=1)

    # Possibly add unknown extra fields at top level (Gson, Moshi accept; kotlinx, Jackson reject)
    # 50% chance to add 0-2 unknown fields
    unknown_fields = []
    if draw(st.booleans()):
        n_unknown = draw(st.integers(min_value=1, max_value=2))
        for i in range(n_unknown):
            key = "unknown" + str(i)
            # unknown field value: string or number or null
            val_choice = draw(st.integers(min_value=0, max_value=2))
            if val_choice == 0:
                val = '"' + draw(st.text(min_size=1, max_size=10)).replace('\\', '\\\\').replace('"', '\\"') + '"'
            elif val_choice == 1:
                val = str(draw(st.integers(min_value=-1000, max_value=1000)))
            else:
                val = "null"
            unknown_fields.append('"' + key + '":' + val)

    # Possibly add duplicate keys for id or amount or name (last wins)
    # 30% chance to add duplicate keys
    duplicates = []
    if draw(st.booleans()):
        # duplicate id
        dup_id_val = id_value()
        duplicates.append('"id":' + dup_id_val)
    if draw(st.booleans()):
        # duplicate amount
        dup_amount_val = amount_value()
        duplicates.append('"amount":' + dup_amount_val)
    if draw(st.booleans()):
        # duplicate name
        dup_name_val = name_value()
        duplicates.append('"name":' + dup_name_val)

    # Build fields list in random order to mix duplicates and unknown fields
    base_fields = [
        '"id":' + idv,
        '"amount":' + amountv,
        '"name":' + namev,
        '"status":' + statusv,
        '"tags":' + tagsv,
        '"child":' + childv,
    ]

    all_fields = base_fields + unknown_fields + duplicates
    # Shuffle fields to randomize order (duplicates can appear anywhere)
    all_fields = draw(st.permutations(all_fields))

    json_text = "{" + ",".join(all_fields) + "}"
    return json_text.encode("utf-8")