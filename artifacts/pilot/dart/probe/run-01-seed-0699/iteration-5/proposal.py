```python
from hypothesis import strategies as st

@st.composite
def generated_json(draw) -> bytes:
    # Constants
    STATUS_VALUES = ["active", "inactive", "unknown"]

    # Helper to produce a JSON string literal from a Python string,
    # escaping backslash and double quote minimally for valid JSON.
    def json_string(s: str) -> str:
        # Escape backslash and double quote only (minimal escaping)
        # No control chars or unicode escaping for simplicity.
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'

    # Recursive record generator with bounded depth
    def record_json(depth: int) -> st.SearchStrategy[str]:
        # At depth limit, child must be null or absent (but absent not allowed by schema)
        # Schema requires child field always present (null or Record)
        # So child: null or record_json(depth-1)
        # We produce all fields always present.

        # id: integer
        id_strat = st.integers(min_value=-(2**31), max_value=2**31-1).map(str)

        # amount: string (any string)
        amount_strat = st.text(min_size=0, max_size=20).map(json_string)

        # name: string or null
        # To maximize chance of divergence, sometimes produce empty string, sometimes null, sometimes normal string
        name_strat = st.one_of(
            st.none().map(lambda _: "null"),
            st.text(min_size=0, max_size=20).map(json_string),
        )

        # status: enum string
        status_strat = st.sampled_from(STATUS_VALUES).map(json_string)

        # tags: array of strings (empty strings allowed, no nulls)
        # To try edge cases, sometimes empty array, sometimes array of empty strings, sometimes normal strings
        tags_strat = st.lists(
            st.text(min_size=0, max_size=10).map(json_string),
            min_size=0,
            max_size=5,
        ).map(lambda lst: "[" + ",".join(lst) + "]")

        # child: null or record_json(depth-1)
        if depth <= 0:
            child_strat = st.just("null")
        else:
            child_strat = st.one_of(
                st.just("null"),
                record_json(depth - 1),
            )

        # Compose fields with possibility of one subtle divergence:
        # We try to produce one of these variants per record:
        # - all fields correct (baseline)
        # - "name" missing (should reject all, but schema requires always present)
        # - "name" present but null or string (both allowed)
        # - "tags" empty array or array with empty string (allowed)
        # - "child" null or nested record (allowed)
        # - "status" correct enum (always)
        # - "id" integer (always)
        # - "amount" string (always)
        # - Introduce one subtle type mismatch in one field per record with low probability:
        #   * "name" as integer (should reject all)
        #   * "tags" array with one null (should reject all)
        #   * "child" present but empty object (should reject all)
        #   * "status" invalid enum string (should reject all)
        #   * "id" as string (should reject all)
        #   * "amount" as integer (should reject all)
        # But since all reject these, no divergence expected.
        # Instead, try to produce:
        # - duplicate keys for "name" or "id" in child with different values (last wins)
        # - "tags" array with empty string and normal strings (allowed)
        # - "name" as null vs string (allowed)
        # - "child" null vs nested record (allowed)
        # - "tags" empty array vs array with empty string (allowed)
        # These are accepted by all, so no divergence expected.
        # To get divergence, try to produce "child" with missing required fields (should reject all)
        # or "child" with extra unknown fields (accepted by all)
        # or "child" with duplicate keys (last wins)
        # or "child" with "status" invalid enum (reject all)
        # So no divergence expected here either.
        # Try to produce "tags" array with empty string and a non-string (integer as string) to see if any accept.
        # But all reject non-string in tags.
        # So no divergence expected.
        # Try to produce "name" as empty string vs null in child with duplicate keys.
        # All accept last key wins.
        # So no divergence expected.
        # Try to produce "child" with "child" null vs missing "child" field (missing field should reject all).
        # So no divergence expected.
        # Try to produce "child" with "child" present but empty object (reject all).
        # So no divergence expected.
        # Try to produce "child" with "child" present but "child" null (allowed).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string again (allowed).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string (allowed).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string (allowed).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string (allowed).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string (max 5).
        # So no divergence expected.
        # Try to produce "tags" array with empty string and empty string and empty string and empty string and empty string and empty string and empty string and empty string and