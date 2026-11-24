"""Simulator loop that drives a Pursuer with PitStateMachine.

Shared by the scenario scripts under Scenarios/. Takes BeamNGpy objects but
does not import BeamNGpy itself.
"""

from __future__ import annotations

from math import dist, hypot
from time import sleep
from typing import Callable

from .config_loader import load_pit_overrides, resolve_config_path
from .pit_state_machine import PitConfig, PitStateMachine, VehicleState

STEPS_PER_SECOND = 60
POLICE_LIGHTBAR = 1    # BeamNGpy set_lights lightbar: 0 off, 1 on, 2 higher intensity
CONTROL_INTERVAL_STEPS = 3   # 20 Hz control
ABORT_CHECK_TICKS = 5        # check for a player reset every 0.25 s

# Fallback sizes (length, width) in m when the bounding box cannot be read.
# Approximate (from info_*.json bboxes): full-size sedan, FCV hatchback, ETK 800 wagon, Covet.
FALLBACK_SIZES = {"fullsize": (5.3, 2.0), "vivace": (4.3, 1.8), "etk800": (4.7, 1.9), "covet": (3.9, 1.7)}
DEFAULT_SIZE = (4.8, 1.9)


def vehicle_size(vehicle) -> tuple[float, float]:
    """(length, width) from BeamNGpy ``Vehicle.get_bbox()``, else a fallback."""
    try:
        box = vehicle.get_bbox()
        length = dist(box["front_bottom_left"], box["rear_bottom_left"])
        width = dist(box["front_bottom_left"], box["front_bottom_right"])
        if 2.0 < length < 10.0 and 1.0 < width < 4.0:
            return length, width
        print(f"  {vehicle.vid}: implausible bbox {length:.2f} x {width:.2f} m", flush=True)
    except Exception as error:  # noqa: BLE001 - any failure falls back
        print(f"  {vehicle.vid}: could not read bbox ({error})", flush=True)
    size = FALLBACK_SIZES.get(getattr(vehicle, "model", None), DEFAULT_SIZE)
    print(f"  {vehicle.vid}: using fallback size {size[0]} x {size[1]} m", flush=True)
    return size


