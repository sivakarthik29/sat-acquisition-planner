# Requirements

Each requirement has an ID. Tests carry the ID in their docstring, and `scripts/check_traceability.py`
fails CI if a requirement has no test or a test names a requirement that does not exist.

| ID | Requirement | Why it exists |
|---|---|---|
| REQ-GEO-01 | Geodetic and ECEF conversions round-trip within 1 m. | Every pass calculation depends on correct ground positions. |
| REQ-GEO-02 | Sun elevation and sidereal time match known values (solstice, equinox, J2000) within 1 deg. | Daylight is a hard condition for optical imaging. |
| REQ-ORB-01 | Altitude and inclination from a real Firefly element set are close to the published values. | Checks the orbit data against Pixxel's public numbers. |
| REQ-ORB-02 | Descending-node local time of real element sets is inside the published 10:00-11:00 window. | Same, for crossing time. |
| REQ-ORB-03 | An orbit designed for a given local time measures that local time. | Independent check of the crossing-time method itself. |
| REQ-ORB-04 | Off-nadir angle matches an independent Skyfield computation within 0.5 deg. | My geometry must agree with a trusted library. |
| REQ-ORB-05 | A target on the far side of the Earth is never reported as a pass. | A small off-nadir angle alone does not mean the target is visible. |
| REQ-ORB-06 | Every pass is within the off-nadir limit, visible, and timed at a true minimum; pass counts are physically plausible. | Pass search must be correct and not invent opportunities. |
| REQ-FEA-01 | Area above the limit fails; area below the billable minimum is accepted with a note. | Published AOI rules. |
| REQ-FEA-02 | Windows shorter than the minimum or longer than the planner range fail. | Published window rule and a planner limit. |
| REQ-FEA-03 | A feasible request explains every rule applied; stale orbit data is a warning, not a failure. | Explainability: reasons, not a bare yes or no. |
| REQ-FEA-04 | If every pass is in the dark the request fails with the sun-elevation reason. | Optical imaging needs light. |
| REQ-FEA-05 | The clear-capture probability is 1 for always-clear history, 0 for always-cloudy, and None when there is no history. | Never show a made-up number. |
| REQ-SCH-01 | Close captures on one satellite conflict; other satellites and distant captures do not; fast pair search equals brute force. | One shared conflict rule for both solvers. |
| REQ-SCH-02 | The optimizer is never worse than greedy and is strictly better on a crafted case. | Justifies using an optimizer at all. |
| REQ-SCH-03 | Plans have no clashes and at most one capture per request; unschedulable requests get a reason. | Valid, explainable plans. |
| REQ-CMD-01 | The compiled command list passes the validator and has a full command block per capture. | Compiler and validator agree. |
| REQ-CMD-02 | The validator rejects each class of bad command list with the right rule id. | Catches errors before they are uplinked. |
| REQ-CMD-03 | The dictionary diff flags breaking, review and informational changes, and the CLI exit code reflects them. | Models review of an operational database change request. |
| REQ-TLE-01 | Element sets parse; loading falls back live, then cache, then demo, and says which. | The tool keeps working offline and is honest about its data. |
| REQ-API-01 | Health, limits (with provenance) and satellites endpoints work. | Operability and transparency. |
| REQ-API-02 | The feasibility endpoint returns checks and passes and rejects bad input with 422. | Safe public interface. |
| REQ-API-03 | The plan endpoint compares both solvers, returns a valid command list, and rejects bad input. | End-to-end behaviour. |
