#!/usr/bin/env python3
"""The claims gate fails when any number in a guide changes.

For each number in each published AGENTS.md, outside the markers, this test
writes a copy of the guide with that one number changed. It then runs the
claims gate on the copy. A copy that passes names a number that no check
or quote reads, and this test fails.

Numbers inside python fences are inputs to a recipe, so they are skipped.
A changed input changes the output, and the recipe check reads the output.

Run tools/build.py first, then: python3 tests/test_agent_claims_mutation.py
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_agent_claims as gate  # noqa: E402

NUMBER = re.compile(r"\d+")


def protected(text: str) -> list[tuple[int, int]]:
    """Spans that are not claims: markers, link targets, and python fences."""
    spans = [m.span() for m in gate.MARKER.finditer(text)]
    spans += [m.span() for m in re.finditer(r"\]\([^)]*\)", text)]
    spans += [m.span() for m in gate.FENCE.finditer(text) if m.group(1) == "python"]
    return spans


def mutants(text: str):
    """Each number, with its last digit changed, one at a time."""
    spans = protected(text)
    for match in NUMBER.finditer(text):
        start, end = match.span()
        if any(a <= start < b for a, b in spans):
            continue
        digits = match.group(0)
        changed = digits[:-1] + str((int(digits[-1]) + 1) % 10)
        line = text.count("\n", 0, start) + 1
        yield line, digits, text[:start] + changed + text[end:]


def fails(path: Path, text: str) -> bool:
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "AGENTS.md"
        copy.write_text(text)
        period = gate.guide_period(path)
        return bool(gate.check_guide(copy, set(), period) or gate.run_recipes(copy))


def main() -> int:
    if not all((gate.STAGING / gate.collection_id(p)).is_dir()
               for p in gate.RETURN_PERIODS):
        print("FAIL: staging/ is empty. Run python3 tools/build.py first.")
        return 1
    survivors, total = [], 0
    for guide in gate.guides():
        rel = guide.relative_to(gate.ROOT)
        for line, digits, text in mutants(guide.read_text()):
            total += 1
            if not fails(guide, text):
                survivors.append(f"{rel}:{line}: changing {digits} passes the gate")
    for survivor in survivors:
        print(f"FAIL: {survivor}")
    if survivors:
        return 1
    print(f"PASS: the gate fails on all {total} changed numbers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
