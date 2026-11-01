"""HTTP API. Thin layer: validate input, call the engine, shape the output. No planning logic lives here."""
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .cloud import OpenMeteoClient
from .commands import compile_plan, load_dictionary, validate
from .config import LIMITS, PUBLISHED_ORBIT, describe
from .feasibility import AOIRequest, assess
from .logging_setup import setup_logging
from .orbit import Satellite, orbit_summary
from .scheduler import Request as PlanRequest
from .scheduler import build_candidates, explain_unscheduled, solve_cpsat, solve_greedy
from .tle import load_satellites

log = logging.getLogger("planner.api")
STATIC_DIR = Path(__file__).parent / "static"


# ---- request models ---------------------------------------------------------------------
class FeasibilityIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    area_km2: float = Field(gt=0)
    start: datetime
    end: datetime


class PlanRequestIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=60)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    area_km2: float = Field(gt=0)
    priority: int = Field(ge=1, le=5)


class PlanIn(BaseModel):
    requests: list[PlanRequestIn] = Field(min_length=1, max_length=30)
    start: datetime
    end: datetime


def _ts(dt: datetime) -> float:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _window_error(start: float, end: float):
    if end <= start:
        raise HTTPException(422, "The end of the window must be after the start.")


# ---- app factory ------------------------------------------------------------------------
def create_app(satellites: list[Satellite] | None = None, cloud_client=None, data_dir: Path | None = None) -> FastAPI:
    setup_logging()
    data_dir = data_dir or Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
    started = time.time()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if satellites is not None:
            app.state.orbits = {"satellites": satellites, "source": "provided", "note": "Orbit data supplied at startup.", "fetched_at": None}
        else:
            res = load_satellites(data_dir, os.environ.get("SAT_SOURCE", "live"))
            app.state.orbits = {"satellites": res.satellites, "source": res.source, "note": res.note, "fetched_at": res.fetched_at}
            log.info("orbit data loaded", extra={"ctx": {"source": res.source, "count": len(res.satellites), "note": res.note}})
        app.state.cloud = cloud_client or OpenMeteoClient(data_dir / "cloud")
        app.state.dictionary = load_dictionary()
        yield

    app = FastAPI(title="Satellite Acquisition Planner", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        rid, t0 = uuid.uuid4().hex[:8], time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        if request.url.path.startswith("/api"):
            log.info("request", extra={"ctx": {"request_id": rid, "method": request.method, "path": request.url.path,
                                              "status": response.status_code, "ms": round((time.perf_counter() - t0) * 1000, 1)}})
        return response

    # ---- endpoints ---------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        orbits = app.state.orbits
        return {"status": "ok", "version": __version__, "uptime_s": round(time.time() - started),
                "satellites": len(orbits["satellites"]), "orbit_source": orbits["source"]}

    @app.get("/api/limits")
    def limits():
        return {"limits": describe(), "dictionary": {"version": app.state.dictionary["version"],
                                                     "notional": app.state.dictionary.get("notional", False)}}

    @app.get("/api/satellites")
    def satellites_info():
        orbits, now = app.state.orbits, time.time()
        return {"source": orbits["source"], "note": orbits["note"],
                "fetched_at": _iso(orbits["fetched_at"]) if orbits["fetched_at"] else None,
                "published": PUBLISHED_ORBIT,
                "satellites": [orbit_summary(s, now) for s in orbits["satellites"]]}

    @app.post("/api/feasibility")
    def feasibility(body: FeasibilityIn):
        req = AOIRequest(body.lat, body.lon, body.area_km2, _ts(body.start), _ts(body.end))
        _window_error(req.start, req.end)
        res = assess(req, app.state.orbits["satellites"], app.state.cloud)
        log.info("feasibility", extra={"ctx": {"feasible": res.feasible, "passes": len(res.opportunities),
                                               "probability": res.probability}})
        return {
            "feasible": res.feasible,
            "checks": [c.__dict__ for c in res.checks],
            "opportunities": [{"sat_name": o.sat_name, "norad_id": o.norad_id, "time": _iso(o.time),
                               "off_nadir_deg": round(o.off_nadir_deg, 1), "roll_deg": round(o.roll_deg, 1),
                               "sun_elev_deg": round(o.sun_elev_deg, 1), "direction": o.direction, "sun_ok": o.sun_ok}
                              for o in res.opportunities],
            "probability": res.probability,
            "probability_detail": res.probability_detail,
            "orbit_source": app.state.orbits["source"],
        }

    @app.post("/api/plan")
    def plan(body: PlanIn):
        start, end = _ts(body.start), _ts(body.end)
        _window_error(start, end)
        if (end - start) / 86400.0 > LIMITS.max_window_days:
            raise HTTPException(422, f"The planner supports windows up to {LIMITS.max_window_days:.0f} days.")
        if len({r.id for r in body.requests}) != len(body.requests):
            raise HTTPException(422, "Request ids must be unique.")
        sats = app.state.orbits["satellites"]
        reqs = [PlanRequest(r.id, r.name, r.lat, r.lon, r.area_km2, r.priority, start, end) for r in body.requests]
        cands, reasons = build_candidates(reqs, sats)
        greedy, optimal = solve_greedy(cands), solve_cpsat(cands)
        commands = compile_plan(optimal.selected)
        report = validate(commands, app.state.dictionary, sats)
        sat_names = {s.norad_id: s.name for s in sats}
        log.info("plan", extra={"ctx": {"requests": len(reqs), "candidates": len(cands), "greedy": greedy.total_value,
                                        "optimal": optimal.total_value, "valid": report.passed}})

        def summarize(sol):
            return {"method": sol.method, "total_value": sol.total_value, "captured": len(sol.selected),
                    "runtime_ms": round(sol.runtime_ms, 1), "status": sol.status}

        return {
            "window": {"start": _iso(start), "end": _iso(end)},
            "candidates": len(cands),
            "solutions": {"greedy": summarize(greedy), "optimized": summarize(optimal)},
            "captures": [{"request_id": c.request_id, "name": c.request_name, "sat_name": c.sat_name,
                          "norad_id": c.norad_id, "time": _iso(c.time), "off_nadir_deg": round(c.off_nadir_deg, 1),
                          "roll_deg": round(c.roll_deg, 1), "sun_elev_deg": round(c.sun_elev_deg, 1),
                          "duration_s": round(c.duration_s, 1), "value": c.weight} for c in optimal.selected],
            "unscheduled": explain_unscheduled(reqs, reasons, optimal.selected),
            "commands": [{"time": _iso(k.t), "sat": k.sat, "sat_name": sat_names.get(k.sat, str(k.sat)),
                          "name": k.name, "params": k.params} for k in commands],
            "validation": {"passed": report.passed, "checked": report.checked,
                           "violations": [{**v.__dict__, "time": _iso(v.t) if v.t else None} for v in report.violations]},
            "dictionary": {"version": app.state.dictionary["version"], "notional": app.state.dictionary.get("notional", False)},
            "orbit_source": app.state.orbits["source"],
        }

    if STATIC_DIR.exists():   # the built React app, served by the same process in Docker
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
