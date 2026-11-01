"""Compare two versions of the command dictionary, like reviewing a database change request.

Severity
  breaking  something that used to be valid now fails (removed command, new required parameter, narrower range, ...)
  review    something that now accepts more than before; safe for old commands but needs a human decision
  info      a new command that nothing depends on yet

Usage:  python -m app.dictdiff old.json new.json     (exit code 1 if anything is breaking)
"""
import json
import sys
from dataclasses import dataclass


@dataclass
class Change:
    severity: str
    command: str
    message: str


def diff_dictionaries(old: dict, new: dict) -> list[Change]:
    out: list[Change] = []
    oc, nc = old["commands"], new["commands"]
    for name in sorted(set(oc) | set(nc)):
        if name not in nc:
            out.append(Change("breaking", name, "command removed"))
            continue
        if name not in oc:
            out.append(Change("info", name, "command added"))
            continue
        a, b = oc[name], nc[name]
        if a["opcode"] != b["opcode"]:
            out.append(Change("breaking", name, f"opcode changed {a['opcode']} -> {b['opcode']}"))
        for p in sorted(set(a["params"]) | set(b["params"])):
            if p not in b["params"]:
                out.append(Change("breaking", name, f"parameter '{p}' removed"))
            elif p not in a["params"]:
                out.append(Change("breaking", name, f"new required parameter '{p}'"))
            else:
                pa, pb = a["params"][p], b["params"][p]
                if pa["type"] != pb["type"]:
                    out.append(Change("breaking", name, f"parameter '{p}' type {pa['type']} -> {pb['type']}"))
                if pb["min"] > pa["min"] or pb["max"] < pa["max"]:
                    out.append(Change("breaking", name, f"parameter '{p}' range narrowed "
                                      f"[{pa['min']}, {pa['max']}] -> [{pb['min']}, {pb['max']}]"))
                if pb["min"] < pa["min"] or pb["max"] > pa["max"]:
                    out.append(Change("review", name, f"parameter '{p}' range widened "
                                      f"[{pa['min']}, {pa['max']}] -> [{pb['min']}, {pb['max']}]"))
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    old, new = (json.load(open(p)) for p in argv[1:])
    changes = diff_dictionaries(old, new)
    print(f"dictionary {old['version']} -> {new['version']}: {len(changes)} change(s)")
    for c in changes:
        print(f"  [{c.severity:8}] {c.command}: {c.message}")
    return 1 if any(c.severity == "breaking" for c in changes) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
