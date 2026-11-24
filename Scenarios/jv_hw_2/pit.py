"""Johnson Valley PIT trial 2: ETK 800 police (pursue) vs. Covet (lead).

With manual: n, lead's AI drives jv_hw_1's Southern Highway waypoint route
(same lane keeping and car avoidance) but with no speed cap. Everything else
(manual: y, pit_config, R to restart) is shared with Scenarios/jv_hw_1/pit.py
through its make_run().
"""

import runpy
from pathlib import Path

_JV_HW_1 = Path(__file__).resolve().parents[1] / "jv_hw_1"
_route = runpy.run_path(str(_JV_HW_1 / "drive_to_southern_highway.py"))["run"]

UNCAPPED_SPEED_MPH = 450  # far above any car's top speed, so no effective cap
SPEED_MODE = "set"        # hold the speed at all times: flat out on the straight highway


def start_lead_route_uncapped(beamng, scenario, trial):
    _route(beamng, scenario, trial, speed_limit_mph=UNCAPPED_SPEED_MPH, speed_mode=SPEED_MODE)


run = runpy.run_path(str(_JV_HW_1 / "pit.py"))["make_run"](start_lead_route_uncapped)
