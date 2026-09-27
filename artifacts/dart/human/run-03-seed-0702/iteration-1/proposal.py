from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for status field
    statuses = ["active", "inactive", "unknown"]

    # Recursive record generator, depth limited to 1 for "child"
    # Returns a dict with all fields present and well-formed
    def record_strategy(depth=0):
        # id: integer (Dart int), but to provoke divergence,
        # sometimes produce a number outside 64-bit int range as JSON number,
        # which json_serializable/freezed accept but manual/built_value reject.
        # We'll produce int in range -2**63 to 2**63-1 mostly,
        # but sometimes produce a float representing out-of-range int.
        def id_value():
            # 80% chance normal int64 range, 20% chance out-of-range double
            normal_int = st.integers(min_value=-(2**63), max_value=2**63 - 1)
            out_of_range_double = st.one_of(
                st.floats(min_value=-(2**63)*10, max_value=-(2**63)-1, allow_infinity=False, allow_nan=False),
                st.floats(min_value=2**63, max_value=(2**63)*10, allow_infinity=False, allow_nan=False),
            )
            return st.one_of(normal_int, out_of_range_double)

        # amount: string, always present, non-null
        amount_str = st.text(min_size=1, max_size=10)

        # name: nullable string
        name_str = st.one_of(st.none(), st.text(min_size=0, max_size=10))

        # status: one of the three strings
        status_str = st.sampled_from(statuses)

        # tags: array of strings, always present
        # To provoke divergence, sometimes produce empty list, sometimes non-empty,
        # but always present (never missing)
        tags_arr = st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5)

        # child: nullable record, only one level recursion allowed
        if depth == 0:
            child_rec = st.one_of(st.none(), record_strategy(depth=1))
        else:
            child_rec = st.none()

        # Compose the record dict
        return st.fixed_dictionaries({
            "id": id_value(),
            "amount": amount_str,
            "name": name_str,
            "status": status_str,
            "tags": tags_arr,
            "child": child_rec,
        })

    # Generate a well-formed record dict
    base_record = draw(record_strategy())

    # Now, to provoke divergence, we produce JSON text with exactly these fields,
    # but we will sometimes:
    # - omit "tags" field (only built_value accepts missing tags)
    # - or produce "tags" with wrong type (all reject)
    # - or produce "id" as out-of-range double (manual and built_value reject, others accept)
    # - or produce "name" or "child" as missing (all accept)
    # - or produce "name" or "child" as null (all accept)
    # - or produce extra unknown keys (all accept)
    # - or produce "status" with invalid string (all reject)
    # - or produce "amount" as null or wrong type (all reject)
    # We want to vary only one or two things at a time.

    # Choose one or two "quirks" to apply
    quirks = []

    # 20% chance omit "tags" field (to test built_value acceptance)
    if draw(st.booleans()):
        quirks.append("omit_tags")

    # 10% chance produce "tags" as wrong type (e.g. string)
    if draw(st.booleans()):
        quirks.append("wrong_tags_type")

    # 30% chance produce "id" as out-of-range double (if not already out-of-range)
    # We detect if id is int or float by type, but we forced id_value to sometimes be float.
    # We'll forcibly replace id with out-of-range double here if chosen.
    if draw(st.booleans()):
        quirks.append("id_out_of_range_double")

    # 10% chance omit "name" (nullable, all accept)
    if draw(st.booleans()):
        quirks.append("omit_name")

    # 10% chance omit "child" (nullable, all accept)
    if draw(st.booleans()):
        quirks.append("omit_child")

    # 10% chance add extra unknown key (all accept)
    if draw(st.booleans()):
        quirks.append("extra_key")

    # 10% chance produce invalid status string (all reject)
    if draw(st.booleans()):
        quirks.append("invalid_status")

    # 10% chance produce amount as null (all reject)
    if draw(st.booleans()):
        quirks.append("amount_null")

    # Apply quirks carefully, but limit to max 2 quirks to keep "almost well-formed"
    if len(quirks) > 2:
        quirks = draw(st.lists(st.sampled_from(quirks), min_size=1, max_size=2, unique=True))

    # Start building JSON text manually
    # Helper to JSON-encode strings (simple escaping)
    def json_str(s):
        # Escape backslash and double quote and control chars minimally
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        s = s.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        # Control characters below 0x20 replaced with \u00XX
        def esc_char(c):
            if ord(c) < 0x20:
                return "\\u%04x" % ord(c)
            return c
        s = "".join(esc_char(c) for c in s)
        return '"' + s + '"'

    # Helper to encode JSON values (string, int, float, null, array, object)
    def encode_json_value(v):
        if v is None:
            return "null"
        elif isinstance(v, bool):
            return "true" if v else "false"
        elif isinstance(v, int):
            return str(v)
        elif isinstance(v, float):
            # JSON floats must have decimal point or exponent
            # Use repr to get decimal point or exponent
            s = repr(v)
            # repr may produce 'nan', 'inf' - invalid JSON, but Hypothesis floats disallow those
            if "e" not in s and "." not in s:
                s += ".0"
            return s
        elif isinstance(v, str):
            return json_str(v)
        elif isinstance(v, list):
            return "[" + ",".join(encode_json_value(x) for x in v) + "]"
        elif isinstance(v, dict):
            items = []
            for k, val in v.items():
                items.append(json_str(k) + ":" + encode_json_value(val))
            return "{" + ",".join(items) + "}"
        else:
            # Should not happen
            return "null"

    # Build the dict to encode, starting from base_record
    doc = dict(base_record)

    # Apply quirks:

    # omit_tags: remove "tags" field
    if "omit_tags" in quirks:
        doc.pop("tags", None)

    # wrong_tags_type: replace "tags" with a string (wrong type)
    if "wrong_tags_type" in quirks:
        doc["tags"] = "not-an-array"

    # id_out_of_range_double: forcibly replace id with out-of-range double
    if "id_out_of_range_double" in quirks:
        # Pick an out-of-range double value
        out_of_range_double = draw(
            st.one_of(
                st.floats(min_value=-(2**63)*10, max_value=-(2**63)-1, allow_infinity=False, allow_nan=False),
                st.floats(min_value=2**63, max_value=(2**63)*10, allow_infinity=False, allow_nan=False),
            )
        )
        doc["id"] = out_of_range_double

    # omit_name: remove "name" field
    if "omit_name" in quirks:
        doc.pop("name", None)

    # omit_child: remove "child" field
    if "omit_child" in quirks:
        doc.pop("child", None)

    # extra_key: add an unknown key with string value
    if "extra_key" in quirks:
        doc["extra_unknown_key"] = "extra_value"

    # invalid_status: replace status with invalid string
    if "invalid_status" in quirks:
        # Pick a string not in statuses
        invalid_status = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in statuses))
        doc["status"] = invalid_status

    # amount_null: replace amount with null
    if "amount_null" in quirks:
        doc["amount"] = None

    # Now encode doc as JSON text (object)
    json_text = encode_json_value(doc)

    # Return bytes
    return json_text.encode("utf-8")