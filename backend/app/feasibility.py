"""Feasibility check. Every rule reports pass/fail, a plain-language reason, and where the rule comes from."""
from dataclasses import dataclass, field

from .cloud import clear_capture_probability
from .config import LIMITS, Limits
from .orbit import Opportunity, Satellite, build_track, find_opportunities


@dataclass
class AOIRequest:
    lat: float
    lon: float
    area_km2: float
    start: float   # unix seconds
    end: float


@dataclass
class Check:
    id: str
    label: str
    passed: bool
    detail: str
    source: str            # "published" | "assumed" | "computed"
    blocking: bool = True  # a failed non-blocking check is a warning


@dataclass
class FeasibilityResult:
    feasible: bool
    checks: list[Check]
    opportunities: list[Opportunity]
    probability: float | None
    probability_detail: dict = field(default_factory=dict)


def usable_opportunities(satellites: list[Satellite], req: AOIRequest, limits: Limits = LIMITS) -> list[Opportunity]:
    """All passes in the window within the off-nadir limit, sorted by time."""
    out: list[Opportunity] = []
    for sat in satellites:
        track = build_track(sat, req.start, req.end, limits.time_step_s)
        out += [o for o in find_opportunities(track, req.lat, req.lon, limits) if req.start <= o.time <= req.end]
    return sorted(out, key=lambda o: o.time)


def assess(req: AOIRequest, satellites: list[Satellite], cloud_client, limits: Limits = LIMITS) -> FeasibilityResult:
    checks: list[Check] = []
    window_days = (req.end - req.start) / 86400.0

    checks.append(Check(
        "AOI-AREA", "Area within the tasking limit", req.area_km2 <= limits.max_area_km2,
        f"{req.area_km2:,.0f} km2 requested; the limit is {limits.max_area_km2:,.0f} km2."
        + (f" Below {limits.min_billable_area_km2:,.0f} km2 it is billed as {limits.min_billable_area_km2:,.0f} km2 but still accepted."
           if req.area_km2 < limits.min_billable_area_km2 else ""),
        "published"))
    checks.append(Check(
        "WINDOW-MIN", "Capture window long enough", window_days >= limits.min_window_days,
        f"Window is {window_days:.1f} days; the minimum is {limits.min_window_days:.0f} day.", "published"))
    checks.append(Check(
        "WINDOW-MAX", "Capture window within planner range", window_days <= limits.max_window_days,
        f"Window is {window_days:.1f} days; the planner supports up to {limits.max_window_days:.0f} days "
        f"because orbit prediction degrades with time.", "assumed"))

    blocking_failed = any(not c.passed for c in checks if c.blocking)
    opps: list[Opportunity] = []
    if not blocking_failed:
        opps = usable_opportunities(satellites, req, limits)
        checks.append(Check(
            "GEOM-PASS", "A satellite can see the target", len(opps) > 0,
            f"{len(opps)} pass(es) within +/-{limits.max_off_nadir_deg:.0f} deg off-nadir in the window."
            if opps else f"No pass within +/-{limits.max_off_nadir_deg:.0f} deg off-nadir in this window. Try a longer window.",
            "computed"))
        lit = [o for o in opps if o.sun_ok]
        if opps:
            checks.append(Check(
                "SUN-ELEV", "Target is lit during a pass", len(lit) > 0,
                f"{len(lit)} of {len(opps)} pass(es) have the sun above {limits.min_sun_elev_deg:.0f} deg."
                if lit else f"All {len(opps)} pass(es) happen with the sun below {limits.min_sun_elev_deg:.0f} deg.",
                "assumed"))
        if satellites:
            worst = max((req.end - s.epoch_unix) / 86400.0 for s in satellites)
            checks.append(Check(
                "ORBIT-AGE", "Orbit data is fresh enough", worst <= limits.tle_stale_days,
                f"Predictions reach {worst:.1f} days past the orbit data epoch; accuracy degrades beyond about "
                f"{limits.tle_stale_days:.0f} days, so late passes are less certain.", "assumed", blocking=False))

    lit = [o for o in opps if o.sun_ok]
    probability, detail = None, {}
    if lit and not any(not c.passed for c in checks if c.blocking):
        probability, detail = clear_capture_probability(cloud_client, req.lat, req.lon, [o.time for o in lit], limits)
    feasible = all(c.passed for c in checks if c.blocking) and bool(lit)
    return FeasibilityResult(feasible, checks, opps, probability, detail)
