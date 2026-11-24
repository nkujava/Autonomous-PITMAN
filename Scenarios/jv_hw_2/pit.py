"""Johnson Valley PIT trial 2: ETK 800 police (pursue) vs. Covet (lead).

Same Southern Highway route for lead (up to 60 mph), manual mode and R to
restart as Scenarios/jv_hw_1/pit.py, reused through its make_run(). Two
differences: the prefab, and lead starts each trial already moving at
LEAD_START_MPH.
"""

import runpy
from pathlib import Path

_JV_HW_1 = Path(__file__).resolve().parents[1] / "jv_hw_1"
_route = runpy.run_path(str(_JV_HW_1 / "drive_to_southern_highway.py"))["run"]

LEAD_START_MPH = 30

run = runpy.run_path(str(_JV_HW_1 / "pit.py"))["make_run"](_route, lead_start_mph=LEAD_START_MPH)
