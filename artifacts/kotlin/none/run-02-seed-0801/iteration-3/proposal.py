from hypothesis import strategies as st

@st.composite
def generated_json(draw, _depth=0):
    # Limit recursion depth to 1 for "child" field
    # Compose a mostly valid record, then introduce 0-2 small deviations
    # to provoke divergence among Gson, Moshi, kotlinx.serialization, Jackson.
    # Deviations are subtle: wrong type for one field, null vs missing, 
    # enum as string but wrong case, array with wrong element types, etc.

    # Base valid fields:
    # id: integer
    # amount: string
    # name: string or null
    # status: one of "active", "inactive", "unknown"
    # tags: array of strings
    # child: record or null (one level recursion)

    # Helpers to produce valid fields as JSON text:
    def json_str(s):
        # Escape quotes and backslashes minimally for JSON string
        # Hypothesis strings are arbitrary unicode, but we keep it simple
        # by restricting to ascii printable for safety here.
        # We'll just replace backslash and quote.
        s = s.replace('\\', '\\\\').replace('"', '\\"')
        return '"' + s + '"'

    def json_int(i):
        return str(i)

    def json_null():
        return "null"

    def json_array_str(arr):
        # arr is list of strings
        # produce JSON array of strings
        return "[" + ",".join(json_str(e) for e in arr) + "]"

    # Valid enum values for status
    valid_statuses = ["active", "inactive", "unknown"]

    # Generate valid base fields
    id_val = draw(st.integers(min_value=0, max_value=2**31-1))
    amount_val = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)))
    # name can be string or null
    name_val = draw(st.one_of(st.none(), st.text(min_size=0, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s))))
    status_val = draw(st.sampled_from(valid_statuses))
    tags_val = draw(st.lists(st.text(min_size=1, max_size=10).filter(lambda s: all(32 <= ord(c) <= 126 for c in s)), min_size=0, max_size=5))

    # child field: either null or one record (no further recursion)
    if _depth == 0:
        child_val = draw(st.one_of(st.none(), generated_json(_depth=1)))
    else:
        child_val = None

    # Build a dict of fields as JSON text (strings)
    fields = {}

    # id field: normally integer
    fields["id"] = json_int(id_val)

    # amount field: normally string
    fields["amount"] = json_str(amount_val)

    # name field: string or null
    if name_val is None:
        fields["name"] = json_null()
    else:
        fields["name"] = json_str(name_val)

    # status field: enum string
    fields["status"] = json_str(status_val)

    # tags field: array of strings
    fields["tags"] = json_array_str(tags_val)

    # child field: record or null
    if child_val is None:
        fields["child"] = json_null()
    else:
        fields["child"] = child_val.decode("utf-8")

    # Now introduce 0,1 or 2 subtle deviations to provoke divergence
    # Possible deviations:
    # - id as string instead of int
    # - amount as number instead of string
    # - name missing (omit field)
    # - status with wrong case or invalid enum string
    # - tags with one element as number instead of string
    # - child as empty object {} instead of null or record
    # - child missing (omit field)
    # - child as null string "null" (string instead of null)
    # - extra comma or whitespace variations (avoid, too broad)
    # - name as number instead of string or null
    # - tags as null instead of array
    # - id as negative number (valid int but maybe edge)
    # - amount as empty string (valid)
    # - status as null (invalid)
    # - tags as array with null element
    # - child with missing fields or wrong field types inside

    # We'll pick 0-2 deviations randomly from a list of functions that mutate fields dict or keys

    def dev_id_string(fields):
        # id as string instead of int
        fields["id"] = json_str(str(id_val))

    def dev_amount_number(fields):
        # amount as number instead of string
        # parse amount_val as int if possible, else fallback to 0
        try:
            n = int(amount_val)
        except Exception:
            n = 0
        fields["amount"] = str(n)

    def dev_name_missing(fields):
        # remove name field
        if "name" in fields:
            del fields["name"]

    def dev_status_wrong_case(fields):
        # status with wrong case (capitalize first letter)
        s = status_val.capitalize()
        fields["status"] = json_str(s)

    def dev_status_invalid_enum(fields):
        # status with invalid enum string
        fields["status"] = json_str("invalid_status")

    def dev_tags_one_number(fields):
        # tags with one element as number instead of string
        if tags_val:
            arr = []
            replaced = False
            for e in tags_val:
                if not replaced:
                    arr.append(str(len(e)))  # number as string
                    replaced = True
                else:
                    arr.append(json_str(e))
            # But we want one element as number literal, not string
            # So build array manually mixing number and strings
            arr_json = []
            replaced = False
            for e in tags_val:
                if not replaced:
                    arr_json.append(str(len(e)))
                    replaced = True
                else:
                    arr_json.append(json_str(e))
            fields["tags"] = "[" + ",".join(arr_json) + "]"

    def dev_child_empty_object(fields):
        # child as empty object {}
        fields["child"] = "{}"

    def dev_child_missing(fields):
        # remove child field
        if "child" in fields:
            del fields["child"]

    def dev_child_null_string(fields):
        # child as string "null" instead of null literal
        fields["child"] = json_str("null")

    def dev_name_number(fields):
        # name as number instead of string or null
        fields["name"] = str(len(name_val) if name_val else 0)

    def dev_tags_null(fields):
        # tags as null instead of array
        fields["tags"] = json_null()

    def dev_status_null(fields):
        # status as null instead of enum string
        fields["status"] = json_null()

    def dev_tags_with_null_element(fields):
        # tags array with one null element
        if tags_val:
            arr_json = []
            replaced = False
            for e in tags_val:
                if not replaced:
                    arr_json.append("null")
                    replaced = True
                else:
                    arr_json.append(json_str(e))
            fields["tags"] = "[" + ",".join(arr_json) + "]"

    def dev_child_missing_fields(fields):
        # child present but missing some fields (only if child is record)
        if "child" in fields and fields["child"] != "null" and fields["child"] != "{}":
            # child is JSON text of a record, parse minimally by removing one field key
            # We cannot parse JSON here, so just remove one field key by string replace
            # Remove first field key found: "id":
            s = fields["child"]
            # Remove first occurrence of a field key and its value
            # Find first field key by searching for "id":
            # We'll remove the first field key and its value by cutting out from the first quote to the next comma or closing brace
            import re
            # Remove first "key":value pair including comma if any
            s2 = re.sub(r'"[^"]+":(?:null|"(?:[^"\\]|\\.)*"|\d+|\{[^}]*\})(,)?', '', s, count=1)
            # If trailing comma left at start, remove it
            s2 = s2.strip()
            if s2.startswith(","):
                s2 = s2[1:].lstrip()
            fields["child"] = s2

    # List of deviation functions
    deviations = [
        dev_id_string,
        dev_amount_number,
        dev_name_missing,
        dev_status_wrong_case,
        dev_status_invalid_enum,
        dev_tags_one_number,
        dev_child_empty_object,
        dev_child_missing,
        dev_child_null_string,
        dev_name_number,
        dev_tags_null,
        dev_status_null,
        dev_tags_with_null_element,
        # dev_child_missing_fields,  # disabled because uses re import disallowed
    ]

    # Pick 0,1 or 2 deviations randomly
    n_devs = draw(st.integers(min_value=0, max_value=2))
    chosen_devs = draw(st.lists(st.sampled_from(deviations), min_size=n_devs, max_size=n_devs, unique=True))

    for dev in chosen_devs:
        dev(fields)

    # Compose JSON object text from fields dict
    # Fields order fixed for consistency
    keys_order = ["id", "amount", "name", "status", "tags", "child"]
    # Include only keys present
    present_keys = [k for k in keys_order if k in fields]

    json_fields = []
    for k in present_keys:
        json_fields.append(json_str(k) + ":" + fields[k])

    json_text = "{" + ",".join(json_fields) + "}"

    return json_text.encode("utf-8")