def run_pit_trial(
    beamng, lead, pursuer, *,
    lead_step: Callable[[dict], dict | None] | None = None,
    timeout: float = 90.0,
    pursuer_gear: int = 2,
    pit_config: str | None = "default",
    focus: str | None = None,
    realtime: bool = False,
    abort: Callable[[], bool] | None = None,
    **config_overrides,
) -> PitStateMachine:
    """Step the simulator until the machine reaches STOP and parks, or ``timeout`` s.

    ``lead_step(state)`` returns ``vehicle.control`` kwargs for Lead each tick;
    pass None when Lead is driven by BeamNG's AI or by the player. ``focus`` is
    the vehicle id the camera/player is switched to (default: the Pursuer).
    ``realtime=True`` lets the simulator run freely at wall-clock speed and
    polls at the control rate instead of pausing and stepping deterministically;
    use it when a human drives. ``abort()`` is checked a few times per second;
    when it returns True (e.g. the player pressed R) the trial stops at once
    so the caller can restart it. ``pit_config`` names a file in
    controller/configs/ (or is a path, or None for PitConfig defaults);
    ``config_overrides`` are applied on top of it. Returns the state machine so
    callers can inspect ``transitions`` and ``pit_attempts``.
    """
    overrides = {}
    if pit_config is not None:
        overrides = load_pit_overrides(pit_config)
        print(f"  PIT config: {resolve_config_path(pit_config)}", flush=True)
    overrides.update(config_overrides)
    lead_size, pursuer_size = vehicle_size(lead), vehicle_size(pursuer)
    config = PitConfig.for_vehicles(*lead_size, *pursuer_size, **overrides)
    print(f"  Lead {getattr(lead, 'model', '?')} {lead_size[0]:.2f}x{lead_size[1]:.2f} m, "
          f"Pursuer {getattr(pursuer, 'model', '?')} {pursuer_size[0]:.2f}x{pursuer_size[1]:.2f} m; "
          f"line-up {config.lineup_behind:.2f} m behind, {config.lineup_lateral:.2f} m to the "
          f"{'right' if config.side > 0 else 'left'}", flush=True)
    machine = PitStateMachine(config)
    aborted = False

    beamng.vehicles.switch(focus or pursuer.vid)
    if realtime:
        beamng.control.resume()
    else:
        beamng.control.pause()
        beamng.settings.set_deterministic(steps_per_second=STEPS_PER_SECOND)
    ai_active = False

    def hand_to_ai() -> None:
        pursuer.ai.set_target(lead.vid, "chase")
        pursuer.ai.set_speed(config.chase_speed, "limit")
        pursuer.ai.set_aggression(config.chase_aggression)

    def take_back_from_ai() -> None:
        pursuer.ai.set_mode("disabled")
        # The AI may leave its own gearbox mode; restore ours before driving.
        pursuer.set_shift_mode("realistic_automatic")
        pursuer.control(gear=pursuer_gear, throttle=0.0, brake=0.0, parkingbrake=0.0)

    try:
        take_back_from_ai()   # also clears any AI left running from before a reset
        # Police lights on from the start (no effect on a car without a light bar).
        pursuer.set_lights(lightbar=POLICE_LIGHTBAR, headlights=1)
        for vehicle in (lead, pursuer):
            vehicle.sensors.poll("state")
        start = pursuer.state["time"]
        printed = 0
        print(f"  t=  0.00s start in {machine.state.value}", flush=True)

        tick = 0
        while pursuer.state["time"] - start < timeout:
            tick += 1
            if abort is not None and tick % ABORT_CHECK_TICKS == 0 and abort():
                aborted = True
                print("  Reset detected: stopping this trial so it restarts fresh.", flush=True)
                return machine
            if lead_step is not None:
                lead_cmd = lead_step(lead.state)
                if lead_cmd:
                    lead.control(**lead_cmd)
            cmd = machine.update(VehicleState.from_beamng(pursuer.state),
                                 VehicleState.from_beamng(lead.state))
            if cmd.ai_chase and not ai_active:
                hand_to_ai()
                ai_active = True
            elif not cmd.ai_chase and ai_active:
                take_back_from_ai()
                ai_active = False
            if not ai_active:
                pursuer.control(steering=cmd.steering, throttle=cmd.throttle,
                                brake=cmd.brake, parkingbrake=cmd.parkingbrake)
            for t in machine.transitions[printed:]:
                print(f"  t={t.time - start:6.2f}s {t.source.value} -> {t.target.value} "
                      f"({t.reason})", flush=True)
            printed = len(machine.transitions)
            if machine.done and cmd.parkingbrake > 0.0:
                break
            if realtime:
                sleep(CONTROL_INTERVAL_STEPS / STEPS_PER_SECOND)
            else:
                beamng.control.step(CONTROL_INTERVAL_STEPS)
            for vehicle in (lead, pursuer):
                vehicle.sensors.poll("state")

        elapsed = pursuer.state["time"] - start
        lead_mph = hypot(*lead.state["vel"][:2]) / 0.44704
        print(f"  Finished in {machine.state.value} after {elapsed:.1f} s, "
              f"{machine.pit_attempts} PIT attempt(s); Lead at {lead_mph:.1f} mph.", flush=True)
        if not machine.done:
            print("  WARNING: timed out before reaching STOP.", flush=True)
    finally:
        if ai_active and not aborted:
            pursuer.ai.set_mode("disabled")
        if not aborted:  # after a reset the cars are already back at their spawns
            # In Arcade mode a held service brake can command reverse at a stop.
            pursuer.control(throttle=0.0, brake=0.0, parkingbrake=1.0)
        if not realtime:
            beamng.settings.set_nondeterministic()
            beamng.settings.remove_step_limit()
            beamng.control.resume()
    return machine
