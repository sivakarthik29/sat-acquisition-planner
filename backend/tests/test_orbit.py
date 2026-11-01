"""Geometry and orbit tests. Docstrings start with the requirement id they verify (see docs/requirements.md)."""
import numpy as np
import pytest
from skyfield.api import EarthSatellite, load, wgs84

from app import geo
from app.config import LIMITS, PUBLISHED_ORBIT
from app.orbit import build_track, equator_crossings, find_opportunities, pointing_at

from .conftest import DAY, NOW

ts = load.timescale()


def test_geodetic_roundtrip():
    """REQ-GEO-01: geodetic -> ECEF -> geodetic round-trips within one metre."""
    for lat, lon in [(0, 0), (12.97, 77.59), (-33.9, 151.2), (78.2, 15.6), (-89.0, -170.0)]:
        la, lo, h = geo.ecef_to_geodetic(geo.geodetic_to_ecef(lat, lon, 0.3))
        assert abs(la[0] - lat) < 1e-7 and abs(lo[0] - lon) < 1e-7 and abs(h[0] - 0.3) < 1e-3


def test_sun_elevation_known_values():
    """REQ-GEO-02: sun elevation matches textbook values within one degree."""
    equinox_noon = datetime_unix(2026, 3, 20, 12, 0)
    solstice_noon = datetime_unix(2026, 6, 21, 12, 0)
    assert geo.sun_elevation_deg(0, 0, equinox_noon) > 88            # sun nearly overhead at the equator
    assert abs(geo.sun_elevation_deg(60, 0, solstice_noon) - 53.4) < 1.0   # 90 - 60 + 23.44
    assert geo.sun_elevation_deg(0, 0, datetime_unix(2026, 3, 20, 0, 0)) < -80   # local midnight


def test_gmst_at_j2000():
    """REQ-GEO-02: sidereal time at J2000 is 280.4606 degrees."""
    assert abs(np.degrees(geo.gmst_rad(2451545.0)) - 280.46061837) < 1e-6


def datetime_unix(y, m, d, hh, mm):
    from datetime import datetime, timezone
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp()


# ---- real Firefly orbit data vs published specs ----------------------------------------------
def test_real_orbit_matches_published_altitude_and_inclination(real_sats):
    """REQ-ORB-01: a real Firefly element set gives altitude and inclination close to the published values."""
    ff2 = next(s for s in real_sats if s.norad_id == 62698)
    assert abs(ff2.altitude_km - PUBLISHED_ORBIT["altitude_km"]) < 5
    assert abs(ff2.inclination_deg - PUBLISHED_ORBIT["inclination_deg"]) < 0.2


def test_real_crossing_times_inside_published_window(real_sats):
    """REQ-ORB-02: descending-node local time of real element sets is inside the published 10:00-11:00 window."""
    lo, hi = PUBLISHED_ORBIT["crossing_local_time_h"]
    for sat in real_sats:
        desc = [c["local_hours"] for c in equator_crossings(sat, sat.epoch_unix + DAY) if c["direction"] == "descending"]
        assert lo <= float(np.median(desc)) <= hi, sat.name


def test_designed_orbit_gives_designed_local_time(demo_sats):
    """REQ-ORB-03: an orbit designed for a 10.5 h descending node measures 10.5 h (independent check of the method)."""
    desc = [c["local_hours"] for c in equator_crossings(demo_sats[0], NOW + 3600) if c["direction"] == "descending"]
    assert abs(float(np.median(desc)) - 10.5) < 0.15


def test_off_nadir_matches_skyfield(real_sats):
    """REQ-ORB-04: my off-nadir angle matches an independent Skyfield computation within 0.5 degrees.
    Independent formula (spherical Earth): sin(off_nadir) = (R_target / r_sat) * cos(elevation), with the satellite's
    elevation and distance both taken from Skyfield."""
    sat = next(s for s in real_sats if s.norad_id == 62698)
    t = sat.epoch_unix + 3600.0
    r, v, jd = sat.propagate([t])
    lat, lon, _ = geo.ecef_to_geodetic(geo.teme_to_ecef(r, jd))
    target_lat, target_lon = float(lat[0]), float(lon[0]) + 1.5          # about 150 km off the ground track
    mine = pointing_at(sat, target_lat, target_lon, t)

    sf = EarthSatellite(sat.line1, sat.line2, sat.name, ts)
    when = ts.from_datetime(__import__("datetime").datetime.fromtimestamp(t, tz=__import__("datetime").timezone.utc))
    elev, _, _ = (sf - wgs84.latlon(target_lat, target_lon)).at(when).altaz()
    r_sat = sf.at(when).distance().km
    r_target = np.linalg.norm(geo.geodetic_to_ecef(target_lat, target_lon))
    expected = np.degrees(np.arcsin(r_target / r_sat * np.cos(np.radians(elev.degrees))))
    assert abs(mine["off_nadir_deg"] - expected) < 0.5
    assert abs(mine["elevation_deg"] - elev.degrees) < 0.5


def test_far_side_of_earth_is_never_a_pass(real_sats):
    """REQ-ORB-05: a target behind the Earth has a tiny off-nadir angle but must not be reported as a pass."""
    sat = real_sats[0]
    t = NOW
    r, v, jd = sat.propagate([t])
    lat, lon, _ = geo.ecef_to_geodetic(geo.teme_to_ecef(r, jd))
    anti_lat, anti_lon = -float(lat[0]), float(lon[0]) + 180.0
    g = pointing_at(sat, anti_lat, anti_lon, t)
    assert g["off_nadir_deg"] < 2.0 and g["elevation_deg"] < 0       # the trap
    track = build_track(sat, t - 120, t + 120, 10.0)
    assert find_opportunities(track, anti_lat, anti_lon) == []


def test_passes_respect_limit_and_are_true_minima(real_sats):
    """REQ-ORB-06: every pass is within the off-nadir limit, visible, and its time is a local minimum."""
    sat = next(s for s in real_sats if s.norad_id == 62698)
    track = build_track(sat, NOW, NOW + 14 * DAY, LIMITS.time_step_s)
    opps = find_opportunities(track, 12.97, 77.59)
    assert opps, "expected at least one pass in 14 days"
    for o in opps:
        assert o.off_nadir_deg <= LIMITS.max_off_nadir_deg
        here = pointing_at(sat, 12.97, 77.59, o.time)
        before = pointing_at(sat, 12.97, 77.59, o.time - 1.0)
        after = pointing_at(sat, 12.97, 77.59, o.time + 1.0)
        assert here["elevation_deg"] > 0
        assert here["off_nadir_deg"] <= before["off_nadir_deg"] + 1e-6
        assert here["off_nadir_deg"] <= after["off_nadir_deg"] + 1e-6


def test_pass_rate_is_physically_plausible(demo_sats):
    """REQ-ORB-06: about 0.3 passes per satellite per day at +/-20 deg off-nadir (a sanity bound, not a tuned number)."""
    track = build_track(demo_sats[0], NOW, NOW + 14 * DAY, LIMITS.time_step_s)
    n = len(find_opportunities(track, 12.97, 77.59))
    assert 2 <= n <= 10
