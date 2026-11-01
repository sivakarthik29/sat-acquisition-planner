"""Earth geometry and sun position, written by hand (numpy only) so every step can be explained.

Times are UTC unix seconds (float). Simplifications, all small next to the 20 deg pointing limit:
  - UT1 is taken as UTC; polar motion and nutation are ignored (a few hundred metres on the ground)
  - local solar time is *mean* solar time (UTC + longitude/15 h), which is what crossing-time specs use
"""
import numpy as np

WGS84_A = 6378.137                    # km
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def jd_from_unix(t):
    return 2440587.5 + np.asarray(t, dtype=float) / 86400.0


def gmst_rad(jd):
    """Greenwich mean sidereal time (IAU-82 polynomial)."""
    d = np.asarray(jd, dtype=float) - 2451545.0
    T = d / 36525.0
    deg = 280.46061837 + 360.98564736629 * d + 0.000387933 * T**2 - T**3 / 38710000.0
    return np.radians(np.mod(deg, 360.0))


def rotate_z(xyz, angle):
    """Rotate vectors (n,3) about +z by `angle` (rad; scalar or (n,)). Positive = counter-clockwise."""
    c, s = np.cos(angle), np.sin(angle)
    x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
    return np.stack([c * x - s * y, s * x + c * y, z], axis=-1)


def teme_to_ecef(r_teme, jd):
    return rotate_z(r_teme, -gmst_rad(jd))


def ecef_to_teme(r_ecef, jd):
    return rotate_z(r_ecef, gmst_rad(jd))


def geodetic_to_ecef(lat_deg, lon_deg, h_km=0.0):
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
    return np.array([
        (n + h_km) * np.cos(lat) * np.cos(lon),
        (n + h_km) * np.cos(lat) * np.sin(lon),
        (n * (1.0 - WGS84_E2) + h_km) * np.sin(lat),
    ])


def ecef_to_geodetic(r):
    """(lat_deg, lon_deg, h_km) for ECEF vectors of shape (3,) or (n,3). Iterative; converges in a few steps."""
    r = np.atleast_2d(np.asarray(r, dtype=float))
    x, y, z = r[:, 0], r[:, 1], r[:, 2]
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1.0 - WGS84_E2))
    for _ in range(6):
        n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1.0 - WGS84_E2 * n / (n + h)))
    n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
    h = p / np.cos(lat) - n
    return np.degrees(lat), np.degrees(lon), h


def sun_elevation_deg(lat_deg, lon_deg, t):
    """Solar elevation at a ground point (NOAA low-precision algorithm, about 0.01 deg)."""
    jd = jd_from_unix(t)
    T = (jd - 2451545.0) / 36525.0
    L0 = np.mod(280.46646 + T * (36000.76983 + 0.0003032 * T), 360.0)
    M = np.radians(357.52911 + T * (35999.05029 - 0.0001537 * T))
    C = (np.sin(M) * (1.914602 - T * (0.004817 + 0.000014 * T))
         + np.sin(2 * M) * (0.019993 - 0.000101 * T) + np.sin(3 * M) * 0.000289)
    omega = np.radians(125.04 - 1934.136 * T)
    lam = np.radians(L0 + C - 0.00569 - 0.00478 * np.sin(omega))           # apparent longitude
    eps = np.radians(23.439291 - 0.0130042 * T + 0.00256 * np.cos(omega))  # obliquity
    decl = np.arcsin(np.sin(eps) * np.sin(lam))
    ra = np.arctan2(np.cos(eps) * np.sin(lam), np.cos(lam))
    hour_angle = gmst_rad(jd) + np.radians(lon_deg) - ra
    lat = np.radians(lat_deg)
    s = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(hour_angle)
    return np.degrees(np.arcsin(np.clip(s, -1.0, 1.0)))


def mean_sun_ra_deg(t):
    """Right ascension of the *mean* sun (relates a node's RAAN to its local time)."""
    T = (jd_from_unix(t) - 2451545.0) / 36525.0
    return np.mod(280.46646 + 36000.76983 * T, 360.0)


def local_mean_solar_hours(lon_deg, t):
    utc_h = np.mod(np.asarray(t, dtype=float), 86400.0) / 3600.0
    return np.mod(utc_h + np.asarray(lon_deg) / 15.0, 24.0)
