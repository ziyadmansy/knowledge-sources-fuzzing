from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants for "status" enum
    statuses = ["active", "inactive", "unknown"]
    
    # Recursive strategy to generate a Record JSON string
    # with controlled recursion depth to avoid infinite recursion.
    def record_json(depth):
        # id: integer
        id_val = draw(st.integers(min_value=0, max_value=2**31-1))
        id_str = '"id":' + str(id_val)
        
        # amount: string (always present)
        # Use decimal-like strings, but also try edge cases like "0", "0.0", "1e10"
        amount_val = draw(st.one_of(
            st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789.eE+-" for c in s) and s.strip() != ""),
            st.just("0"),
            st.just("0.0"),
            st.just("1e10"),
            st.just("-123.45"),
        ))
        amount_str = '"amount":' + '"' + amount_val + '"'
        
        # name: string or null or missing (simulate missing by omitting field)
        # To maximize divergence, sometimes omit, sometimes null, sometimes string
        name_choice = draw(st.sampled_from(["present_string", "present_null", "missing"]))
        if name_choice == "present_string":
            # string or empty string or unicode
            name_val = draw(st.one_of(
                st.text(min_size=0, max_size=20),
                st.just(""),
                st.just("Δοκιμή"),  # unicode test
            ))
            name_str = '"name":' + ('"' + name_val.replace('"', '\\"') + '"')
        elif name_choice == "present_null":
            name_str = '"name":null'
        else:
            name_str = None  # missing
        
        # status: one of the enum strings or missing or invalid string
        # To trigger divergence, sometimes omit (built_value accepts), sometimes invalid string (all reject)
        status_choice = draw(st.sampled_from(["present_valid", "present_invalid", "missing"]))
        if status_choice == "present_valid":
            status_val = draw(st.sampled_from(statuses))
            status_str = '"status":' + '"' + status_val + '"'
        elif status_choice == "present_invalid":
            # invalid string not in enum, e.g. "pending", "null", "ACTIVE" (case sensitive)
            invalid_status = draw(st.sampled_from(["pending", "null", "ACTIVE", ""]))
            status_str = '"status":' + '"' + invalid_status + '"'
        else:
            status_str = None  # missing
        
        # tags: array of strings, or missing
        # To trigger divergence, sometimes missing (built_value accepts), sometimes empty array, sometimes array with empty string or unicode
        tags_choice = draw(st.sampled_from(["present_array", "missing"]))
        if tags_choice == "present_array":
            # array of strings, length 0 to 3
            tags_len = draw(st.integers(min_value=0, max_value=3))
            tags_elems = []
            for _ in range(tags_len):
                tag = draw(st.one_of(
                    st.text(min_size=0, max_size=10),
                    st.just(""),
                    st.just("✓"),
                    st.just("tag1"),
                    st.just("tag2"),
                ))
                # Escape quotes in tags
                tag_escaped = tag.replace('"', '\\"')
                tags_elems.append('"' + tag_escaped + '"')
            tags_str = '"tags":[' + ",".join(tags_elems) + ']'
        else:
            tags_str = None  # missing
        
        # child: null, missing, or nested record (one level only)
        # To maximize divergence, sometimes missing (accepted as null), sometimes null, sometimes nested record
        child_choice = draw(st.sampled_from(["present_null", "missing", "present_record"]))
        if child_choice == "present_null":
            child_str = '"child":null'
        elif child_choice == "missing":
            child_str = None
        else:
            # nested record, depth limited to 1
            # To avoid infinite recursion, nested record has no further child (always null)
            # Use a simpler nested record with all fields present and valid
            nested_id = draw(st.integers(min_value=0, max_value=2**31-1))
            nested_amount = draw(st.text(min_size=1, max_size=10).filter(lambda s: all(c in "0123456789.eE+-" for c in s) and s.strip() != ""))
            nested_name = draw(st.one_of(st.text(min_size=0, max_size=20), st.just(None)))
            nested_status = draw(st.sampled_from(statuses))
            nested_tags_len = draw(st.integers(min_value=0, max_value=2))
            nested_tags_elems = []
            for _ in range(nested_tags_len):
                t = draw(st.text(min_size=0, max_size=10))
                t_escaped = t.replace('"', '\\"')
                nested_tags_elems.append('"' + t_escaped + '"')
            nested_tags_str = "[" + ",".join(nested_tags_elems) + "]"
            nested_name_str = ('"' + nested_name.replace('"', '\\"') + '"') if nested_name is not None else "null"
            child_str = (
                '"child":{'
                + '"id":' + str(nested_id) + ","
                + '"amount":"' + nested_amount + '",'
                + '"name":' + nested_name_str + ","
                + '"status":"' + nested_status + '",'
                + '"tags":' + nested_tags_str + ","
                + '"child":null"
                + "}"
            )
        
        # Compose fields, omitting those that are None (missing)
        fields = [id_str, amount_str]
        if name_str is not None:
            fields.append(name_str)
        if status_str is not None:
            fields.append(status_str)
        if tags_str is not None:
            fields.append(tags_str)
        if child_str is not None:
            fields.append(child_str)
        
        # Shuffle fields order to avoid positional bias
        # Hypothesis does not have a direct shuffle, but we can draw a permutation of indices
        import itertools
        indices = list(range(len(fields)))
        perm = draw(st.permutations(indices))
        fields_shuffled = [fields[i] for i in perm]
        
        json_obj = "{" + ",".join(fields_shuffled) + "}"
        return json_obj
    
    # Draw the top-level record JSON string with depth 0
    json_text = record_json(depth=0)
    return json_text.encode("utf-8")