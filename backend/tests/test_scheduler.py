import random

from app.config import LIMITS
from app.scheduler import (Candidate, Request, build_candidates, conflict_pairs, conflicts, solve_cpsat,
                           solve_greedy)

from .conftest import DAY, NOW


def cand(rid, sat, t, weight, roll=0.0, dur=1.0):
    half = dur / 2 + LIMITS.imaging_margin_s
    return Candidate(rid, rid, f"S{sat}", sat, t, 5.0, roll, 60.0, "descending", dur, t - half, t + half, weight, 0, 0, 100)


def test_conflict_rule():
    """REQ-SCH-01: close captures on one satellite conflict; other satellites and distant captures do not."""
    a = cand("a", 1, 1000, 100)
    assert conflicts(a, cand("b", 1, 1040, 100))          # 40 s apart: not enough to re-warm the payload
    assert not conflicts(a, cand("c", 1, 1200, 100))      # 200 s apart: fine
    assert not conflicts(a, cand("d", 2, 1040, 100))      # different satellite
    # a 40 deg roll change needs 20 s settle + 40/0.5 = 100 s, longer than the 64 s gap -> conflict
    assert conflicts(cand("f", 1, 1000, 100, roll=20.0), cand("g", 1, 1075, 100, roll=-20.0))
    # same pointing needs only the 70 s payload re-warm, and a 79 s gap is enough
    assert not conflicts(cand("f", 1, 1000, 100, roll=20.0), cand("h", 1, 1090, 100, roll=19.0))


def test_optimizer_beats_greedy_on_a_crafted_case():
    """REQ-SCH-02: greedy takes the single best capture and loses two smaller ones that were worth more together."""
    a = cand("A", 1, 100, 300)
    b = cand("B", 1, 40, 200)
    c = cand("C", 1, 160, 200)
    assert conflicts(a, b) and conflicts(a, c) and not conflicts(b, c)
    greedy, optimal = solve_greedy([a, b, c]), solve_cpsat([a, b, c])
    assert greedy.total_value == 300 and optimal.total_value == 400 and optimal.status == "OPTIMAL"


def test_optimizer_never_worse_than_greedy_and_plans_are_valid():
    """REQ-SCH-02 / REQ-SCH-03: on random instances CP-SAT >= greedy, with no clashes and one capture per request."""
    rng = random.Random(7)
    for _ in range(25):
        cands = [cand(f"r{rng.randrange(8)}", rng.randrange(1, 3), rng.uniform(0, 1500), rng.choice([100, 200, 300, 400]),
                      roll=rng.uniform(-20, 20)) for _ in range(30)]
        cands.sort(key=lambda c: (c.norad_id, c.time))
        g, o = solve_greedy(cands), solve_cpsat(cands)
        assert o.total_value >= g.total_value
        for sol in (g, o):
            assert len({c.request_id for c in sol.selected}) == len(sol.selected)
            for i, x in enumerate(sol.selected):
                for y in sol.selected[i + 1:]:
                    assert not conflicts(x, y)


def test_conflict_pairs_match_brute_force():
    """REQ-SCH-01: the fast pair search finds exactly the conflicts a brute-force check finds."""
    rng = random.Random(3)
    cands = [cand(f"r{i}", rng.randrange(1, 3), rng.uniform(0, 2000), 100, roll=rng.uniform(-20, 20)) for i in range(40)]
    cands.sort(key=lambda c: (c.norad_id, c.time))
    brute = {(i, j) for i in range(len(cands)) for j in range(i + 1, len(cands)) if conflicts(cands[i], cands[j])}
    assert set(conflict_pairs(cands)) == brute


def test_real_orbit_candidates_are_daylight_and_in_window(real_sats):
    """REQ-SCH-03: every candidate built from real orbit data is inside its window, daylit, and within the limit."""
    reqs = [Request("blr", "Bengaluru", 12.97, 77.59, 500, 3, NOW, NOW + 14 * DAY),
            Request("del", "Delhi", 28.61, 77.21, 800, 5, NOW, NOW + 14 * DAY)]
    cands, reasons = build_candidates(reqs, real_sats)
    assert cands
    for c in cands:
        assert NOW <= c.time <= NOW + 14 * DAY
        assert c.sun_elev_deg >= LIMITS.min_sun_elev_deg and c.off_nadir_deg <= LIMITS.max_off_nadir_deg


def test_oversized_request_gets_a_reason(real_sats):
    """REQ-SCH-03: a request that can never be scheduled is explained, not silently dropped."""
    reqs = [Request("big", "Huge", 12.97, 77.59, 9000, 5, NOW, NOW + 5 * DAY)]
    cands, reasons = build_candidates(reqs, real_sats)
    assert not cands and "limit" in reasons["big"]
