"""Scheduling: pick which passes to use for competing requests.

Model
  - A candidate is one pass of one satellite over one request's target (daylight, within the off-nadir limit).
  - Each request is captured at most once.
  - Two candidates on the same satellite conflict if the gap between them is shorter than the time needed to slew
    and re-warm the payload (rules.required_gap_s). Different satellites never conflict.
  - Goal: maximise total value, where value = 100 x priority + a 0..10 quality tie-break (smaller off-nadir is better).

Two solvers use the exact same conflict rule: a greedy baseline and an optimal CP-SAT model.
"""
import time
from dataclasses import dataclass

from ortools.sat.python import cp_model

from .config import LIMITS, Limits
from .orbit import Satellite, build_track, find_opportunities
from .rules import imaging_duration_s, required_gap_s

CONFLICT_SEARCH_S = 900.0  # candidates further apart than this can never conflict (max required gap is ~100 s)


@dataclass
class Request:
    id: str
    name: str
    lat: float
    lon: float
    area_km2: float
    priority: int          # 1 (low) .. 5 (high)
    start: float
    end: float


@dataclass
class Candidate:
    request_id: str
    request_name: str
    sat_name: str
    norad_id: int
    time: float
    off_nadir_deg: float
    roll_deg: float
    sun_elev_deg: float
    direction: str
    duration_s: float
    pad_start: float
    pad_end: float
    weight: int
    lat: float
    lon: float
    area_km2: float


@dataclass
class Solution:
    method: str
    selected: list[Candidate]
    total_value: int
    runtime_ms: float
    status: str


def build_candidates(requests: list[Request], satellites: list[Satellite], limits: Limits = LIMITS):
    """Return (candidates, reasons) where reasons maps request id -> why it has no candidate."""
    if not requests:
        return [], {}
    horizon_start = min(r.start for r in requests)
    horizon_end = max(r.end for r in requests)
    tracks = [build_track(s, horizon_start, horizon_end, limits.time_step_s) for s in satellites]
    cands: list[Candidate] = []
    reasons: dict[str, str] = {}
    for req in requests:
        if req.area_km2 > limits.max_area_km2:
            reasons[req.id] = f"Area {req.area_km2:,.0f} km2 is above the {limits.max_area_km2:,.0f} km2 limit."
            continue
        dur = imaging_duration_s(req.area_km2, limits)
        seen, lit = 0, 0
        for tr in tracks:
            for o in find_opportunities(tr, req.lat, req.lon, limits):
                if not (req.start <= o.time <= req.end):
                    continue
                seen += 1
                if not o.sun_ok:
                    continue
                lit += 1
                quality = round(10 * (1 - o.off_nadir_deg / limits.max_off_nadir_deg))
                half = dur / 2 + limits.imaging_margin_s
                cands.append(Candidate(
                    req.id, req.name, o.sat_name, o.norad_id, o.time, o.off_nadir_deg, o.roll_deg, o.sun_elev_deg,
                    o.direction, dur, o.time - half, o.time + half, 100 * req.priority + quality,
                    req.lat, req.lon, req.area_km2))
        if seen == 0:
            reasons[req.id] = "No pass within the off-nadir limit in this window."
        elif lit == 0:
            reasons[req.id] = "Every pass happens with the sun too low."
    cands.sort(key=lambda c: (c.norad_id, c.time))
    return cands, reasons


def conflicts(a: Candidate, b: Candidate, limits: Limits = LIMITS) -> bool:
    if a.norad_id != b.norad_id:
        return False
    first, second = (a, b) if a.time <= b.time else (b, a)
    return second.pad_start - first.pad_end < required_gap_s(first.roll_deg, second.roll_deg, limits)


def conflict_pairs(cands: list[Candidate], limits: Limits = LIMITS) -> list[tuple[int, int]]:
    """Index pairs that cannot both be chosen. `cands` must be sorted by (satellite, time)."""
    pairs = []
    for i, a in enumerate(cands):
        for j in range(i + 1, len(cands)):
            b = cands[j]
            if b.norad_id != a.norad_id or b.time - a.time > CONFLICT_SEARCH_S:
                break
            if conflicts(a, b, limits):
                pairs.append((i, j))
    return pairs


def solve_greedy(cands: list[Candidate], limits: Limits = LIMITS) -> Solution:
    """Baseline: take the highest-value candidate first, skip anything that clashes with what is already chosen."""
    t0 = time.perf_counter()
    chosen: list[Candidate] = []
    done: set[str] = set()
    for c in sorted(cands, key=lambda c: (-c.weight, c.time)):
        if c.request_id in done or any(conflicts(c, k, limits) for k in chosen):
            continue
        chosen.append(c)
        done.add(c.request_id)
    chosen.sort(key=lambda c: c.time)
    return Solution("greedy", chosen, sum(c.weight for c in chosen), (time.perf_counter() - t0) * 1000, "HEURISTIC")


def solve_cpsat(cands: list[Candidate], limits: Limits = LIMITS, time_limit_s: float = 10.0) -> Solution:
    """Optimal selection with OR-Tools CP-SAT: one yes/no variable per candidate."""
    t0 = time.perf_counter()
    if not cands:
        return Solution("cp-sat", [], 0, 0.0, "OPTIMAL")
    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"x{i}") for i in range(len(cands))]
    by_request: dict[str, list] = {}
    for i, c in enumerate(cands):
        by_request.setdefault(c.request_id, []).append(x[i])
    for vars_ in by_request.values():
        model.AddAtMostOne(vars_)
    for i, j in conflict_pairs(cands, limits):
        model.AddBoolOr([x[i].Not(), x[j].Not()])
    model.Maximize(sum(c.weight * x[i] for i, c in enumerate(cands)))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 0
    status = solver.Solve(model)
    name = solver.StatusName(status)
    chosen = [c for i, c in enumerate(cands) if solver.Value(x[i])] if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else []
    chosen.sort(key=lambda c: c.time)
    return Solution("cp-sat", chosen, sum(c.weight for c in chosen), (time.perf_counter() - t0) * 1000, name)


def explain_unscheduled(requests: list[Request], reasons: dict[str, str], chosen: list[Candidate]) -> list[dict]:
    done = {c.request_id for c in chosen}
    out = []
    for r in requests:
        if r.id not in done:
            out.append({"request_id": r.id, "name": r.name,
                        "reason": reasons.get(r.id, "Every usable pass clashes with a higher-value capture.")})
    return out
