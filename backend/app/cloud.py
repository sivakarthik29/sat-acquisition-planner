"""Cloud history and the clear-capture probability.

Method ("analog years"): for each of the last N years, shift every pass in the window back by that many years and
look up the hourly cloud cover at the same place and date. A year counts as "clear" if at least one pass would have
had cloud below the threshold. Probability = clear years / years with data.

Why this way: it keeps day-to-day weather persistence inside each year, which an independent per-pass draw would lose.
Limits: a handful of years is a small sample; hourly reanalysis cloud is not the same as satellite-seen cloud.
Data: Open-Meteo historical weather API (free, no key; check its terms for commercial use).
"""
import json
import logging
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from .config import LIMITS, Limits

log = logging.getLogger("planner.cloud")
URL = ("https://archive-api.open-meteo.com/v1/archive?latitude={lat:.3f}&longitude={lon:.3f}"
       "&start_date={start}&end_date={end}&hourly=cloud_cover&timezone=GMT")


class OpenMeteoClient:
    def __init__(self, cache_dir: Path | None = None, timeout: float = 15.0):
        self.cache_dir = cache_dir
        self.timeout = timeout

    def hourly_cloud(self, lat: float, lon: float, start: date, end: date) -> dict[int, float]:
        """Hourly cloud cover (%) keyed by unix time of the hour."""
        key = f"cloud_{lat:.2f}_{lon:.2f}_{start}_{end}.json"
        path = self.cache_dir / key if self.cache_dir else None
        if path and path.exists():
            raw = json.loads(path.read_text())
        else:
            url = URL.format(lat=lat, lon=lon, start=start, end=end)
            req = urllib.request.Request(url, headers={"User-Agent": "sat-planner/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read())
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(raw))
        out = {}
        for ts, val in zip(raw["hourly"]["time"], raw["hourly"]["cloud_cover"]):
            if val is not None:
                out[int(datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).timestamp())] = float(val)
        return out


def _shift_years(t: float, years: int) -> float:
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    try:
        return dt.replace(year=dt.year + years).timestamp()
    except ValueError:                     # 29 Feb in a non-leap year
        return dt.replace(year=dt.year + years, day=28).timestamp()


def clear_capture_probability(client, lat: float, lon: float, pass_times: list[float],
                              limits: Limits = LIMITS) -> tuple[float | None, dict]:
    """Return (probability or None, detail). None means there was not enough history to say."""
    per_year: dict[int, dict] = {}
    for k in range(1, limits.cloud_analog_years + 1):
        shifted = [_shift_years(t, -k) for t in pass_times]
        d0 = datetime.fromtimestamp(min(shifted), tz=timezone.utc).date()
        d1 = datetime.fromtimestamp(max(shifted), tz=timezone.utc).date()
        try:
            hourly = client.hourly_cloud(lat, lon, d0, d1)
        except Exception as exc:
            log.warning("cloud history request failed (%s): %s", d0, exc)
            continue
        vals = [hourly.get(int(round(t / 3600.0)) * 3600) for t in shifted]
        vals = [v for v in vals if v is not None]
        if vals:
            best = min(vals)
            per_year[d0.year] = {"best_cloud_pct": round(best, 1), "clear": best < limits.cloud_max_pct}
    if len(per_year) < 3:
        return None, {"years": per_year, "note": "Cloud history unavailable or too short, so no probability is shown."}
    p = sum(1 for y in per_year.values() if y["clear"]) / len(per_year)
    return p, {"years": per_year, "note": f"{len(per_year)} past years, same dates and hours."}
