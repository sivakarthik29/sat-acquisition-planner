"""Synthetic orbits. Used for tests and for demo mode when live orbit data is unavailable.

These are NOT real satellites. They are sun-synchronous orbits built to look like the published Firefly
orbit (589 km, 97.7 deg, descending node near 10:30 local time), so the planner can run offline.
"""
from datetime import datetime, timezone

from . import geo
from .orbit import Satellite


def _checksum(line: str) -> int:
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line[:68]) % 10


def make_tle(name: str, norad: int, epoch_unix: float, inc_deg: float, raan_deg: float, ecc: float,
             argp_deg: float, ma_deg: float, mean_motion: float) -> tuple[str, str, str]:
    """Build a valid two-line element set (no drag) from orbital elements."""
    dt = datetime.fromtimestamp(epoch_unix, tz=timezone.utc)
    day_of_year = dt.timetuple().tm_yday + (dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1e6) / 86400.0
    epoch = f"{dt.year % 100:02d}{day_of_year:012.8f}"
    l1 = f"1 {norad:05d}U 00000A   {epoch}  .00000000  00000+0  00000+0 0  999"
    l1 += str(_checksum(l1))
    l2 = (f"2 {norad:05d} {inc_deg:8.4f} {raan_deg % 360:8.4f} {int(round(ecc * 1e7)):07d} "
          f"{argp_deg % 360:8.4f} {ma_deg % 360:8.4f} {mean_motion:11.8f}{1:5d}")
    l2 += str(_checksum(l2))
    return name, l1, l2


def raan_for_descending_local_time(local_hours: float, epoch_unix: float) -> float:
    """RAAN that puts the descending node at the given local mean solar time (sun-synchronous design rule).
    Ascending node local time = descending + 12 h, and RAAN = mean-sun RA + 15 deg * (LTAN - 12 h)."""
    return float((geo.mean_sun_ra_deg(epoch_unix) + 15.0 * local_hours) % 360.0)


def demo_satellites(now_unix: float, count: int = 6, local_hours: float = 10.5) -> list[Satellite]:
    raan = raan_for_descending_local_time(local_hours, now_unix)
    sats = []
    for i in range(count):
        name, l1, l2 = make_tle(f"DEMO-{i + 1}", 90001 + i, now_unix, 97.7, raan, 0.0008, 90.0,
                                i * 360.0 / count, 14.93)
        sats.append(Satellite(name, 90001 + i, l1, l2))
    return sats
