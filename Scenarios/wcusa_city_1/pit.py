"""West Coast USA city PIT trial: ETK 800 police (pursue) vs. Covet (lead).

With manual: n, lead's AI is in BeamNG's flee mode, running from pursue
through the city with no fixed speed cap ("limit" mode, so the AI still
picks its own speed for corners and intersections). manual: y, pit_config
and R to restart are shared with Scenarios/jv_hw_1/pit.py through its
make_run().
"""

import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent

FLEE_FROM = "pursue"
SPEED_LIMIT = 200.0   # m/s (~450 mph): far above any car's top speed, so no fixed cap
SPEED_MODE = "limit"  # the AI drives as fast as it judges safe, up to the limit


def start_lead_fleeing(beamng, scenario, trial):
    """Put lead's AI in flee mode from pursue."""
    lead = scenario.vehicles["lead"]
    beamng.vehicles.switch(FLEE_FROM)
    lead.set_shift_mode("arcade")
    lead.ai.set_target(FLEE_FROM, "flee")   # also sets the AI mode to flee
    lead.ai.set_speed(SPEED_LIMIT, SPEED_MODE)
    print(f"  Lead AI is fleeing from {FLEE_FROM} through the city "
          f"(speed mode {SPEED_MODE}, no fixed cap).", flush=True)


run = runpy.run_path(str(HERE.parent / "jv_hw_1" / "pit.py"))["make_run"](start_lead_fleeing)
