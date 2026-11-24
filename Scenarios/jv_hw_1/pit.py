"""Johnson Valley PIT trial: the police car (pursue) runs the PIT controller.

manual: n (default) - Lead's setup is delegated to drive_to_southern_highway.run,
    so its AI route and speed limit stay identical to Configs/jv_hw_1.yaml. The
    simulator is stepped deterministically.
manual: y - no AI is started on lead; the camera and your inputs go to lead and
    you drive it yourself. The simulator runs in real time.

In both modes, pressing R stops the current trial and the runner restarts it
from the spawn positions with a fresh state machine.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))  # repository root
sys.path.insert(0, str(HERE))

import drive_to_southern_highway  # noqa: E402
from controller.pit_trial import run_pit_trial  # noqa: E402

TIMEOUT_SECONDS = 120
MANUAL_TIMEOUT_SECONDS = 300
PIT_CONFIG = "default"  # default; a trial config's pit_config: overrides it


METRES_PER_SECOND_PER_MPH = 0.44704


def make_run(start_lead_ai, lead_start_mph=None):
    """Build a run() whose manual: n mode starts Lead with ``start_lead_ai(beamng, scenario, trial)``.

    ``lead_start_mph`` (optional) brings Lead up to that speed along its heading
    at the start of every trial, in both modes, using BeamNGpy's set_velocity
    (reached over about 1 s). Other Johnson Valley scenarios (e.g. jv_hw_2)
    reuse this with their own settings.
    """

    def launch_lead(lead):
        if lead_start_mph:
            lead.set_velocity(lead_start_mph * METRES_PER_SECOND_PER_MPH, dt=1.0)
            print(f"  Lead starts at {lead_start_mph:g} mph.", flush=True)

    def run(beamng, scenario, trial, pit_config=PIT_CONFIG, manual=False, reset_requested=None):
        missing = {"lead", "pursue"}.difference(scenario.vehicles)
        if missing:
            raise RuntimeError(
                f"Johnson Valley trial {trial} is missing vehicles: {', '.join(sorted(missing))}")
        lead, pursuer = scenario.vehicles["lead"], scenario.vehicles["pursue"]

        if manual:
            print("  You are driving lead. pursue is driven by the PIT controller.", flush=True)
            launch_lead(lead)
            run_pit_trial(beamng, lead, pursuer, timeout=MANUAL_TIMEOUT_SECONDS,
                          pit_config=pit_config, focus="lead", realtime=True,
                          abort=reset_requested)
        else:
            start_lead_ai(beamng, scenario, trial)
            launch_lead(lead)
            print("  pursue is now driven by the PIT controller.", flush=True)
            run_pit_trial(beamng, lead, pursuer, timeout=TIMEOUT_SECONDS,
                          pit_config=pit_config, abort=reset_requested)

    return run


run = make_run(drive_to_southern_highway.run)  # jv_hw_1: Lead's Southern Highway route
