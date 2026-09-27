```python
from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper: produce a JSON string literal from a Python string (with minimal escaping)
    def json_string(s: str) -> str:
        # Escape backslash and double quote and control chars minimally
        # We only need to produce valid JSON strings, so escape \ and "
        # and control chars as \uXXXX
        def escape_char(c):
            o = ord(c)
            if c == '"':
                return '\\"'
            elif c == '\\':
                return '\\\\'
            elif 0x20 <= o <= 0x10FFFF:
                return c
            else:
                return '\\u%04x' % o
        return '"' + ''.join(escape_char(c) for c in s) + '"'

    # Compose a JSON array of strings
    def json_array_of_strings(lst):
        # lst is list of strings
        return '[' + ','.join(json_string(s) for s in lst) + ']'

    # Compose a JSON object from a dict of key->value strings (already JSON encoded)
    def json_object(d):
        # d: dict of str->str (JSON encoded values)
        # keys are always JSON strings, so quote keys
        return '{' + ','.join(json_string(k) + ':' + v for k, v in d.items()) + '}'

    # Recursive generator for "child" field JSON text or "null"
    # Limit recursion depth to 1 (one level of recursion normally)
    def gen_record(depth=0):
        # id: integer
        # amount: string
        # name: string or null
        # status: enum string
        # tags: array of strings (empty strings allowed, no nulls)
        # child: record or null (only one level recursion normally)
        # We will produce a dict of JSON-encoded values (strings)

        # To induce subtle divergences, we vary one or two fields slightly off well-formed:
        # - sometimes omit a field (should be rejected by all)
        # - sometimes wrong type for a field (should be rejected by all)
        # - sometimes enum value slightly off (should be rejected by all)
        # - sometimes null in tags (should be rejected by all)
        # - sometimes duplicate keys with different values (last wins)
        # - sometimes empty string in tags (accepted by all)
        # - sometimes name null or string
        # - sometimes child null or nested record (depth limit)
        # - sometimes extra unknown fields (accepted by all)
        # - sometimes keys out of order (should not matter)
        # - sometimes whitespace (we omit for simplicity)
        # - sometimes numeric strings for amount (should be rejected)
        # - sometimes id as string (should be rejected)
        # - sometimes tags empty array or array with empty strings
        # - sometimes child missing required fields (should be rejected)
        # - sometimes duplicate keys in child

        # To maximize chance of divergence, we produce mostly well-formed records,
        # but with one subtle variation per record.

        # We will produce a dict of key->JSON text values (strings)

        # Decide on a "variation" mode for this record
        variation = draw(st.sampled_from([
            "valid",
            "id_string",          # id as string (should reject all)
            "amount_int",         # amount as int (reject all)
            "name_int",           # name as int (reject all)
            "status_invalid",     # status invalid enum (reject all)
            "tags_with_null",     # tags array contains null (reject all)
            "child_missing_field",# child present but missing required field (reject all)
            "child_null",         # child is null (valid)
            "tags_empty_strings", # tags array with empty strings (valid)
            "duplicate_keys",     # duplicate keys with different values (last wins)
            "extra_fields",       # extra unknown fields (valid)
            "missing_field",      # omit one required field (reject all)
            "name_null",          # name is null (valid)
            "tags_empty_array",   # tags empty array (valid)
            "child_valid",        # child is valid nested record (valid)
        ]))

        # Base well-formed values
        base_id = draw(st.integers(min_value=0, max_value=1000))
        base_amount = draw(st.text(min_size=1, max_size=10))
        base_name = draw(st.one_of(st.none(), st.text(min_size=1, max_size=10)))
        base_status = draw(st.sampled_from(STATUS_VALUES))
        base_tags = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=5))
        # ensure no null in tags for base
        base_tags = [s if s is not None else "" for s in base_tags]

        # Compose child record or null
        if depth == 0:
            # For child, either null or valid nested record or missing field or invalid status
            child_choice = draw(st.sampled_from(["null", "valid", "missing_field", "invalid_status"]))
            if child_choice == "null":
                child_json = "null"
            elif child_choice == "valid":
                child_json = gen_record(depth=depth+1)
            elif child_choice == "missing_field":
                # produce child missing a required field (e.g. omit "id")
                # build child dict manually with omission
                child_id = draw(st.integers(min_value=0, max_value=1000))
                child_amount = draw(st.text(min_size=1, max_size=10))
                child_name = draw(st.one_of(st.none(), st.text(min_size=1, max_size=10)))
                child_status = draw(st.sampled_from(STATUS_VALUES))
                child_tags = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=5))
                child_tags = [s if s is not None else "" for s in child_tags]
                # omit "id"
                child_dict = {
                    "amount": json_string(child_amount),
                    "name": json_string(child_name) if child_name is not None else "null",
                    "status": json_string(child_status),
                    "tags": json_array_of_strings(child_tags),
                    "child": "null",
                }
                child_json = json_object(child_dict)
            else:  # invalid_status
                child_id = draw(st.integers(min_value=0, max_value=1000))
                child_amount = draw(st.text(min_size=1, max_size=10))
                child_name = draw(st.one_of(st.none(), st.text(min_size=1, max_size=10)))
                child_status = "invalid_enum"
                child_tags = draw(st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=5))
                child_tags = [s if s is not None else "" for s in child_tags]
                child_dict = {
                    "id": str(child_id),
                    "amount": json_string(child_amount),
                    "name": json_string(child_name) if child_name is not None else "null",
                    "status": json_string(child_status),
                    "tags": json_array_of_strings(child_tags),
                    "child": "null",
                }
                child_json = json_object(child_dict)
        else:
            # depth > 0, no further recursion
            child_json = "null"

        # Now build the main record dict according to variation
        if variation == "valid":
            record_dict = {
                "id": str(base_id),
                "amount": json_string(base_amount),
                "name": json_string(base_name) if base_name is not None else "null",
                "status": json_string(base_status),
                "tags": json_array_of_strings(base_tags),
                "child": child_json,
            }
            # fix id to integer (not string)
            record_dict["id"] = str(base_id)
            # But id must be integer JSON, so no quotes
            record_dict["id"] = str(base_id)
        elif variation == "id_string":
            # id as string (should reject all)
            record_dict = {
                "id": json_string(str(base_id)),
                "amount": json_string(base_amount),
                "name": json_string(base_name) if base_name is not None else "null",
                "status": json_string(base_status),
                "tags": json_array_of_strings(base_tags),
                "child": child_json,
            }
        elif variation == "amount_int":
            # amount as int (reject all)
            record_dict = {
                "id": str(base_id),
                "amount": str(draw(st.integers(min_value=0, max_value=10000))),
                "name": json_string(base_name) if base_name is not None else "null",
                "status": json_string(base_status),
                "tags": json_array_of_strings(base_tags),
                "child": child_json,
            }
        elif variation == "name_int":
            # name as int (reject all)
            record_dict = {
                "id": str(base_id),
                "amount": json_string(base_amount),
                "name": str(draw(st.integers(min_value=0, max_value=10000))),
                "status": json_string(base_status),
                "tags": json_array_of_strings(base_tags),
                "child": child_json,
            }
        elif variation == "status_invalid":
            # invalid enum value for status (reject all)
            record_dict = {
                "id": str(base_id),
                "amount": json_string(base_amount),
                "name": json_string(base_name) if base_name is not None else "null",
                "status": json_string("invalid_enum_value"),
                "tags": json_array_of_strings(base_tags),
                "child": child_json,
            }
        elif variation == "tags_with_null":
            # tags array contains null (reject all)
            tags_with_null = base_tags + ["null"]
            # But "null" as string is allowed, we want actual JSON null
            # So we build tags array manually with one null element
            tags_json_parts = [json_string(s) for s in base_tags]
            tags_json_parts.append("null")
            tags_json = "[" + ",".join(tags_json_parts) + "]"
            record_dict = {
                "id": str(base_id),
                "amount": json_string(base_amount),
                "name": json_string(base_name) if base_name is not None else "null",
                "status": json_string(base_status),
                "tags": tags_json,
                "child": child_json,
            }
        elif variation == "child_missing_field":
            # child present but missing required field (reject all)
            # child_json already generated above for this case
            record_dict = {
                "id": str(base_id),
                "amount": json_string(base_amount),
                "name": json_string(base_name) if base_name is not None else "null",
                "status": json_string(base_status),
                "tags": json_array_of_strings(base_tags),
                "child": child_json,
            }
        elif variation == "child_null":
            record_dict = {
                "id": str(base_id),
                "amount": json_string(base_amount),
                "name": json_string(base_name) if base_name is not None else "null",
                "status": json_string(base_status),
                "tags": json_array_of_strings(base_tags),
                "child": "null",
            }
        elif variation == "tags_empty_strings":
            # tags array with empty strings (valid)
            tags_empty = [""] * draw(st.integers(min_value=0, max_value