#!/usr/bin/env python3
"""Anonymize a checkout of this repo for the double-blind review mirror.

Run inside a worktree of the `review-mirror` branch after merging main:

  git worktree add ../ksf-review review-mirror && cd ../ksf-review
  git merge main && python3 .review/make_mirror.py && git add -A && git commit -m "Anonymize for review"

anonymous.4open.science mirrors the `review-mirror` branch. This script deletes
itself, so the mirror never contains the strings it replaces. It ends with a
leak scan and exits non-zero if anything identifying is left.
"""

from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path.cwd()
DELETE = ["CITATION.cff", "CLAUDE.md", "paper/main.tex", "docs/upstream", ".review"]

# Order matters: specific phrases first, generic ones last.
REPLACE = [
    ("(*Beyond Sanitizers*, AST 2027 submission, repo `agentic-fuzzing-dart-json`, ", "(anonymized for review; "),
    ("An earlier study ([Beyond Sanitizers](https://doi.org/10.5281/zenodo.22555794))", "An earlier study (anonymized for review)"),
    ("[agentic-fuzzing-dart-json](https://github.com/ziyadmansy/agentic-fuzzing-dart-json) checked out next to this\nrepository",
     "the previous study's artifact (anonymized for review) checked out next to this\nrepository as `previous-study-artifact`"),
    ("hard deadline: preprint before PhD applications on 1 December", "hard deadline: 1 December"),
    ("artifact release, Zenodo DOI, preprint; CV/SOP entry.", "artifact release, DOI, preprint."),
    ("citing mansy2026agentic/mansy2026beyond here\n% deanonymizes the submission.", "the named citations are omitted\n% from this copy."),
    ("Copyright (c) 2026 Ziyad Mohammad Mansy Ibrahim", "Copyright (c) 2026 Anonymous Author(s)"),
    ("kotlinx.serialization #3276", "kotlinx.serialization (issue number withheld for review)"),
    ("#3276", "(issue number withheld for review)"),
    ("Paper 2's", "The previous study's"),
    ("paper 2's", "the previous study's"),
    ("Paper 2", "The previous study"),
    ("paper 2", "the previous study"),
    ("Paper 3", "This study"),
    ("paper 3", "this study"),
    ("agentic-fuzzing-dart-json", "previous-study-artifact"),
    ("/Users/ziyadmansy", "/home/reviewer"),
]

LEAK = re.compile(
    r"ziyad|mansy|ibrahim|zenodo|10\.5281|orcid|agentic-fuzzing|agentic-grammar|/Users/|"
    r"AST 2027|FORGE|beyond sanitizers|paper [123]\b|\bPhD\b|#3276|issues/3276",
    re.IGNORECASE,
)


def tracked_text_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    files = []
    for name in out.decode().split("\0"):
        path = ROOT / name
        if not name or not path.is_file():
            continue
        try:
            path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue
        files.append(path)
    return files


def drop_named_bib_entries(text: str) -> str:
    return re.sub(r"@misc\{(mansy2026agentic|mansy2026beyond|kotlinxissue3276),.*?\n\}\n\n?", "", text, flags=re.S)


def main() -> None:
    for name in DELETE:
        path = ROOT / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    for path in tracked_text_files():
        text = original = path.read_text(encoding="utf-8")
        if path.name == "references.bib":
            text = drop_named_bib_entries(text)
        for old, new in REPLACE:
            text = text.replace(old, new)
        if text != original:
            path.write_text(text, encoding="utf-8")
    leaks = []
    for path in tracked_text_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if LEAK.search(line):
                leaks.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}")
    if leaks:
        print("LEAKS LEFT:\n" + "\n".join(leaks))
        sys.exit(1)
    print("clean")


if __name__ == "__main__":
    main()
