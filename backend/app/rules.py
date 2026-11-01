"""Operating rules shared by the scheduler and the validator (single source of truth)."""
from .config import LIMITS, Limits


def imaging_duration_s(area_km2: float, limits: Limits = LIMITS) -> float:
    """The AOI is modelled as one strip: length = area / swath, duration = length / ground speed."""
    strip_km = area_km2 / limits.swath_km
    return max(1.0, strip_km / limits.ground_speed_km_s)


def slew_time_s(roll_from_deg: float, roll_to_deg: float, limits: Limits = LIMITS) -> float:
    return limits.settle_s + abs(roll_to_deg - roll_from_deg) / limits.slew_rate_deg_s


def required_gap_s(roll_a_deg: float, roll_b_deg: float, limits: Limits = LIMITS) -> float:
    """Minimum gap between the padded end of capture A and the padded start of capture B on one satellite.
    The satellite must finish slewing, and the payload must be switched off and warmed up again."""
    return max(slew_time_s(roll_a_deg, roll_b_deg, limits), limits.payload_warmup_s + 10.0)
