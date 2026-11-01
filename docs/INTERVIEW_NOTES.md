# Interview notes

Read the code for each module once before an interview. If you cannot explain a line, change it or cut it from the resume.

## 60-second pitch

"I wanted to understand how a constellation operator turns a customer's imaging request into safe commands. So I built a small version from public data. You click a place; it propagates the public orbit data for the Firefly satellites, finds every pass within the 20 degree limit, and explains whether the request is feasible, rule by rule, with the chance of a clear capture from past cloud history. For many requests it picks the passes with an optimiser and compares that with a greedy baseline. Then it writes a command timeline and an independent validator re-checks it before it would be sent. The limits from Pixxel's docs are marked published; the ones I had to assume, like slew rate, are marked assumed."

## 3-minute demo

1. Open the orbit pill: real element sets, altitude and crossing time against the published 589 km and 10-11 h.
2. Check one target (Bengaluru, 500 km2, 14 days): read the reasons and the source chips.
3. Make it fail: area 6000, or a 12-hour window.
4. Plan tab, load the example set, set the window to 3 days: compare greedy and optimiser.
5. Open the command timeline; point out "Validated" and that the command set is notional.
6. Show `pytest -q`, `scripts/check_traceability.py`, and the CI workflow.

## Module by module

**geo.py** Earth geometry. Time is unix seconds. GMST by the IAU-82 polynomial; TEME to Earth-fixed is one rotation about z. Sun position uses the NOAA low-precision algorithm (about 0.01 deg). Ignores polar motion and nutation (hundreds of metres), irrelevant against a 20 deg limit.

**orbit.py**
- SGP4 gives position and velocity in TEME from a TLE. Accuracy is kilometres at the epoch and worsens with age, which is why the planner warns after 7 days.
- Pointing frame: z = nadir, x = velocity, y = z cross x (right of the track). Off-nadir = angle between line of sight and nadir. Roll = cross-track part, positive to the right.
- **Visibility check (bug I found):** a target on the far side of the Earth can have a tiny off-nadir angle because the line of sight passes through the planet. Without an elevation check the pass count was about 20 times too high. There is a test for it (REQ-ORB-05).
- Pass search: sample every 10 s, find runs inside the limit, refine closest approach to 0.25 s. Grazing passes shorter than 10 s at the very edge of the limit can be missed.
- Sanity: about 0.3 passes per satellite per day at +/-20 deg.

**feasibility.py** Each rule returns pass or fail, a reason, and a source (published, assumed, computed). Non-blocking warnings (old orbit data) do not fail the verdict. Probability: "analog years", the fraction of the last 5 years in which the same dates and hours had at least one clear pass. It keeps weather persistence within a year; its weakness is a small sample and reanalysis cloud, not satellite-seen cloud. If the history is missing the answer is blank.

**scheduler.py** A candidate is one pass for one request. Constraints: at most one capture per request; two captures on one satellite conflict if the gap is shorter than max(settle + roll change / slew rate, payload warm-up + 10 s). Greedy sorts by value and skips clashes. CP-SAT has one yes/no variable per candidate, an at-most-one per request, a pairwise "not both" per conflict, and maximises value. Both use the same `conflicts()` function. Optimiser is never worse than greedy (tested on random instances) and strictly better on a crafted case (greedy takes one 300 and loses two 200s). On the example set the two often tie; that is honest, and the UI says so.

**commands.py** The compiler emits for each capture: point (finishing the slew just before the padded start), payload on, image, payload off; it returns to nadir only when the next capture is more than 10 minutes away. The validator is independent: it checks the dictionary and parameters, ordering, payload warm-up, pointing, slew time, then recomputes off-nadir, horizon and sun from the orbit data. Each rule has a failure test.

**dictdiff.py** Compares two dictionary versions. Breaking: removed command, new required parameter, narrower range, type or opcode change. Review: wider range. Info: new command. Exit code 1 on breaking, so CI can block a change. This is a toy version of reviewing an operational database change request.

## Numbers to remember

| Fact | Value |
|---|---|
| Off-nadir limit (published) | +/-20 deg |
| Swath (published) | 38 km |
| Max area / min billable (published) | 5,000 / 100 km2 |
| Cloud threshold (published) | 20% |
| Published orbit | 589 km, 97.65 deg, descending node 10-11 h |
| Real element sets (snapshot 19 Jul 2026) | FIREFLY 2: 589 km, 10.7 h. FFLY-2: 586 km, 10.5 h. FIREFLY 3: about 555 km, 10.96 h |
| Assumed (mine) | sun >= 20 deg, 0.5 deg/s slew, 20 s settle, 60 s warm-up |

The lower altitude of FIREFLY 3 (and a crossing time near the top of the window) is an observation from one snapshot. Do not claim a cause; say it could be orbit lowering or phasing, and that you would check fresh data.

## What is true on your resume today

| Resume claim | Status |
|---|---|
| Acquisition planning workflow, each stage tested | Built |
| Orbit engine, SGP4, passes, off-nadir, sun elevation | Built |
| Unit-tested against Skyfield | Built (REQ-ORB-04) |
| Verified against published specs (crossing time, altitude) | Built (REQ-ORB-01/02/03, header table) |
| Explainable feasibility, clear-capture probability | Built; the cloud call was tested with stubs, run it live once |
| CP-SAT scheduler vs greedy baseline | Built |
| Telecommand validator, versioned dictionary with change diffs | Built |
| Telemetry anomaly analysis on ESA benchmark, report, runbook | **Not built.** Hold this bullet until it is |
| FastAPI service, CI/CD, structured logging, health checks | Built; Dockerfile and workflow are written but run them once on your machine and GitHub |
| Requirements-to-test traceability, CONOPS-style document | Built (`docs/requirements.md`, `docs/DESIGN.md`) |
| Skills: Shapely | **Not used.** Remove it |
| Skills: pandas, scikit-learn, telemetry trending and anomaly detection | Not used yet (phase 2). Remove until then |
| Skills: Skyfield/SGP4, OR-Tools, Pydantic, Leaflet, pytest, Docker, GitHub Actions | Used |

## Questions to expect

- **Why SGP4 and what is its error?** Standard model for TLEs; kilometre-level at the epoch, growing roughly a few km per day.
- **How do you know your geometry is right?** Unit tests, an independent Skyfield computation, a physical pass-rate check, and a designed-orbit local-time check.
- **Why does a small off-nadir angle not guarantee visibility?** The target could be behind the Earth; you need a horizon check.
- **Why an optimiser if greedy often ties?** It cannot lose, it proves optimality, and it wins when requests clash. Show the crafted case.
- **What is assumed?** Sun elevation, slew rate, settle, warm-up. They are tagged in the UI and `config.py`.
- **What would you add with real Pixxel data?** Real agility, power and downlink limits, ground-station contacts, polygon AOIs, forecast clouds.
- **What did you do when something looked wrong?** The pass count was far too high; I traced it to the far-side-of-Earth case and added a horizon check and a test.
- **What would you do if validation fails at 3 AM?** Do not send; read the rule id and message, check the orbit data age, escalate if the cause is not clear.
