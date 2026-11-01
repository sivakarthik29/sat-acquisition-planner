from dataclasses import replace

from app.cloud import clear_capture_probability
from app.config import LIMITS
from app.feasibility import AOIRequest, assess

from .conftest import DAY, NOW, ConstantCloud


def ids(res):
    return {c.id: c for c in res.checks}


def test_area_above_limit_is_infeasible(real_sats):
    """REQ-FEA-01: an area above the published limit fails with the AOI-AREA reason."""
    res = assess(AOIRequest(12.97, 77.59, 6000, NOW, NOW + 5 * DAY), real_sats, ConstantCloud(0))
    assert not res.feasible
    assert not ids(res)["AOI-AREA"].passed and "5,000" in ids(res)["AOI-AREA"].detail


def test_small_area_is_accepted_but_billed(real_sats):
    """REQ-FEA-01: an area below the minimum billable size is accepted, with a note."""
    res = assess(AOIRequest(12.97, 77.59, 50, NOW, NOW + 5 * DAY), real_sats, ConstantCloud(0))
    assert ids(res)["AOI-AREA"].passed and "billed" in ids(res)["AOI-AREA"].detail


def test_short_window_is_infeasible(real_sats):
    """REQ-FEA-02: a window shorter than the minimum fails with WINDOW-MIN."""
    res = assess(AOIRequest(12.97, 77.59, 500, NOW, NOW + 0.5 * DAY), real_sats, ConstantCloud(0))
    assert not res.feasible and not ids(res)["WINDOW-MIN"].passed


def test_long_window_is_rejected(real_sats):
    """REQ-FEA-02: windows beyond the planner range fail with WINDOW-MAX."""
    res = assess(AOIRequest(12.97, 77.59, 500, NOW, NOW + 40 * DAY), real_sats, ConstantCloud(0))
    assert not ids(res)["WINDOW-MAX"].passed and not res.feasible


def test_feasible_request_explains_every_check(real_sats):
    """REQ-FEA-03: a feasible request lists passes and a reason for each rule it applied."""
    res = assess(AOIRequest(12.97, 77.59, 500, NOW, NOW + 14 * DAY), real_sats, ConstantCloud(0))
    assert res.feasible and res.opportunities
    assert {"AOI-AREA", "WINDOW-MIN", "WINDOW-MAX", "GEOM-PASS", "SUN-ELEV", "ORBIT-AGE"} <= set(ids(res))
    assert all(c.detail and c.source in ("published", "assumed", "computed") for c in res.checks)
    assert res.opportunities == sorted(res.opportunities, key=lambda o: o.time)


def test_no_daylight_pass_is_infeasible(real_sats):
    """REQ-FEA-04: if every pass is in the dark the request fails with SUN-ELEV."""
    dark = replace(LIMITS, min_sun_elev_deg=89.9)
    res = assess(AOIRequest(12.97, 77.59, 500, NOW, NOW + 14 * DAY), real_sats, ConstantCloud(0), dark)
    assert res.opportunities and not ids(res)["SUN-ELEV"].passed and not res.feasible


def test_stale_orbit_data_is_a_warning_not_a_failure(real_sats):
    """REQ-FEA-03: old orbit data raises a non-blocking warning."""
    res = assess(AOIRequest(12.97, 77.59, 500, NOW, NOW + 25 * DAY), real_sats, ConstantCloud(0))
    age = ids(res)["ORBIT-AGE"]
    assert not age.passed and not age.blocking and res.feasible


def test_clear_history_gives_probability_one_and_cloudy_gives_zero():
    """REQ-FEA-05: the analog-year probability is 1 for always-clear history and 0 for always-cloudy history."""
    times = [NOW + i * DAY for i in range(1, 4)]
    p_clear, _ = clear_capture_probability(ConstantCloud(5), 12.97, 77.59, times)
    p_cloudy, _ = clear_capture_probability(ConstantCloud(90), 12.97, 77.59, times)
    assert p_clear == 1.0 and p_cloudy == 0.0


def test_missing_history_gives_none_not_a_made_up_number():
    """REQ-FEA-05: with no usable cloud history the probability is None."""
    class Broken:
        def hourly_cloud(self, *a):
            raise OSError("offline")

    p, detail = clear_capture_probability(Broken(), 12.97, 77.59, [NOW + DAY])
    assert p is None and "unavailable" in detail["note"]
