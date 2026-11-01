"""Orbit engine: SGP4 propagation, pointing geometry, pass (access) search, equator crossings.

Pointing frame (per satellite, per instant):
  z = nadir (towards Earth centre), x = along-track (velocity), y = z cross x = right of the ground track.
  off-nadir = angle between the line of sight to the target and nadir.
  roll      = cross-track part of that angle; positive = target to the right of the ground track.
"""
from dataclasses import dataclass

import numpy as np
from sgp4.api import WGS72, Satrec

from . import geo
from .config import LIMITS, Limits

RE_WGS72 = 6378.135  # km, the radius SGP4 uses internally


class Satellite:
    def __init__(self, name: str, norad_id: int, line1: str, line2: str):
        self.name = name
        self.norad_id = int(norad_id)
        self.line1, self.line2 = line1, line2
        self.satrec = Satrec.twoline2rv(line1, line2, WGS72)
        self.epoch_unix = (self.satrec.jdsatepoch + self.satrec.jdsatepochF - 2440587.5) * 86400.0

    # ---- orbit facts from the elements -------------------------------------------------
    @property
    def inclination_deg(self) -> float:
        return float(np.degrees(self.satrec.inclo))

    @property
    def period_min(self) -> float:
        return 2.0 * np.pi / self.satrec.no_kozai

    @property
    def altitude_km(self) -> float:
        """Mean altitude from the SGP4 semi-major axis (accurate to a few km)."""
        return float(self.satrec.a * RE_WGS72 - RE_WGS72)

    # ---- propagation -------------------------------------------------------------------
    def propagate(self, t):
        """Return (r_teme, v_teme, jd) in km, km/s for unix times t. Failed epochs become NaN."""
        t = np.atleast_1d(np.asarray(t, dtype=float))
        days = t / 86400.0
        di = np.floor(days)
        jd_whole, jd_frac = di + 2440587.0, days - di + 0.5
        err, r, v = self.satrec.sgp4_array(jd_whole, jd_frac)
        bad = err != 0
        r[bad] = np.nan
        v[bad] = np.nan
        return r, v, geo.jd_from_unix(t)


@dataclass
class Track:
    sat: Satellite
    t: np.ndarray
    jd: np.ndarray
    r: np.ndarray
    v: np.ndarray


_TRACK_CACHE: dict = {}


def build_track(sat: Satellite, t0: float, t1: float, step_s: float) -> Track:
    """Satellite state sampled on a regular grid aligned to `step_s` (so repeated calls can reuse it)."""
    start = np.floor(t0 / step_s) * step_s
    key = (sat.norad_id, sat.line1, start, round(t1 / step_s), step_s)
    if key not in _TRACK_CACHE:
        if len(_TRACK_CACHE) > 24:
            _TRACK_CACHE.pop(next(iter(_TRACK_CACHE)))
        t = np.arange(start, t1 + step_s, step_s)
        r, v, jd = sat.propagate(t)
        _TRACK_CACHE[key] = Track(sat, t, jd, r, v)
    return _TRACK_CACHE[key]


# ---- pointing geometry ----------------------------------------------------------------
def pointing_arrays(r, v, target):
    """Pointing angles from satellites at r (n,3) with velocity v (n,3) to target positions (n,3), all in TEME.
    Returns off_nadir_deg, roll_deg, pitch_deg, range_km, elevation_deg.
    elevation_deg is the satellite's elevation above the target's local horizon; it must be > 0 for the target to be
    visible. (A small off-nadir angle alone is not enough: the line of sight could pass through the Earth.)"""
    nadir = -r / np.linalg.norm(r, axis=1, keepdims=True)
    los = target - r
    rng = np.linalg.norm(los, axis=1)
    lz = np.sum(los * nadir, axis=1)
    off = np.degrees(np.arccos(np.clip(lz / rng, -1.0, 1.0)))
    v_perp = v - np.sum(v * nadir, axis=1, keepdims=True) * nadir
    x = v_perp / np.linalg.norm(v_perp, axis=1, keepdims=True)
    y = np.cross(nadir, x)
    roll = np.degrees(np.arctan2(np.sum(los * y, axis=1), lz))
    pitch = np.degrees(np.arctan2(np.sum(los * x, axis=1), lz))
    up = target / np.linalg.norm(target, axis=1, keepdims=True)
    elev = np.degrees(np.arcsin(np.clip(np.sum(-los * up, axis=1) / rng, -1.0, 1.0)))
    return off, roll, pitch, rng, elev


def _target_teme(lat: float, lon: float, jd):
    ecef = geo.geodetic_to_ecef(lat, lon)
    return geo.ecef_to_teme(np.broadcast_to(ecef, (len(jd), 3)), jd)


