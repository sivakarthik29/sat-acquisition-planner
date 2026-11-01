from dataclasses import replace

import pytest

from app.commands import Command, compile_plan, load_dictionary, validate
from app.config import LIMITS
from app.scheduler import Request, build_candidates, solve_cpsat

from .conftest import DAY, NOW

CITIES = [("Bengaluru", 12.97, 77.59), ("Delhi", 28.61, 77.21), ("Mumbai", 19.07, 72.88), ("Chennai", 13.08, 80.27),
          ("Kolkata", 22.57, 88.36), ("Hyderabad", 17.38, 78.48), ("Jaipur", 26.91, 75.79), ("Pune", 18.52, 73.86)]
DICT = load_dictionary()


@pytest.fixture(scope="module")
def plan(real_sats):
    reqs = [Request(f"r{i}", n, la, lo, 300, 1 + i % 5, NOW, NOW + 14 * DAY) for i, (n, la, lo) in enumerate(CITIES)]
    cands, _ = build_candidates(reqs, real_sats)
    sol = solve_cpsat(cands)
    assert sol.selected, "the fixture plan should capture something"
    return sol, compile_plan(sol.selected)


def clone(cmds):
    return [Command(c.t, c.sat, c.name, dict(c.params)) for c in cmds]


def rules(report):
    return {v.rule for v in report.violations}


def one_sat_stream(cmds):
    sat = next(c.sat for c in cmds if c.name == "PAYLOAD_IMAGE")
    return clone([c for c in cmds if c.sat == sat])


def test_compiled_plan_passes_validation(plan, real_sats):
    """REQ-CMD-01: the plan the compiler produces passes the independent validator with no errors."""
    sol, cmds = plan
    report = validate(cmds, DICT, real_sats)
    assert report.passed and not [v for v in report.violations if v.severity == "error"]
    assert sum(c.name == "PAYLOAD_IMAGE" for c in cmds) == len(sol.selected)


def test_every_capture_has_the_full_command_block(plan):
    """REQ-CMD-01: each capture is point -> payload on -> image -> payload off, in that time order."""
    _, cmds = plan
    for img in (c for c in cmds if c.name == "PAYLOAD_IMAGE"):
        same = [c for c in cmds if c.sat == img.sat]
        on = max(c.t for c in same if c.name == "PAYLOAD_ON" and c.t <= img.t)
        off = min(c.t for c in same if c.name == "PAYLOAD_OFF" and c.t >= img.t)
        point = max(c.t for c in same if c.name == "ADCS_POINT_TARGET" and c.t <= img.t)
        assert on <= img.t - LIMITS.payload_warmup_s + 1e-6 and point < img.t < off


@pytest.mark.parametrize("mutate,expected", [
    (lambda i: i.params.update(duration_s=500.0), "V-PARAM-RANGE"),
    (lambda i: i.params.pop("bandset"), "V-PARAM-MISSING"),
    (lambda i: i.params.update(bandset=1.5), "V-PARAM-TYPE"),
    (lambda i: i.params.update(gain=3), "V-PARAM-EXTRA"),
    (lambda i: setattr(i, "name", "SELF_DESTRUCT"), "V-DICT-UNKNOWN"),
])
def test_validator_rejects_bad_parameters_and_unknown_commands(plan, real_sats, mutate, expected):
    """REQ-CMD-02: parameter and dictionary errors are caught with the right rule id."""
    cmds = one_sat_stream(plan[1])
    mutate(next(c for c in cmds if c.name == "PAYLOAD_IMAGE"))
    report = validate(cmds, DICT, real_sats)
    assert not report.passed and expected in rules(report)


def test_validator_rejects_wrong_time_order(plan, real_sats):
    """REQ-CMD-02: commands given out of time order are caught."""
    cmds = list(reversed(one_sat_stream(plan[1])))
    assert "V-TIME-ORDER" in rules(validate(cmds, DICT, real_sats))


def test_validator_rejects_missing_or_short_payload_warmup(plan, real_sats):
    """REQ-CMD-02: imaging without enough payload warm-up is caught, whether the power-on is missing or late."""
    cmds = one_sat_stream(plan[1])
    img = next(c for c in cmds if c.name == "PAYLOAD_IMAGE")
    late = clone(cmds)
    next(c for c in late if c.name == "PAYLOAD_ON" and c.t <= img.t).t = img.t - 10
    missing = [c for c in clone(cmds) if c.name != "PAYLOAD_ON"]
    assert "V-SEQ-PAYLOAD" in rules(validate(late, DICT, real_sats))
    assert "V-SEQ-PAYLOAD" in rules(validate(missing, DICT, real_sats))


def test_validator_rejects_imaging_with_no_pointing(plan, real_sats):
    """REQ-CMD-02: imaging with no target pointing command is caught."""
    cmds = [c for c in one_sat_stream(plan[1]) if c.name != "ADCS_POINT_TARGET"]
    assert "V-SEQ-POINT" in rules(validate(cmds, DICT, real_sats))


def test_validator_rejects_a_slew_that_cannot_finish(plan, real_sats):
    """REQ-CMD-02: pointing issued too close to imaging start is caught."""
    cmds = one_sat_stream(plan[1])
    img = next(c for c in cmds if c.name == "PAYLOAD_IMAGE")
    next(c for c in cmds if c.name == "ADCS_POINT_TARGET" and c.t <= img.t).t = img.t - LIMITS.imaging_margin_s - 1.0
    assert "V-TIME-SLEW" in rules(validate(cmds, DICT, real_sats))


def test_validator_rejects_targets_the_satellite_cannot_see(plan, real_sats):
    """REQ-CMD-02: pointing at a place that is not under the satellite at that time is caught by the geometry check."""
    cmds = one_sat_stream(plan[1])
    point = next(c for c in cmds if c.name == "ADCS_POINT_TARGET")
    point.params.update(lat_deg=-33.0, lon_deg=151.0)      # Sydney
    assert rules(validate(cmds, DICT, real_sats)) & {"V-GEOM-HORIZON", "V-GEOM-OFFNADIR"}


def test_validator_rejects_imaging_in_the_dark(plan, real_sats):
    """REQ-CMD-02: the same plan fails if the minimum sun elevation is raised above what the passes have."""
    strict = replace(LIMITS, min_sun_elev_deg=89.9)
    assert "V-GEOM-SUN" in rules(validate(plan[1], DICT, real_sats, strict))


def test_payload_left_on_is_only_a_warning(plan, real_sats):
    """REQ-CMD-02: a payload left on at the end of the sequence is reported as a warning, not an error."""
    cmds = one_sat_stream(plan[1])
    last_off = max(i for i, c in enumerate(cmds) if c.name == "PAYLOAD_OFF")
    del cmds[last_off]
    report = validate(cmds, DICT, real_sats)
    assert report.passed and any(v.rule == "V-SEQ-PAYLOAD-OFF" and v.severity == "warning" for v in report.violations)
