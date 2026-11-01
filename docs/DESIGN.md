# Design and Concept of Operations

## 1. Purpose

Turn "can you image this place?" into an answer an operator can trust: a verdict with reasons, a schedule that resolves competing requests, and a command list that has been checked before it is sent. The system is a learning model of a constellation operator's planning loop, built only from public information.

## 2. Operational concept

```
request (area, window)
   -> passes found from orbit data
   -> feasibility verdict with reasons
   -> schedule chosen across competing requests
   -> command timeline compiled
   -> validator re-checks it independently
   -> (notional) uplink
```

Users: a planner who submits requests and reads the verdict; an operator who reviews the schedule and the validated commands.

## 3. System context

| Element | Role | Source |
|---|---|---|
| Orbital elements (TLE) | Where each satellite is | CelesTrak, cached 2 h |
| Cloud history | Chance of a clear capture | Open-Meteo archive |
| Command dictionary | What commands exist and their limits | `app/data/command_dictionary_v1.json` (notional) |
| Operating rules | Slew, warm-up, off-nadir, sun | `config.py`, `rules.py` |

## 4. Key design decisions

1. **One rulebook.** Scheduler and validator import the same rules (`rules.py`). A plan the scheduler accepts is one the validator accepts, and a change to a rule changes both.
2. **Independent validation.** The validator recomputes pointing geometry from orbit data rather than trusting the schedule. Errors in the scheduler cannot hide in the validator.
3. **Reasons, not booleans.** Every feasibility rule returns pass/fail, a sentence, and its source (published, assumed, computed). Assumptions are visible in the UI.
4. **Two solvers, one conflict rule.** Greedy is the baseline; CP-SAT finds the optimum. Comparing them shows when optimisation matters (many clashes) and when it does not.
5. **Honest data.** If live orbit data is unavailable the app falls back to cache, then to synthetic orbits, and always labels which one it is using. If cloud history is missing the probability is blank, never invented.
6. **Hand-written geometry, cross-checked.** Pointing and sun geometry are written directly so they can be explained; an independent Skyfield computation checks them in the tests.

## 5. Models and assumptions

| Topic | Model | Limit |
|---|---|---|
| Orbit | SGP4 from TLE | Error grows with element age; warn after 7 days |
| Frames | TEME to Earth-fixed by sidereal angle only | Ignores polar motion and nutation (hundreds of metres) |
| Pointing | Off-nadir = angle between line of sight and geocentric nadir; roll = cross-track part | Geocentric nadir differs from geodetic by about 0.2 deg |
| Visibility | Target must be above the satellite's horizon | A small off-nadir angle alone is not enough (line of sight could pass through the Earth) |
| AOI | One strip: length = area / swath | Shape is ignored |
| Imaging time | strip length / ground speed (6.9 km/s) | Constant speed |
| Conflicts | Gap between padded captures must exceed max(slew + settle, payload warm-up + 10 s) | Agility values are assumed |
| Value | 100 x priority + 0..10 quality tie-break | Priority dominates by design |
| Cloud | Analog years: fraction of past years with at least one clear pass at the same dates and hours | Few years; reanalysis cloud is not satellite-seen cloud |

## 6. Verification approach

- Requirements in `docs/requirements.md`; each test carries its requirement ID; CI fails on gaps.
- Orbit checks against published values: altitude and descending-node local time of real element sets.
- Method checks: an orbit designed for 10.5 h local time measures 10.5 h.
- Independent check: off-nadir and elevation against Skyfield.
- Failure injection: the validator is tested with one deliberately broken command list per rule.

## 7. Failure modes handled

| Failure | Behaviour |
|---|---|
| CelesTrak unreachable | Use cache; if none, labelled demo orbits |
| Cloud service unreachable | Probability shown as unavailable |
| Element set too old | Non-blocking warning on the feasibility result |
| Unschedulable request | Listed with a reason (area, no pass, no daylight, clashes) |
| Bad API input | 422 with a readable message |

## 8. Operations

- Structured JSON logs (one line per request with id, status and duration).
- `GET /api/health` reports status, version, satellite count and orbit source; the container has a health check.
- CI: tests, traceability, UI build, container build and start; optional deploy hook on main.

## 9. Out of scope (for now)

Ground-station contacts, data volume and power budgets, polygon AOIs, multi-strip coverage, forecast clouds, real command databases, and telemetry anomaly analysis (planned: ESA benchmark).
