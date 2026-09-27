"""The knowledge slot (docs/design.md §4): the only thing that differs between arms.

A section is a one-sentence header naming where the knowledge came from, then
the knowledge body. The 1,500-character cap applies to the body. The human
section is paper 2's `_KNOWLEDGE_PARITY_SECTION`, verbatim, header included, so
the Dart `human` arm replicates paper 2's knowledge-parity prompt byte for byte.
"""

KNOWLEDGE_CAP = 1500

# `sysprobe`: extension arm, systematic probing (design §10); same header as `probe`,
# so only the knowledge body differs between the two.
ARMS = ("none", "human", "code", "probe", "sysprobe")

_HUMAN_HEADER = """What is already known about these four implementations, from a
hand-run characterization of them before any fuzzing (use it however you
see fit):"""

# Paper 2's four observations (its design doc §17), unchanged.
HUMAN_DART_BODY = """1. All four receive the output of one shared `jsonDecode` call. Invalid
   JSON syntax, or a top-level value that is not an object, is rejected
   identically before any of them runs, so it can never cause disagreement.
2. When the `tags` field is missing entirely, built_value accepts the
   document and silently uses an empty list, while manual, json_serializable
   and freezed reject it. Missing `id`, `amount` or `status` is rejected by
   all four.
3. A wrong JSON type for a field, or null for a non-nullable field, was
   rejected by all four in every case tried (manual, json_serializable and
   freezed throw a private `_TypeError`; built_value throws its own public
   `DeserializationError`). An unrecognized `status` string is rejected by
   all four. An extra unknown top-level key, or a missing nullable `name`
   or `child`, is accepted by all four.
4. `id` decoding differs in the generated code: manual (`json['id'] as int`)
   and built_value require a true Dart int, while json_serializable and
   freezed decode it as `(json['id'] as num).toInt()`, which also accepts a
   Dart double. `jsonDecode` turns an integer literal outside the 64-bit
   range into a double, and `toInt()` on an out-of-range double saturates to
   the int64 minimum/maximum instead of throwing."""

_HEADERS = {
    "human": _HUMAN_HEADER,
    "code": """What is already known about these four implementations, from reading
their deserialization code before any fuzzing (use it however you see
fit):""",
    "probe": """What is already known about these four implementations, from running
probe documents against them before any fuzzing (use it however you see
fit):""",
}
_HEADERS["sysprobe"] = _HEADERS["probe"]


class KnowledgeError(ValueError):
    pass


def knowledge_section(arm: str, body: str | None) -> str | None:
    """The full text for the prompt's knowledge slot, or None for the `none` arm."""
    if arm not in ARMS:
        raise KnowledgeError(f"unknown arm {arm!r}")
    if arm == "none":
        if body:
            raise KnowledgeError("the none arm takes no knowledge body")
        return None
    body = (body or "").strip()
    if not body:
        raise KnowledgeError(f"the {arm} arm needs a knowledge body")
    if len(body) > KNOWLEDGE_CAP:
        raise KnowledgeError(f"knowledge body is {len(body)} chars; the cap is {KNOWLEDGE_CAP}")
    return f"{_HEADERS[arm]}\n{body}"
