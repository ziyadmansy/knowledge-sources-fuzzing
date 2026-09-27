from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Basic building blocks for fields, mostly valid but with small controlled deviations
    # to provoke divergence.
    
    # id: integer normally, but sometimes a string that looks like an int (to test type mismatch)
    id_valid = st.integers(min_value=0, max_value=10**9)
    id_invalid_str = st.text(min_size=1, max_size=10).filter(lambda s: not s.isdigit())
    id_field = st.one_of(id_valid.map(str), id_invalid_str).map(lambda s: s if s.isdigit() else s)
    # We'll produce id as a JSON number or JSON string (digits only) to test type mismatch subtly.
    # But since type mismatches on scalar fields are always rejected consistently,
    # this is low priority for divergence, so mostly produce valid int as number.
    id_field = st.one_of(
        id_valid.map(str),  # produce number as JSON number (string of digits)
        id_valid.map(lambda i: f'"{i}"'),  # produce number as JSON string of digits (type mismatch)
    )
    
    # amount: string normally, but sometimes a number (type mismatch)
    amount_valid = st.text(min_size=1, max_size=10).filter(lambda s: all(c.isdigit() or c in ".-" for c in s))
    amount_invalid_num = st.integers(min_value=-10000, max_value=10000).map(str)
    # We'll produce amount as JSON string normally, or as JSON number (type mismatch)
    amount_field = st.one_of(
        amount_valid.map(lambda s: f'"{s}"'),
        amount_invalid_num,  # number without quotes
    )
    
    # name: string or null normally, but sometimes number (type mismatch)
    name_valid = st.one_of(st.none(), st.text(min_size=0, max_size=10).map(lambda s: f'"{s}"'))
    name_invalid_num = st.integers(min_value=-1000, max_value=1000).map(str)
    name_field = st.one_of(name_valid, name_invalid_num)
    
    # status: enum "active", "inactive", "unknown" normally, but sometimes invalid enum string
    status_valid = st.sampled_from(['"active"', '"inactive"', '"unknown"'])
    status_invalid = st.text(min_size=1, max_size=10).filter(lambda s: s not in {"active","inactive","unknown"}).map(lambda s: f'"{s}"')
    # Mostly valid, sometimes invalid
    status_field = st.one_of(status_valid, status_invalid)
    
    # tags: array of strings normally, but sometimes empty array, or array with non-string (type mismatch)
    tag_str = st.text(min_size=1, max_size=5).map(lambda s: f'"{s}"')
    tags_valid = st.lists(tag_str, min_size=0, max_size=3).map(lambda lst: "[" + ",".join(lst) + "]")
    tags_invalid = st.one_of(
        st.just("123"),  # string instead of array
        st.just("null"),  # null instead of array
        st.just("[]"),  # empty array (valid)
        st.just("[123]"),  # array with number (type mismatch)
        st.just('["valid", 123]'),  # mixed types (type mismatch)
    )
    tags_field = st.one_of(tags_valid, tags_invalid)
    
    # child: null or nested record normally, but sometimes type mismatch or invalid enum inside
    # We'll build child recursively but only one level deep.
    # To avoid infinite recursion, define a helper inside.
    def child_record():
        # child can be null or a record
        # record fields same as top-level but no further nesting (child.child always null)
        id_c = id_valid.map(str)
        amount_c = amount_valid.map(lambda s: f'"{s}"')
        name_c = st.one_of(st.none(), st.text(min_size=0, max_size=10).map(lambda s: f'"{s}"'))
        status_c = status_valid
        tags_c = tags_valid
        # child.child always null to keep one level recursion
        child_child_c = st.just("null")
        
        # Compose child record JSON text
        def make_child_json(id_, amount_, name_, status_, tags_, child_):
            # name_ can be None (null) or string
            name_str = name_ if name_ is not None else "null"
            return (
                '{'
                f'"id":{id_},'
                f'"amount":{amount_},'
                f'"name":{name_str},'
                f'"status":{status_},'
                f'"tags":{tags_},'
                f'"child":{child_}'
                '}'
            )
        
        return st.tuples(id_c, amount_c, name_c, status_c, tags_c, child_child_c).map(
            lambda t: make_child_json(*t)
        )
    
    child_field = st.one_of(st.just("null"), child_record())
    
    # Compose top-level JSON object string
    def make_top_json(id_, amount_, name_, status_, tags_, child_):
        # name_ can be string or number or null (string or number or "null")
        return (
            '{'
            f'"id":{id_},'
            f'"amount":{amount_},'
            f'"name":{name_},'
            f'"status":{status_},'
            f'"tags":{tags_},'
            f'"child":{child_}'
            '}'
        )
    
    # Draw all fields
    id_ = draw(id_field)
    amount_ = draw(amount_field)
    name_ = draw(name_field)
    status_ = draw(status_field)
    tags_ = draw(tags_field)
    child_ = draw(child_field)
    
    json_text = make_top_json(id_, amount_, name_, status_, tags_, child_)
    return json_text.encode("utf-8")