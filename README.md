# Satellite Acquisition Planning & Ops-Readiness Toolkit

Given a place on the map and a time window, can a Firefly-class satellite image it, and when? And if many requests compete, which passes should be used? This project answers both from public orbit data, then checks the resulting command list against operating rules before it would be "uplinked".

It is an independent learning project. It uses public data only. It is **not** Pixxel software, and the command set is **notional**.

## What it does

1. **Predicts passes.** Propagates public orbital elements (TLEs) with SGP4 and finds every pass within the off-nadir limit, with the sun-elevation at the target.
2. **Checks feasibility, with reasons.** Each rule says pass or fail, why, and where the rule comes from (published, assumed, or computed). It also estimates the chance of a clear capture from past cloud history.
3. **Schedules competing requests.** A greedy baseline and an optimal OR-Tools CP-SAT model use the same conflict rule, so they can be compared fairly.
4. **Compiles and validates commands.** The plan becomes a timed command list. An independent validator re-checks it against the dictionary and recomputes the geometry itself.
5. **Reviews dictionary changes.** `python -m app.dictdiff old.json new.json` flags breaking, review-needed and informational changes, like a change request review.

## Quick start

```bash
# Backend (Python 3.11+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q                                  # 50+ tests, no network needed
uvicorn app.main:app --reload              # http://localhost:8000/api/health

# Frontend (Node 18+), in a second terminal
cd frontend
npm install
npm run dev                                # http://localhost:5173 (proxies /api to :8000)
```

Single process (UI served by the API): `cd frontend && npm run build`, then run uvicorn as above and open `http://localhost:8000`.

Docker: `docker build -t sat-planner . && docker run -p 8000:8000 sat-planner`.

Orbit data: by default the app fetches the six Firefly element sets from CelesTrak and caches them for two hours, falling back to an older cache and then to clearly labelled synthetic demo orbits. Force demo mode with `SAT_SOURCE=demo`. The header pill always shows which source is in use.

## Architecture

```
React (Vite + Leaflet) ──HTTP──▶ FastAPI (app/main.py)         validate input, shape output only
                                    │
        tle.py ── orbit data ──▶ orbit.py ── passes ──▶ feasibility.py ──▶ cloud.py (Open-Meteo history)
                                    │                        │
                                    └────────▶ scheduler.py (greedy + CP-SAT) ──▶ commands.py (compile + validate)
                                                  rules.py + config.py: one shared rulebook
```

| Module | Job |
|---|---|
| `config.py` | Every number, tagged published / derived / assumed |
| `geo.py` | Hand-written Earth geometry and sun position |
| `orbit.py` | SGP4 propagation, pointing geometry, pass search, crossing-time check |
| `feasibility.py` | Explainable rules, clear-capture probability |
| `scheduler.py` | Candidates, shared conflict rule, greedy and CP-SAT |
| `commands.py` | Command compiler and rule-based validator |
| `dictdiff.py` | Command dictionary change review |

## What is real and what is assumed

- **Published (Pixxel docs):** ±20° off-nadir, 38 km swath, 5,000 km² max AOI, 100 km² minimum billable, 20% cloud threshold, one-day minimum window.
- **Assumed (mine):** minimum sun elevation, slew rate, settle time, payload warm-up. These are tagged `assumed` in the UI and in `/api/limits`.
- **Verified against published orbit facts:** altitude and descending-node local time of the real element sets (tests `REQ-ORB-01/02`, and the orbit table in the header).

## Tests and traceability

`docs/requirements.md` lists requirement IDs. Every test names the ID it verifies, and `python scripts/check_traceability.py` fails if a requirement has no test. CI runs both, builds the UI, builds the Docker image, and (if a deploy hook secret is set) triggers a deploy.

## Known limits

- SGP4 accuracy falls as element sets age; the planner warns beyond about 7 days.
- The AOI is modelled as one strip (area / swath), not a polygon.
- Cloud probability uses a handful of past years of reanalysis data, not satellite-seen cloud or forecasts.
- Slew model uses cross-track roll only; there is no power, data-volume, or ground-station model yet.
- Frame handling ignores polar motion and nutation (hundreds of metres on the ground).

## Data sources and terms

- Orbital elements: CelesTrak (please keep the two-hour cache; do not poll faster).
- Cloud history: Open-Meteo historical weather API (free for non-commercial use; check its terms before any commercial use).
- Map tiles: OpenStreetMap contributors and CARTO.

## Roadmap

Telemetry anomaly analysis on ESA's public benchmark (fixed-limit alarms vs a simple ML detector, with an investigation report and runbook). Ground-station passes and a data-volume constraint.