def pointing_at(sat: Satellite, lat: float, lon: float, t: float) -> dict:
    """Pointing geometry and sun elevation for one satellite, one target, one instant."""
    r, v, jd = sat.propagate([t])
    off, roll, pitch, rng, elev = pointing_arrays(r, v, _target_teme(lat, lon, jd))
    return {
        "off_nadir_deg": float(off[0]), "roll_deg": float(roll[0]), "pitch_deg": float(pitch[0]),
        "range_km": float(rng[0]), "elevation_deg": float(elev[0]),
        "sun_elev_deg": float(geo.sun_elevation_deg(lat, lon, t)),
    }


# ---- access (pass) search --------------------------------------------------------------
@dataclass
class Opportunity:
    sat_name: str
    norad_id: int
    time: float            # unix seconds, closest approach
    off_nadir_deg: float
    roll_deg: float
    sun_elev_deg: float
    direction: str         # "ascending" or "descending"
    sun_ok: bool


def find_opportunities(track: Track, lat: float, lon: float, limits: Limits = LIMITS) -> list[Opportunity]:
    """All passes where the target is within the off-nadir limit. One entry per pass, at closest approach."""
    sat = track.sat
    tgt = _target_teme(lat, lon, track.jd)
    off, _, _, _, elev = pointing_arrays(track.r, track.v, tgt)
    # NaN compares False, so failed epochs drop out; elev > 0 removes the far side of the Earth
    inside = np.flatnonzero((off <= limits.max_off_nadir_deg) & (elev > 0))
    if inside.size == 0:
        return []
    runs = np.split(inside, np.flatnonzero(np.diff(inside) > 1) + 1)
    step = float(track.t[1] - track.t[0])
    ecef = geo.geodetic_to_ecef(lat, lon)
    out = []
    for run in runs:
        tc = track.t[run[np.argmin(off[run])]]
        tf = tc + np.arange(-step, step + 1e-9, 0.25)              # refine closest approach to 0.25 s
        r, v, jd = sat.propagate(tf)
        o, ro, _, _, el = pointing_arrays(r, v, geo.ecef_to_teme(np.broadcast_to(ecef, (len(jd), 3)), jd))
        o = np.where(el > 0, o, np.nan)
        if np.all(np.isnan(o)):
            continue
        i = int(np.nanargmin(o))
        t_best = float(tf[i])
        if t_best < track.t[0] or t_best > track.t[-1]:
            continue
        sun = float(geo.sun_elevation_deg(lat, lon, t_best))
        out.append(Opportunity(
            sat_name=sat.name, norad_id=sat.norad_id, time=t_best,
            off_nadir_deg=float(o[i]), roll_deg=float(ro[i]), sun_elev_deg=sun,
            direction="ascending" if v[i, 2] > 0 else "descending",
            sun_ok=sun >= limits.min_sun_elev_deg,
        ))
    return out


# ---- orbit sanity checks against published specs -----------------------------------------
def equator_crossings(sat: Satellite, t0: float, hours: float = 24.0, step_s: float = 10.0) -> list[dict]:
    """Equator crossings with the local mean solar time at the crossing longitude."""
    t = np.arange(t0, t0 + hours * 3600.0, step_s)
    r, v, jd = sat.propagate(t)
    z = r[:, 2]
    idx = np.flatnonzero((z[:-1] * z[1:] < 0))
    out = []
    for i in idx:
        tc = float(t[i] + step_s * z[i] / (z[i] - z[i + 1]))     # linear interpolation of the zero crossing
        rc, vc, jdc = sat.propagate([tc])
        lon = float(geo.ecef_to_geodetic(geo.teme_to_ecef(rc, jdc))[1][0])
        out.append({
            "time": tc, "lon_deg": lon,
            "local_hours": float(geo.local_mean_solar_hours(lon, tc)),
            "direction": "ascending" if vc[0, 2] > 0 else "descending",
        })
    return out


def orbit_summary(sat: Satellite, now: float) -> dict:
    crossings = equator_crossings(sat, now, hours=24)
    desc = [c["local_hours"] for c in crossings if c["direction"] == "descending"]
    return {
        "name": sat.name, "norad_id": sat.norad_id,
        "altitude_km": round(sat.altitude_km, 1), "inclination_deg": round(sat.inclination_deg, 2),
        "period_min": round(sat.period_min, 2), "epoch_unix": sat.epoch_unix,
        "tle_age_days": round((now - sat.epoch_unix) / 86400.0, 1),
        "descending_crossing_local_h": round(float(np.median(desc)), 2) if desc else None,
    }
