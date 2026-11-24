"""Run the Pursuer PIT state machine against a straight-driving Lead vehicle.

Lead holds its spawn heading at LEAD_SPEED_MPH (same lane-keeping law as
drive_forward.py). Pursuer is driven by controller.PitStateMachine using
simulator ground-truth state.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repository root

from controller.pit_trial import run_pit_trial  # noqa: E402

TIMEOUT_SECONDS = 90
PIT_CONFIG = "default"  # default; a trial config's pit_config: overrides it
DRIVE_SELECTOR = 2                  # Drive in the stock automatic gearbox's shifter mapping.
LEAD_SPEED_MPH = 25
LEAD_SPEED = LEAD_SPEED_MPH * 0.44704
LEAD_GIVE_UP_HEADING = 0.5          # |dir . right| beyond this: Lead driver brakes


class LeadDriver:
    """Straight-line lane keeping plus PI speed control for Lead."""

    def __init__(self):
        self.origin = None
        self.right = None
        self.integral = 0.0

    def __call__(self, state):
        if self.origin is None:
            self.origin = tuple(state["pos"])
            self.right = (state["dir"][1], -state["dir"][0])
        x, y = state["pos"][0] - self.origin[0], state["pos"][1] - self.origin[1]
        lateral = x * self.right[0] + y * self.right[1]
        heading_error = state["dir"][0] * self.right[0] + state["dir"][1] * self.right[1]
        if abs(heading_error) > LEAD_GIVE_UP_HEADING:   # spun out: stop driving
            return dict(steering=0.0, throttle=0.0, brake=0.6)
        steering = max(-0.15, min(0.15, -0.05 * lateral - 0.9 * heading_error))
        speed = sum(v * d for v, d in zip(state["vel"], state["dir"]))
        error = LEAD_SPEED - speed
        self.integral = max(-0.25, min(0.25, self.integral + 0.01 * error))
        demand = 0.22 * error + self.integral
        return dict(steering=steering, throttle=min(0.6, max(0.0, demand)),
                    brake=min(0.4, max(0.0, -demand)))


def run(beamng, scenario, trial, pit_config=PIT_CONFIG):
    missing = {"Lead", "Pursuer"}.difference(scenario.vehicles)
    if missing:
        raise RuntimeError(f"ATT trial {trial} is missing vehicles: {', '.join(sorted(missing))}")
    lead = scenario.vehicles["Lead"]
    lead.set_shift_mode("realistic_automatic")
    lead.control(gear=DRIVE_SELECTOR, throttle=0.0, brake=0.0, parkingbrake=0.0)
    print(f"  Lead target {LEAD_SPEED_MPH} mph straight ahead.", flush=True)
    try:
        run_pit_trial(beamng, lead, scenario.vehicles["Pursuer"],
                      lead_step=LeadDriver(), timeout=TIMEOUT_SECONDS, pit_config=pit_config)
    finally:
        lead.control(throttle=0.0, brake=1.0, parkingbrake=1.0)
