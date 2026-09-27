"""The two differential targets (docs/design.md §5): what differs between them is
the harness, the path names, the prompt's description of the four paths, and
whether divergence can occur on inputs that fail the strict JSON gate.
"""

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_ANDROID_STUDIO_JDK = "/Applications/Android Studio.app/Contents/jbr/Contents/Home"

_SCHEMA_BLOCK = """Record schema (all six fields always present in a well-formed document):
{
  "id": <integer>,
  "amount": <string>,
  "name": <string or null>,
  "status": <one of "active", "inactive", "unknown">,
  "tags": <array of strings>,
  "child": <Record or null, one level of recursion normally>
}"""


@dataclass(frozen=True)
class Target:
    name: str
    path_order: tuple[str, str, str, str]
    # The prompt's title noun, e.g. "Dart JSON deserializers".
    title: str
    description: str
    # The prompt's sentence on what kind of documents to emit.
    syntax_note: str
    # Dart: the four paths only run after a shared jsonDecode, so divergence exists only on
    # schema_evaluated inputs. Kotlin: every library parses the text itself, so divergence is
    # counted on all inputs (docs/design.md §10) and also reported split by gate status.
    divergence_on_all_inputs: bool
    default_executable: Path
    env_overrides: dict[str, str] = field(default_factory=dict)

    def env(self) -> dict[str, str] | None:
        if not self.env_overrides:
            return None
        merged = dict(os.environ)
        for key, value in self.env_overrides.items():
            merged.setdefault(key, value)
        return merged

    def harness_sha256(self, executable: str) -> str:
        """Hash what actually runs: the Dart AOT binary, or the Kotlin launcher's jars."""
        path = Path(executable)
        if self.name == "kotlin":
            files = sorted((path.parent.parent / "lib").glob("*.jar"))
        else:
            files = [path]
        if not files or not all(f.is_file() for f in files):
            return "unknown"
        digest = hashlib.sha256()
        for f in files:
            digest.update(f.name.encode())
            digest.update(f.read_bytes())
        return digest.hexdigest()


# Paper 2's SCHEMA_DESCRIPTION and closing sentence, verbatim, so the Dart prompts
# are byte-identical to paper 2's (tests/test_prompt_parity.py checks this).
DART = Target(
    name="dart",
    path_order=("A_manual", "B_json_serializable", "C_freezed", "D_built_value"),
    title="Dart JSON deserializers",
    description=_SCHEMA_BLOCK
    + """

Four independent Dart JSON deserializers are run against every document you
produce: hand-written manual parsing, and three codegen frameworks
(json_serializable, freezed, built_value). Your goal is to produce documents
that are syntactically valid JSON objects but make these four
implementations disagree with each other -- one accepting where another
rejects, or two accepting but decoding to different values -- or that make
any of them fail with an undocumented (private, unnameable) exception type
rather than a clear, catchable one.""",
    syntax_note="""Emit syntactically valid JSON objects only (invalid JSON syntax is rejected
identically by all four paths before any of them run, so it cannot score).""",
    divergence_on_all_inputs=False,
    default_executable=REPO_ROOT.parent / "agentic-fuzzing-dart-json" / "build" / "dart_json_harness",
)

# Same structure, with only harness facts stated: which libraries run, and that each
# parses the raw text itself. No behavioural claims (those are the knowledge slot's job).
KOTLIN = Target(
    name="kotlin",
    path_order=("A_gson", "B_moshi", "C_kotlinx", "D_jackson"),
    title="Kotlin JSON deserializers",
    description=_SCHEMA_BLOCK
    + """

Four independent Kotlin JSON deserializers are run against every document you
produce, each at its default configuration and each decoding into the same
Kotlin data class: Gson, Moshi (generated adapter), kotlinx.serialization,
and Jackson with its Kotlin module. Your goal is to produce documents that
make these four implementations disagree with each other -- one accepting
where another rejects, or two accepting but decoding to different values.""",
    syntax_note="""Each document is passed to all four libraries as raw text, and each library
parses that text itself.""",
    divergence_on_all_inputs=True,
    default_executable=REPO_ROOT
    / "kotlin-harness"
    / "build"
    / "install"
    / "kotlin-json-harness"
    / "bin"
    / "kotlin-json-harness",
    env_overrides={"JAVA_HOME": _ANDROID_STUDIO_JDK},
)

TARGETS = {t.name: t for t in (DART, KOTLIN)}
