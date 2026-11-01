"""Turn a schedule into a timed command list, and check any command list against the rules before 'uplink'.

The command set is notional (see data/command_dictionary_v1.json). The validator is independent of the compiler:
it recomputes pointing geometry from the orbit data instead of trusting the schedule.

Validator rules
  V-DICT-UNKNOWN    command is not in the dictionary
  V-PARAM-MISSING / V-PARAM-EXTRA / V-PARAM-TYPE / V-PARAM-RANGE   parameters do not match the dictionary
  V-TIME-ORDER      commands for one satellite are not in time order
  V-SEQ-PAYLOAD     imaging started without the payload on for the warm-up time
  V-SEQ-POINT       imaging started without a target pointing command
  V-TIME-SLEW       imaging started before the slew could finish
  V-GEOM-HORIZON    target is below the satellite's horizon at imaging time
  V-GEOM-OFFNADIR   target is outside the off-nadir limit at imaging time
  V-GEOM-SUN        sun is below the minimum elevation at imaging time
  V-SEQ-PAYLOAD-OFF payload left on at the end of the sequence (warning)
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import LIMITS, Limits
from .orbit import Satellite, pointing_at
from .rules import slew_time_s
from .scheduler import Candidate

DICTIONARY_PATH = Path(__file__).parent / "data" / "command_dictionary_v1.json"
NADIR_RETURN_S = 600.0   # if the next capture is further away than this, the satellite returns to nadir in between
TOL = 1e-3               # seconds


@dataclass
class Command:
    t: float
    sat: int
    name: str
    params: dict = field(default_factory=dict)


@dataclass
class Violation:
    rule: str
    message: str
    t: float | None = None
    sat: int | None = None
    severity: str = "error"   # "error" | "warning"


@dataclass
class ValidationReport:
    passed: bool
    violations: list[Violation]
    checked: int


def load_dictionary(path: Path = DICTIONARY_PATH) -> dict:
    return json.loads(Path(path).read_text())


# ---- compiler ---------------------------------------------------------------------------
def compile_plan(selected: list[Candidate], limits: Limits = LIMITS, bandset: int = 1) -> list[Command]:
    """One block per capture: warm up the payload, finish the slew, image, power down."""
    cmds: list[Command] = []
    by_sat: dict[int, list[Candidate]] = {}
    for c in sorted(selected, key=lambda c: c.time):
        by_sat.setdefault(c.norad_id, []).append(c)
    for sat, caps in by_sat.items():
        prev_roll, prev_end = 0.0, None
        for c in caps:
            if prev_end is not None and c.pad_start - prev_end > NADIR_RETURN_S:
                cmds.append(Command(prev_end + 1.0, sat, "ADCS_POINT_NADIR"))
                prev_roll = 0.0
            cmds.append(Command(c.pad_start - slew_time_s(prev_roll, c.roll_deg, limits), sat, "ADCS_POINT_TARGET",
                                {"lat_deg": round(c.lat, 5), "lon_deg": round(c.lon, 5)}))
            cmds.append(Command(c.pad_start - limits.payload_warmup_s, sat, "PAYLOAD_ON"))
            cmds.append(Command(c.pad_start + limits.imaging_margin_s, sat, "PAYLOAD_IMAGE",
                                {"duration_s": round(c.duration_s, 2), "bandset": bandset}))
            cmds.append(Command(c.pad_end, sat, "PAYLOAD_OFF"))
            prev_roll, prev_end = c.roll_deg, c.pad_end
        cmds.append(Command(prev_end + 1.0, sat, "ADCS_POINT_NADIR"))
    return sorted(cmds, key=lambda k: (k.sat, k.t))


# ---- validator --------------------------------------------------------------------------
def _check_params(cmd: Command, spec: dict, out: list[Violation]):
    for pname, pspec in spec["params"].items():
        if pname not in cmd.params:
            out.append(Violation("V-PARAM-MISSING", f"{cmd.name}: missing parameter '{pname}'.", cmd.t, cmd.sat))
            continue
        val = cmd.params[pname]
        ok_type = (isinstance(val, int) and not isinstance(val, bool)) if pspec["type"] == "int" else \
                  (isinstance(val, (int, float)) and not isinstance(val, bool))
        if not ok_type:
            out.append(Violation("V-PARAM-TYPE", f"{cmd.name}: '{pname}' must be {pspec['type']}.", cmd.t, cmd.sat))
        elif not (pspec["min"] <= val <= pspec["max"]):
            out.append(Violation("V-PARAM-RANGE",
                                 f"{cmd.name}: '{pname}' = {val} is outside {pspec['min']} to {pspec['max']}.", cmd.t, cmd.sat))
    for pname in cmd.params:
        if pname not in spec["params"]:
            out.append(Violation("V-PARAM-EXTRA", f"{cmd.name}: unexpected parameter '{pname}'.", cmd.t, cmd.sat))


def validate(commands: list[Command], dictionary: dict, satellites: list[Satellite],
             limits: Limits = LIMITS) -> ValidationReport:
    out: list[Violation] = []
    sat_by_id = {s.norad_id: s for s in satellites}
    known = dictionary["commands"]

    streams: dict[int, list[Command]] = {}
    for c in commands:                                   # keep the order the commands were given in
        streams.setdefault(c.sat, []).append(c)

    for sat_id, stream in streams.items():
        for a, b in zip(stream, stream[1:]):
            if b.t < a.t - TOL:
                out.append(Violation("V-TIME-ORDER", f"{b.name} is scheduled before the preceding {a.name}.", b.t, sat_id))
        payload_on_since: float | None = None
        target: dict | None = None            # last ADCS_POINT_TARGET: {"lat","lon","t"}
        roll = 0.0                            # roll the satellite currently holds (0 = nadir)
        for c in sorted(stream, key=lambda k: k.t):
            spec = known.get(c.name)
            if spec is None:
                out.append(Violation("V-DICT-UNKNOWN", f"'{c.name}' is not in the command dictionary.", c.t, sat_id))
                continue
            before = len(out)
            _check_params(c, spec, out)
            if len(out) > before:
                continue                       # do not reason about a malformed command
            if c.name == "PAYLOAD_ON":
                payload_on_since = c.t
            elif c.name == "PAYLOAD_OFF":
                payload_on_since = None
            elif c.name == "ADCS_POINT_NADIR":
                target, roll = None, 0.0
            elif c.name == "ADCS_POINT_TARGET":
                target = {"lat": c.params["lat_deg"], "lon": c.params["lon_deg"], "t": c.t}
            elif c.name == "PAYLOAD_IMAGE":
                if payload_on_since is None or c.t - payload_on_since < limits.payload_warmup_s - TOL:
                    out.append(Violation("V-SEQ-PAYLOAD",
                                         f"Imaging starts without {limits.payload_warmup_s:.0f} s of payload warm-up.", c.t, sat_id))
                if target is None:
                    out.append(Violation("V-SEQ-POINT", "Imaging starts with no target pointing command.", c.t, sat_id))
                    continue
                sat = sat_by_id.get(sat_id)
                if sat is None:
                    out.append(Violation("V-DICT-UNKNOWN", f"No orbit data for satellite {sat_id}.", c.t, sat_id))
                    continue
                mid = c.t + c.params["duration_s"] / 2.0
                g = pointing_at(sat, target["lat"], target["lon"], mid)
                need = slew_time_s(roll, g["roll_deg"], limits)
                have = c.t - limits.imaging_margin_s - target["t"]
                if have < need - TOL:
                    out.append(Violation("V-TIME-SLEW",
                                         f"Slew needs {need:.0f} s but only {max(have, 0):.0f} s is available.", c.t, sat_id))
                if g["elevation_deg"] <= 0:
                    out.append(Violation("V-GEOM-HORIZON", "Target is below the satellite's horizon.", c.t, sat_id))
                elif g["off_nadir_deg"] > limits.max_off_nadir_deg + 1e-6:
                    out.append(Violation("V-GEOM-OFFNADIR",
                                         f"Target is {g['off_nadir_deg']:.1f} deg off-nadir; the limit is {limits.max_off_nadir_deg:.0f} deg.", c.t, sat_id))
                if g["sun_elev_deg"] < limits.min_sun_elev_deg:
                    out.append(Violation("V-GEOM-SUN",
                                         f"Sun elevation is {g['sun_elev_deg']:.0f} deg; the minimum is {limits.min_sun_elev_deg:.0f} deg.", c.t, sat_id))
                roll = g["roll_deg"]
        if payload_on_since is not None:
            out.append(Violation("V-SEQ-PAYLOAD-OFF", "Payload is still on at the end of the sequence.",
                                 stream[-1].t, sat_id, severity="warning"))

    return ValidationReport(not any(v.severity == "error" for v in out), out, len(commands))
