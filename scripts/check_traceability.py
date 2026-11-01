"""Check that every requirement in docs/requirements.md has at least one test, and every test names a real requirement.

Run from the repository root:  python scripts/check_traceability.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ_RE = re.compile(r"REQ-[A-Z]+-\d+")

requirements = set(re.findall(r"^\| (REQ-[A-Z]+-\d+) \|", (ROOT / "docs" / "requirements.md").read_text(), re.M))
covered: dict[str, set[str]] = {r: set() for r in requirements}
unknown: list[tuple[str, str]] = []

for path in sorted((ROOT / "backend" / "tests").glob("test_*.py")):
    for rid in set(REQ_RE.findall(path.read_text())):
        if rid in covered:
            covered[rid].add(path.name)
        else:
            unknown.append((path.name, rid))

print(f"{'requirement':<12} tests")
for rid in sorted(covered):
    print(f"{rid:<12} {', '.join(sorted(covered[rid])) or 'NONE'}")

missing = [r for r, files in covered.items() if not files]
if missing or unknown:
    print(f"\nFAIL: untested requirements: {missing}; unknown ids in tests: {unknown}")
    sys.exit(1)
print(f"\nOK: {len(requirements)} requirements, all covered.")
