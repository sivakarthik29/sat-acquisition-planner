import copy
import json

from app.commands import load_dictionary
from app.dictdiff import diff_dictionaries, main

OLD = load_dictionary()


def changed(mutator):
    new = copy.deepcopy(OLD)
    mutator(new)
    return diff_dictionaries(OLD, new)


def test_identical_dictionaries_have_no_changes():
    """REQ-CMD-03: comparing a dictionary with itself reports nothing."""
    assert diff_dictionaries(OLD, copy.deepcopy(OLD)) == []


def test_breaking_changes_are_flagged():
    """REQ-CMD-03: removed commands, new required parameters, narrower ranges and type changes are breaking."""
    cases = [
        lambda d: d["commands"].pop("PAYLOAD_ON"),
        lambda d: d["commands"]["PAYLOAD_ON"]["params"].update(level={"type": "int", "min": 0, "max": 3}),
        lambda d: d["commands"]["PAYLOAD_IMAGE"]["params"]["duration_s"].update(max=60.0),
        lambda d: d["commands"]["PAYLOAD_IMAGE"]["params"]["bandset"].update(type="float"),
        lambda d: d["commands"]["PAYLOAD_IMAGE"].update(opcode=999),
        lambda d: d["commands"]["PAYLOAD_IMAGE"]["params"].pop("bandset"),
    ]
    for case in cases:
        assert any(c.severity == "breaking" for c in changed(case))


def test_widened_range_needs_review_and_new_command_is_info():
    """REQ-CMD-03: a wider range is safe for old commands but needs a human; a new command is informational."""
    wider = changed(lambda d: d["commands"]["PAYLOAD_IMAGE"]["params"]["duration_s"].update(max=300.0))
    assert [c.severity for c in wider] == ["review"]
    added = changed(lambda d: d["commands"].update(PAYLOAD_CALIBRATE={"opcode": 220, "params": {}}))
    assert [(c.severity, c.command) for c in added] == [("info", "PAYLOAD_CALIBRATE")]


def test_cli_exit_code_reflects_breaking_changes(tmp_path):
    """REQ-CMD-03: the command-line tool exits 1 when anything is breaking, so CI can block the change."""
    new = copy.deepcopy(OLD)
    new["commands"].pop("PAYLOAD_OFF")
    a, b, c = tmp_path / "old.json", tmp_path / "new.json", tmp_path / "same.json"
    a.write_text(json.dumps(OLD)); b.write_text(json.dumps(new)); c.write_text(json.dumps(OLD))
    assert main(["x", str(a), str(b)]) == 1
    assert main(["x", str(a), str(c)]) == 0
