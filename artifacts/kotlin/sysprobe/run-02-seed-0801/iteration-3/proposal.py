from hypothesis import strategies as st

# Constants for enum values and max recursion depth
STATUS_VALUES = ['"active"', '"inactive"', '"unknown"']
MAX_DEPTH = 1  # one level of recursion normally

def json_string_escape(s: str) -> str:
    # Minimal escaping for JSON strings: backslash and quote
    return s.replace('\\', '\\\\').replace('"', '\\"')

@st.composite
def generated_json(draw, depth=0) -> st.SearchStrategy[str]:
    """
    Generate JSON text for the record schema with controlled malformations
    to maximize divergence between Gson, Moshi, kotlinx.serialization, and Jackson.
    Produces a JSON string (bytes can be obtained by encoding outside if needed).
    """

    # Helper: generate JSON string literal with optional null or wrong types
    def gen_string_field(field_name, nullable=True):
        # According to known behavior:
        # - amount: string, non-nullable
        # - name: string or null, nullable
        # We want to sometimes produce:
        # - correct string
        # - null (if nullable)
        # - number (to test type coercion)
        # - missing (handled outside)
        # - null for non-nullable (to test Gson acceptance)
        # - wrong types (bool, array) rarely to trigger rejections

        # For amount (non-nullable string), allow null to trigger Gson acceptance
        # For name (nullable string), allow null normally

        # We produce a tuple (field_json_text or None if missing)
        # We do not produce missing here, missing handled outside

        # Compose possible values:
        # - valid string
        # - null (if nullable or forced)
        # - number (int or float) as JSON number (no quotes)
        # - boolean true/false
        # - empty array []
        # - empty object {}

        # We bias towards valid string and null (if nullable)
        # but include wrong types with small probability

        # Generate a string value
        s = draw(st.text(min_size=0, max_size=10))
        s_escaped = json_string_escape(s)
        valid_str = f'"{s_escaped}"'

        # Wrong types
        number = draw(st.one_of(st.integers(min_value=-1000, max_value=1000).map(str),
                               st.floats(allow_nan=False, allow_infinity=False).map(lambda f: f'{f:.3f}')))
        boolean = draw(st.booleans().map(lambda b: "true" if b else "false"))
        empty_array = "[]"
        empty_object = "{}"

        choices = [valid_str]
        if nullable:
            choices.append("null")
        # Add wrong types rarely
        choices.extend([number, boolean, empty_array, empty_object])

        # Weight valid string highest, then null if allowed, then others
        weights = []
        for c in choices:
            if c == valid_str:
                weights.append(50)
            elif c == "null":
                weights.append(20)
            else:
                weights.append(5)

        chosen = draw(st.sampled_from(choices).filter(lambda _: True).flatmap(lambda c: st.just(c)))
        # Actually use weighted sampling
        # Hypothesis does not have weighted sampling directly, so simulate by repeating
        weighted_choices = []
        for c, w in zip(choices, weights):
            weighted_choices.extend([c]*w)
        chosen = draw(st.sampled_from(weighted_choices))
        return f'"{field_name}":{chosen}'

    # Helper: generate JSON integer field with possible null or missing
    def gen_int_field(field_name, nullable=False):
        # id: integer, non-nullable
        # Gson accepts null as 0, others reject null for non-nullable
        # We want to produce:
        # - valid integer
        # - null (to test Gson acceptance)
        # - string number (wrong type)
        # - missing (handled outside)
        # - boolean (wrong type)
        # - float (wrong type)
        # - empty array/object (wrong type)

        valid_int = str(draw(st.integers(min_value=0, max_value=1000000)))

        # String number (wrong type)
        str_num = f'"{valid_int}"'

        boolean = "true" if draw(st.booleans()) else "false"
        float_num = f'{draw(st.floats(min_value=0, max_value=1000000, allow_nan=False, allow_infinity=False)):.3f}'
        empty_array = "[]"
        empty_object = "{}"

        choices = [valid_int, str_num]
        if nullable:
            choices.append("null")
        # Add wrong types rarely
        choices.extend([boolean, float_num, empty_array, empty_object])

        weights = []
        for c in choices:
            if c == valid_int:
                weights.append(50)
            elif c == str_num:
                weights.append(10)
            elif c == "null":
                weights.append(20)
            else:
                weights.append(5)

        weighted_choices = []
        for c, w in zip(choices, weights):
            weighted_choices.extend([c]*w)
        chosen = draw(st.sampled_from(weighted_choices))
        return f'"{field_name}":{chosen}'

    # Helper: generate enum field "status"
    def gen_enum_field(field_name, nullable=False):
        # status: enum, non-nullable
        # Gson accepts missing enum as null, unknown enum as null
        # Moshi, kotlinx.serialization reject missing or unknown enum values
        # Jackson accepts missing enum as null, rejects unknown enum values
        # Gson accepts case variants as null, others reject

        # We produce:
        # - valid enum (correct case)
        # - missing (handled outside)
        # - null (to test Gson acceptance)
        # - unknown enum (string not in enum)
        # - case variant of enum
        # - wrong type (number, bool, array, object)

        valid_enum = draw(st.sampled_from(STATUS_VALUES))

        # Case variant: randomly uppercase or lowercase entire string (without quotes)
        base = valid_enum.strip('"')
        case_variant = '"' + draw(st.sampled_from([base.upper(), base.lower()])) + '"'

        unknown_enum = '"' + draw(st.text(min_size=3, max_size=8).filter(lambda s: s.lower() not in ['active', 'inactive', 'unknown'])) + '"'

        boolean = "true" if draw(st.booleans()) else "false"
        number = str(draw(st.integers(min_value=0, max_value=1000)))
        empty_array = "[]"
        empty_object = "{}"
        null_val = "null"

        choices = [valid_enum]
        if nullable:
            choices.append(null_val)
        choices.extend([case_variant, unknown_enum, boolean, number, empty_array, empty_object])
        weights = []
        for c in choices:
            if c == valid_enum:
                weights.append(50)
            elif c == null_val:
                weights.append(20)
            elif c == case_variant:
                weights.append(10)
            elif c == unknown_enum:
                weights.append(5)
            else:
                weights.append(3)

        weighted_choices = []
        for c, w in zip(choices, weights):
            weighted_choices.extend([c]*w)
        chosen = draw(st.sampled_from(weighted_choices))
        return f'"{field_name}":{chosen}'

    # Helper: generate tags array field
    def gen_tags_field(field_name, nullable=False):
        # tags: array of strings, non-nullable
        # Gson accepts null as null, others reject null for non-nullable
        # Gson accepts wrong types inside array? Unknown, but we can try
        # Moshi rejects duplicates? Not tested explicitly, but we can try duplicates
        # Gson accepts extra unknown keys and duplicates silently

        # We produce:
        # - valid array of strings
        # - empty array
        # - null (to test Gson acceptance)
        # - array with wrong types inside (numbers, bools, nulls)
        # - wrong type (string, number, bool, object)
        # - missing (handled outside)

        # Generate array elements
        def gen_tag_element():
            # Mostly strings, sometimes wrong types
            s = draw(st.text(min_size=0, max_size=10))
            s_escaped = json_string_escape(s)
            str_val = f'"{s_escaped}"'
            wrong_types = ["null", "true", "false", "123", "[]", "{}"]
            choices = [str_val] * 10 + wrong_types
            chosen = draw(st.sampled_from(choices))
            return chosen

        # Generate array length 0..5
        length = draw(st.integers(min_value=0, max_value=5))
        elements = [gen_tag_element() for _ in range(length)]

        # Possibly add duplicates with some probability
        if length > 0 and draw(st.booleans()):
            # duplicate one element
            dup_idx = draw(st.integers(min_value=0, max_value=length-1))
            elements.append(elements[dup_idx])

        arr = "[" + ",".join(elements) + "]"

        # Wrong types for entire field
        wrong_types = [
            "null",
            f'"{draw(st.text(min_size=0, max_size=10))}"',
            "123",
            "true",
            "false",
            "{}"
        ]

        choices = [arr] * 10 + wrong_types
        weights = [50 if c == arr else 5 for c in choices]

        weighted_choices = []
        for c, w in zip(choices, weights):
            weighted_choices.extend([c]*w)
        chosen = draw(st.sampled_from(weighted_choices))
        return f'"{field_name}":{chosen}'

    # Helper: generate child field (recursive Record or null)
    def gen_child_field(field_name, depth):
        # child: Record or null, nullable
        # Gson accepts null for non-nullable fields, Moshi rejects missing nested objects,
        # kotlinx.serialization rejects missing nested objects,
        # Jackson accepts missing nested objects but rejects null nested objects if non-nullable

        # We produce:
        # - valid nested record (depth+1)
        # - null
        # - missing (handled outside)
        # - wrong types (string, number, bool, array, object with wrong schema)

        # If depth >= MAX_DEPTH, produce null or missing or wrong types only to avoid deep recursion
        if depth >= MAX_DEPTH:
            choices = ["null", "123", '"string"', "true", "false", "[]", "{}"]
            weights = [30, 5, 5, 5, 5, 5, 5]
            weighted_choices = []
            for c, w in zip(choices, weights):
                weighted_choices.extend([c]*w)
            chosen = draw(st.sampled_from(weighted_choices))
            return f'"{field_name}":{chosen}'

        # Otherwise produce nested record or null or wrong types
        nested_record = draw(generated_json(depth=depth+1))
        wrong_types = ["null", "123", '"string"', "true", "false", "[]", "{}"]
        choices = [nested_record, "null"] + wrong_types
        weights = [50, 30] + [5]*len(wrong_types)

        weighted_choices = []
        for c, w in zip(choices, weights):
            weighted_choices.extend([c]*w)
        chosen = draw(st.sampled_from(weighted_choices))
        return f'"{field_name}":{chosen}'

    # Decide which fields to omit (missing) - bias towards mostly present fields,
    # but sometimes omit one field to trigger divergence on missing required fields
    # We omit at most one field per document to keep "almost well-formed"
    fields = ["id", "amount", "name", "status", "tags", "child"]
    omit_field = draw(st.one_of(st.none(), st.sampled_from(fields)))

    # Compose fields
    parts = []

    # id: integer, non-nullable
    if omit_field != "id":
        parts.append(gen_int_field("id", nullable=False))

    # amount: string, non-nullable
    if omit_field != "amount":
        parts.append(gen_string_field("amount", nullable=False))

    # name: string or null, nullable
    if omit_field != "name":
        parts.append(gen_string_field("name", nullable=True))

    # status: enum, non-nullable
    if omit_field != "status":
        parts.append(gen_enum_field("status", nullable=False))

    # tags: array of strings, non-nullable
    if omit_field != "tags":
        parts.append(gen_tags_field("tags", nullable=False))

    # child: Record or null, nullable
    if omit_field != "child":
        parts.append(gen_child_field("child", depth))

    # Possibly add duplicate keys for one field (Gson accepts duplicates silently,
    # Moshi rejects duplicates, others reject duplicates)
    # We do this rarely to trigger divergence on duplicates
    if draw(st.booleans()):
        # Pick a field to duplicate from those present
        present_fields = [p for p in parts]
        if present_fields:
            dup_field = draw(st.sampled_from(present_fields))
            parts.append(dup_field)

    # Possibly add extra unknown keys (Gson and Moshi accept, kotlinx and Jackson reject)
    # Add zero or one unknown key rarely
    if draw(st.booleans()):
        # unknown key with simple string value
        unknown_key = draw(st.text(min_size=1, max_size=10).filter(lambda s: s not in fields))
        unknown_key_escaped = json_string_escape(unknown_key)
        unknown_value = draw(st.one_of(
            st.text(min_size=0, max_size=10).map(lambda s: f'"{json_string_escape(s)}"'),
            st.integers(min_value=0, max_value=1000).map(str),
            st.just("null"),
            st.just("true"),
            st.just("false"),
            st.just("[]"),
            st.just("{}"),
        ))
        parts.append(f'"{unknown_key_escaped}":{unknown_value}')

    # Shuffle fields to vary order
    parts = draw(st.permutations(parts))

    json_text = "{" + ",".join(parts) + "}"
    return json_text.encode("utf-8")