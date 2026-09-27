"""Validate and execute the narrow contract returned by a strategy proposer."""

import ast
from collections.abc import Iterable
from dataclasses import dataclass
import builtins

from hypothesis import strategies as st


class ProposalError(ValueError):
    """Raised when generated strategy source does not meet the project contract."""


def load_strategy(source: str):
    """Load a generated ``generated_json`` strategy after lightweight validation."""
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as error:
        raise ProposalError(f"proposal has invalid Python: {error}") from error

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = {alias.name for alias in node.names}
            if isinstance(node, ast.ImportFrom) and node.module == "hypothesis":
                names.discard("strategies")
            if names or (isinstance(node, ast.ImportFrom) and node.module != "hypothesis"):
                raise ProposalError("proposal imports are restricted to hypothesis.strategies")
        if isinstance(node, (ast.Call,)) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "open", "compile", "__import__"}:
                raise ProposalError(f"proposal uses forbidden call: {node.func.id}")

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "hypothesis" and fromlist == ("strategies",):
            return builtins.__import__(name, globals, locals, fromlist, level)
        raise ProposalError("proposal imports are restricted to hypothesis.strategies")

    # Blocklist, not whitelist: the whitelist-of-evidenced-safe-names approach
    # (bytes/str/repr/range/format/isinstance/chr/len, added one real NameError
    # at a time) turned into unbounded whack-a-mole against ordinary Python
    # (all, int, ... kept surfacing). Every pure builtin (str, int, len, all,
    # sorted, ...) is harmless on its own, so instead deny the specific named
    # entry points that grant code execution, I/O, or process control, and
    # allow everything else. NOTE for the threat model: this is a filter
    # against *accidental* misuse by non-adversarial LLM output, not a real
    # security sandbox -- Python's object model (e.g. walking
    # `().__class__.__base__.__subclasses__()`) can reach dangerous
    # functionality without ever naming a blocked builtin, and no amount of
    # blocklisting/whitelisting names alone closes that off; a real boundary
    # would need process isolation (subprocess/container), not name filtering.
    _BLOCKED_BUILTINS = frozenset(
        {
            "eval", "exec", "compile", "__import__", "open", "input",
            "breakpoint", "exit", "quit", "help",
            "globals", "locals", "vars", "getattr", "setattr", "delattr",
        }
    )
    safe_builtins = {
        name: value for name, value in vars(builtins).items() if name not in _BLOCKED_BUILTINS
    }
    safe_builtins["__import__"] = safe_import
    namespace = {"st": st, "__builtins__": safe_builtins}
    exec(compile(tree, "<generated-strategy>", "exec"), namespace, namespace)
    strategy = namespace.get("generated_json")
    if strategy is None or not callable(strategy):
        raise ProposalError("proposal must define callable generated_json")
    try:
        example = strategy().example()
    except Exception as error:
        raise ProposalError(f"generated_json is not a Hypothesis strategy: {error}") from error
    if not isinstance(example, bytes):
        raise ProposalError("generated_json must emit bytes")
    return strategy


@dataclass(frozen=True)
class GenerationError:
    """Marks one failed Hypothesis draw so the campaign can log and skip past it
    instead of aborting the whole run (e.g. a stray unpaired UTF-16 surrogate
    that only some draws hit, not a systemic proposal defect)."""

    error: str


def proposal_inputs(source: str, examples: int) -> Iterable[bytes | GenerationError]:
    """Create a bounded stream of examples from validated proposal source."""
    strategy = load_strategy(source)
    for _ in range(examples):
        try:
            value = strategy().example()
        except Exception as error:
            yield GenerationError(f"{type(error).__name__}: {error}")
            continue
        if not isinstance(value, bytes):
            yield GenerationError("generated_json emitted a non-bytes value")
            continue
        yield value