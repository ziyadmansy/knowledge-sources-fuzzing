"""Batch subprocess client for the NDJSON harnesses (paper 2's Dart harness and
this repo's Kotlin harness speak the same protocol).

Ported from paper 2's `dart_runner.py`. One long-lived process handles a whole
campaign; a batch-level timeout or crash is checked around the whole invocation.
The only change is `env`, needed to point the Kotlin launcher script at a JDK.
"""

import base64
from dataclasses import dataclass
import json
import subprocess
from typing import Mapping, Sequence


@dataclass(frozen=True)
class HarnessBatchResult:
    lines: list[dict]
    timed_out: bool
    returncode: int | None


def run_batch(
    executable: str,
    inputs: Sequence[bytes],
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
) -> HarnessBatchResult:
    """Send every input as one NDJSON request line and collect the harness's
    NDJSON response lines, in order. A killed/timed-out process still yields
    whatever complete lines it flushed before dying (Python's
    `subprocess.run` populates `TimeoutExpired.stdout` with captured output
    up to that point), so a batch-level fault does not discard earlier,
    genuinely-produced results -- the same principle the original project's
    `runner.py` applied per input, just at batch granularity here.
    """
    request = (
        "\n".join(
            json.dumps({"input_b64": base64.b64encode(data).decode("ascii")})
            for data in inputs
        )
        + "\n"
    )
    try:
        completed = subprocess.run(
            [executable],
            input=request.encode("utf-8"),
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=dict(env) if env is not None else None,
        )
        stdout, returncode, timed_out = completed.stdout, completed.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, returncode, timed_out = (error.stdout or b""), None, True

    lines: list[dict] = []
    # Split on the literal LF byte only, matching exactly what the harnesses
    # emit as their line terminator (Dart `stdout.writeln`, Kotlin `newLine()`
    # on macOS/Linux). `str.splitlines()` (or
    # splitting after decoding with Python's text-mode line semantics) is
    # wrong here: it also breaks on U+2028/U+2029/U+000C/U+0085/etc, which are
    # legal, unescaped characters inside a JSON string (only `"`, `\`, and
    # ASCII control characters below 0x20 must be escaped per the JSON spec)
    # -- a generator producing arbitrary Unicode text can and does emit these,
    # and splitting on them desynchronizes response lines from request lines,
    # which looks like a harness crash but is a request/response bookkeeping
    # bug in this client, not a fault in the harness itself.
    for raw_line in stdout.split(b"\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            lines.append(json.loads(raw_line.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # a truncated final line from a killed process -- not attributable
            # to any specific input, so it is dropped rather than guessed at
            continue
    return HarnessBatchResult(lines=lines, timed_out=timed_out, returncode=returncode)
