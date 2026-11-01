"""Every number the planner uses, tagged with where it comes from.

source = "published"  -> stated in Pixxel's public documentation
source = "derived"    -> computed from published numbers
source = "assumed"    -> my own modelling choice (NOT a Pixxel number)

Keeping this in one place makes the assumptions easy to defend and to change.
"""
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Limits:
    # --- published (docs.pixxel.space: constellation overview, tasking basics, Aurora AOI requirements)
    max_off_nadir_deg: float = 20.0       # +/-20 deg slew (+/-10 recommended for best quality)
    swath_km: float = 38.0                # Firefly swath width
    max_area_km2: float = 5000.0          # max AOI for a tasking order
    min_billable_area_km2: float = 100.0  # smaller AOIs are billed as 100 km2 (not rejected)
    cloud_max_pct: float = 20.0           # cloud cover threshold
    min_window_days: float = 1.0          # one-day tasking windows are supported
    # --- derived
    ground_speed_km_s: float = 6.9        # ~589 km altitude -> sub-satellite speed on the ground
    # --- assumed (not Pixxel numbers)
    min_sun_elev_deg: float = 20.0        # low sun = long shadows and poor signal
    slew_rate_deg_s: float = 0.5          # satellite agility is not public
    settle_s: float = 20.0                # pointing settle time after a slew
    payload_warmup_s: float = 60.0        # payload power-on to ready
    imaging_margin_s: float = 5.0         # padding before and after each capture
    max_window_days: float = 30.0         # planner limit (orbit prediction degrades with time)
    tle_stale_days: float = 7.0           # warn when orbit data is older than this
    time_step_s: float = 10.0             # orbit sampling step for pass search
    cloud_analog_years: int = 5           # past years used for the cloud-history estimate


PROVENANCE = {
    "max_off_nadir_deg": ("published", "Pixxel constellation overview: +/-20 deg slew"),
    "swath_km": ("published", "Pixxel constellation overview: 38 km swath"),
    "max_area_km2": ("published", "Aurora AOI requirements: 5,000 km2 max"),
    "min_billable_area_km2": ("published", "Aurora AOI requirements: 100 km2 minimum billable"),
    "cloud_max_pct": ("published", "Pixxel constellation overview: < 20% cloud"),
    "min_window_days": ("published", "Tasking basics: one-day windows supported"),
    "ground_speed_km_s": ("derived", "orbital speed at 589 km scaled to the ground track"),
    "min_sun_elev_deg": ("assumed", "typical optical-imaging minimum; not published"),
    "slew_rate_deg_s": ("assumed", "agility is not public"),
    "settle_s": ("assumed", "not public"),
    "payload_warmup_s": ("assumed", "not public"),
    "imaging_margin_s": ("assumed", "planner padding"),
    "max_window_days": ("assumed", "planner limit"),
    "tle_stale_days": ("assumed", "SGP4 error grows with TLE age"),
    "time_step_s": ("assumed", "pass-search sampling step"),
    "cloud_analog_years": ("assumed", "years of history used for the cloud estimate"),
}

LIMITS = Limits()

# Published constellation facts, used only to sanity-check the orbit data (not for planning).
PUBLISHED_ORBIT = {
    "altitude_km": 589.0,
    "inclination_deg": 97.65,
    "crossing_local_time_h": (10.0, 11.0),
}


def describe(limits: Limits = LIMITS) -> list[dict]:
    out = []
    for f in fields(limits):
        src, note = PROVENANCE[f.name]
        out.append({"name": f.name, "value": getattr(limits, f.name), "source": src, "note": note})
    return out
