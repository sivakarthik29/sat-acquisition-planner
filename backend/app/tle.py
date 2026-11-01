"""Orbit data (TLE) loading: CelesTrak -> local cache -> synthetic demo, in that order.

CelesTrak asks users not to poll more than once every two hours, so a fresh cache is reused for that long.
"""
import logging
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .demo import demo_satellites
from .orbit import Satellite

log = logging.getLogger("planner.tle")

# NORAD IDs of the six Firefly satellites (public catalogue). Edit here if the catalogue changes.
FIREFLY_IDS = [62697, 62698, 62699, 65319, 65320, 65322]
CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={id}&FORMAT=tle"
CACHE_TTL_S = 2 * 3600


@dataclass
class LoadResult:
    satellites: list
    source: str          # "live" | "cache" | "demo"
    note: str
    fetched_at: float | None


def parse_tle_text(text: str) -> list[Satellite]:
    """Parse 3-line (name + 2 lines) or 2-line element sets. Lines that do not parse are skipped."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    sats, i = [], 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            name, l1, l2, i = f"NORAD {lines[i][2:7].strip()}", lines[i], lines[i + 1], i + 2
        elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            name, l1, l2, i = lines[i].lstrip("0 ").strip(), lines[i + 1], lines[i + 2], i + 3
        else:
            i += 1
            continue
        try:
            sats.append(Satellite(name, int(l1[2:7]), l1, l2))
        except Exception as exc:  # malformed element set
            log.warning("skipping unparsable TLE for %s: %s", name, exc)
    return sats


def fetch_celestrak(norad_id: int, timeout: float = 10.0) -> str:
    req = urllib.request.Request(CELESTRAK_URL.format(id=norad_id), headers={"User-Agent": "sat-planner/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def load_satellites(cache_dir: Path, mode: str = "live", now: float | None = None,
                    fetch=fetch_celestrak, ids=FIREFLY_IDS) -> LoadResult:
    now = time.time() if now is None else now
    if mode == "demo":
        return LoadResult(demo_satellites(now), "demo", "Synthetic demo orbits (SAT_SOURCE=demo).", None)

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / "tle_cache.txt"
    if cache.exists() and now - cache.stat().st_mtime < CACHE_TTL_S:
        sats = parse_tle_text(cache.read_text())
        if sats:
            return LoadResult(sats, "cache", "Fresh cache (under 2 hours old).", cache.stat().st_mtime)

    chunks = []
    for norad_id in ids:
        try:
            text = fetch(norad_id)
            if parse_tle_text(text):
                chunks.append(text.strip())
            else:
                log.warning("no element set returned for %s", norad_id)
        except Exception as exc:
            log.warning("fetch failed for %s: %s", norad_id, exc)
    if chunks:
        cache.write_text("\n".join(chunks) + "\n")
        return LoadResult(parse_tle_text(cache.read_text()), "live", f"Fetched {len(chunks)} of {len(ids)} from CelesTrak.", now)

    if cache.exists():
        sats = parse_tle_text(cache.read_text())
        if sats:
            return LoadResult(sats, "cache", "CelesTrak unreachable; using an older cache.", cache.stat().st_mtime)
    return LoadResult(demo_satellites(now), "demo", "CelesTrak unreachable and no cache: using synthetic demo orbits.", None)
