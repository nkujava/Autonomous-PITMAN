"""Pursuit-and-PIT state machine for the Pursuer (police) vehicle.

States::

    CHASE --(within chase_distance of the line-up point)--> LINE_UP
      ^                                                        |
      +----(more than chase_distance + chase_hysteresis away)--+

    LINE_UP --(speed/position matched)--> PIT --(predicted loss of control,
                                                 Lead spun, or timeout)--> RECOVER
       ^                                                                 |
       +-------------(Pursuer stable, Lead still driving)----------------+
                                                                         |
    STOP <-----------(Pursuer stable, Lead stopped)----------------------+

    Lead stopping after at least one PIT attempt also ends the trial from
    CHASE or LINE_UP: Lead only counts as pitted once its speed is ~0.

In CHASE the Pursuer is handed to BeamNG's built-in chase AI (the returned
Command has ``ai_chase=True`` and no driver inputs); every other state is our
own controller. The caller switches the AI on and off.

This module is pure Python and does not import BeamNGpy, so it can be unit
tested without the simulator. It uses simulator ground-truth state (position,
velocity, heading); it is not a perception system.

Conventions (BeamNG ``state`` sensor, same as Scenarios/att/drive_forward.py):

- World frame: x and y horizontal, z up. Distances in m, speeds in m/s,
  angles in rad, headings measured counter-clockwise from +x.
- ``dir`` is the vehicle's forward unit vector.
- Steering command: positive steers right, negative steers left.
- "Lead frame": longitudinal = along Lead's heading (positive ahead of Lead),
  lateral = toward Lead's right side (positive right).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class State(Enum):
    CHASE = "chase"
    LINE_UP = "line_up"
    PIT = "pit"
    RECOVER = "recover"
    STOP = "stop"


def wrap_angle(angle: float) -> float:
    """Wrap an angle to [-pi, pi)."""
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class VehicleState:
    """Planar vehicle state. ``hx, hy`` is the unit forward vector."""

    time: float
    x: float
    y: float
    vx: float
    vy: float
    hx: float
    hy: float

    @classmethod
    def from_beamng(cls, state: dict) -> "VehicleState":
        """Build from a polled BeamNGpy ``vehicle.state`` dictionary."""
        dx, dy = state["dir"][0], state["dir"][1]
        norm = math.hypot(dx, dy) or 1.0
        return cls(
            float(state["time"]),
            float(state["pos"][0]), float(state["pos"][1]),
            float(state["vel"][0]), float(state["vel"][1]),
            dx / norm, dy / norm,
        )

    @property
    def heading(self) -> float:
        return math.atan2(self.hy, self.hx)

    @property
    def forward_speed(self) -> float:
        return self.vx * self.hx + self.vy * self.hy

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def sideslip(self, min_speed: float = 3.0) -> float:
        """Body sideslip angle (rad, velocity left of heading positive); 0 when slow."""
        if self.speed < min_speed:
            return 0.0
        lateral = -self.vx * self.hy + self.vy * self.hx
        return math.atan2(lateral, abs(self.forward_speed))


@dataclass(frozen=True)
class Command:
    """Normalized BeamNG driver inputs for ``vehicle.control(...)``."""

    steering: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0
    parkingbrake: float = 0.0
    ai_chase: bool = False   # True: let BeamNG's chase AI drive; ignore the inputs above


@dataclass(frozen=True)
class Transition:
    time: float
    source: State
    target: State
    reason: str


@dataclass
class PitConfig:
    # Line-up geometry, in the Lead frame (Pursuer centre relative to Lead centre).
    side: int = 1                      # +1: Pursuer lines up on Lead's right, -1: left
    lineup_behind: float = 3.5         # m behind Lead's centre (front bumper near Lead's rear axle)
    lineup_lateral: float = 2.4        # m centre-to-centre side offset (~car width + gap)

    # Size-scaled geometry knobs used by for_vehicles() to derive lineup_behind,
    # lineup_lateral, pit_lateral and contact_lateral from the cars' bounding boxes.
    rear_axle_fraction: float = 0.3    # Lead's rear axle position behind its centre, x length
    lineup_gap: float = 0.3            # m side gap between the cars while lining up
    pit_depth: float = 1.5             # m the PIT aim point sits inside Lead's flank
    contact_margin: float = 0.2        # m beyond touching that still counts as contact
    # CHASE: BeamNG's built-in chase AI drives while far from the line-up point.
    chase_distance: float = 5.0        # m from the line-up point: hand over to LINE_UP
    chase_hysteresis: float = 3.0      # m extra before LINE_UP hands back to CHASE
    chase_speed: float = 90.0          # m/s AI speed limit (~200 mph: effectively uncapped)
    chase_aggression: float = 1.0      # BeamNG AI aggression, 0..1

    lookahead: float = 8.0             # m pure-pursuit look-ahead along the offset line
    max_closing_speed: float = 8.0     # m/s max speed difference while closing the gap
    gap_gain: float = 2              # (m/s) per m of longitudinal error

    # PIT entry tolerances (loose: commit to the hit early).
    speed_tolerance: float = 2.5             # m/s
    longitudinal_tolerance: float = 1.5      # m
    lateral_tolerance: float = 0.9           # m
    heading_tolerance: float = math.radians(12)
    min_lead_speed: float = 4.0              # m/s; no PIT on a stationary car
    entry_hold_time: float = 0.2             # s the alignment must hold before PIT

    # PIT execution: steer into Lead's rear quarter and keep pushing, with a
    # throttle ramp, until Pursuer predicts its own loss of control.
    pit_lateral: float = 0.4           # m target lateral offset (deep inside Lead's flank)
    pit_lookahead: float = 3.0         # m shorter look-ahead -> firmer steer-in
    pit_max_steering: float = .9
    pit_throttle_start: float = 0.7    # throttle at PIT entry
    pit_throttle_ramp: float = 1.5     # throttle added per second in PIT (full in 0.2 s)
    pit_max_throttle: float = 1.0
    contact_lateral: float = 2.1       # m centre-to-centre lateral distance treated as contact
    contact_longitudinal: float = 4.5  # m overlap window for contact
    pit_timeout: float = 5.0           # s safety limit on the push

    # Pursuer loss-of-control prediction: each signal is extrapolated
    # prediction_horizon s ahead with its filtered rate of change.
    # Wide limits: keep pushing through the impact and bail out late.
    prediction_horizon: float = 0.2                  # s
    pit_max_yaw_rate: float = math.radians(45)       # rad/s
    pit_max_slip: float = math.radians(12)           # rad body sideslip
    pit_max_heading_error: float = math.radians(35)  # rad from road heading
    min_slip_speed: float = 3.0                      # m/s; sideslip ignored below this
    rate_filter: float = 0.3                         # low-pass weight on new rate samples

    # Recover: brake and hold the road heading (Lead's heading at PIT entry).
    recover_brake: float = 0.35
    recover_min_time: float = 1.0
    recover_timeout: float = 8.0
    stable_yaw_rate: float = math.radians(8)
    stable_heading_error: float = math.radians(10)
    stable_hold_time: float = 0.5

    # Outcome check: did the PIT work? Lead counts as pitted only once it has
    # stopped (speed below lead_stopped_speed for lead_stopped_hold) after at
    # least one PIT attempt.
    spin_heading: float = math.radians(60)   # Lead heading change that ends the PIT push early
    lead_stopped_speed: float = 0.1          # m/s, "speed of 0" with physics noise
    lead_stopped_hold: float = 0.5           # s Lead must stay stopped

    # Stop.
    stop_speed: float = 0.5

    # Gains and limits.
    steer_gain: float = 1.2            # steering per rad of pure-pursuit angle
    max_steering: float = 0.5
    heading_gain: float = 1.5          # recover/stop: steering per rad heading error (P)
    yaw_rate_gain: float = 0.4         # recover/stop: steering per rad/s yaw rate (D)
    speed_kp: float = 0.25
    speed_ki: float = 0.05
    integral_limit: float = 0.25
    max_throttle: float = 1.0
    max_brake: float = 0.6

    @classmethod
    def for_vehicles(
        cls, lead_length: float, lead_width: float,
        pursuer_length: float, pursuer_width: float, **overrides,
    ) -> "PitConfig":
        """Scale the line-up and contact geometry to the two vehicles' sizes (m).

        Approximation: Lead's rear axle sits ``rear_axle_fraction * length``
        behind its centre, and the Pursuer's front bumper is placed level with
        that axle. Any derived field given in ``overrides`` is used as-is.
        """
        knobs = cls(**overrides)   # overrides may change the geometry knobs
        half_widths = 0.5 * (lead_width + pursuer_width)
        geometry = dict(
            lineup_behind=knobs.rear_axle_fraction * lead_length + 0.5 * pursuer_length,
            lineup_lateral=half_widths + knobs.lineup_gap,
            contact_lateral=half_widths + knobs.contact_margin,
            pit_lateral=half_widths - knobs.pit_depth,
            contact_longitudinal=0.5 * (lead_length + pursuer_length),
        )
        geometry.update(overrides)
        return cls(**geometry)


class YawRateEstimator:
    """Finite-difference yaw rate from successive headings (rad/s, CCW positive)."""

    def __init__(self) -> None:
        self._last: tuple[float, float] | None = None
        self.rate = 0.0

    def update(self, vehicle: VehicleState) -> float:
        if self._last is not None:
            dt = vehicle.time - self._last[0]
            if dt > 1e-6:
                self.rate = wrap_angle(vehicle.heading - self._last[1]) / dt
        self._last = (vehicle.time, vehicle.heading)
        return self.rate


class StabilityPredictor:
    """Predicts yaw rate, sideslip and heading error ``horizon`` s ahead.

    Each signal is extrapolated linearly with a low-pass-filtered finite
    difference: x_pred = x + horizon * dx/dt.
    """

    def __init__(self, filter_weight: float = 0.5) -> None:
        self.weight = filter_weight
        self._last: tuple[float, float, float, float] | None = None
        self.values = (0.0, 0.0, 0.0)   # yaw rate, sideslip, heading error
        self.rates = [0.0, 0.0, 0.0]

    def update(self, time: float, yaw_rate: float, slip: float, heading_error: float) -> None:
        values = (yaw_rate, slip, heading_error)
        if self._last is not None:
            dt = time - self._last[0]
            if dt > 1e-6:
                for i, (new, old) in enumerate(zip(values, self._last[1:])):
                    sample = (new - old) / dt
                    self.rates[i] += self.weight * (sample - self.rates[i])
        self._last = (time, *values)
        self.values = values

    def predict(self, horizon: float) -> tuple[float, float, float]:
        return tuple(v + horizon * r for v, r in zip(self.values, self.rates))


class PitStateMachine:
    """Call :meth:`update` once per control interval with both vehicle states."""

    def __init__(self, config: PitConfig | None = None) -> None:
        self.config = config or PitConfig()
        if self.config.side not in (-1, 1):
            raise ValueError("PitConfig.side must be +1 (right) or -1 (left).")
        self.state = State.CHASE
        self.transitions: list[Transition] = []
        self.pit_attempts = 0
        self._pursuer_yaw = YawRateEstimator()
        self._stability = StabilityPredictor(self.config.rate_filter)
        self.contact_made = False     # set once contact is detected during a PIT
        self._entered = None         # time the current state was entered
        self._timer_start = None      # start of the current hold/contact timer
        self._road_heading = None     # Lead heading at PIT entry
        self._lead_stopped_since = None   # time Lead's speed last dropped to ~0
        self._speed_integral = 0.0

    # ------------------------------------------------------------------ helpers

    @property
    def done(self) -> bool:
        return self.state is State.STOP

    def lead_frame(self, pursuer: VehicleState, lead: VehicleState) -> tuple[float, float]:
        """Pursuer position relative to Lead as (longitudinal, lateral)."""
        dx, dy = pursuer.x - lead.x, pursuer.y - lead.y
        longitudinal = dx * lead.hx + dy * lead.hy
        lateral = dx * lead.hy - dy * lead.hx   # right vector = (hy, -hx)
        return longitudinal, lateral

    def lineup_distance(self, pursuer: VehicleState, lead: VehicleState) -> float:
        """Distance (m) from the Pursuer's centre to its line-up point beside Lead."""
        c = self.config
        longitudinal, lateral = self.lead_frame(pursuer, lead)
        return math.hypot(longitudinal + c.lineup_behind, lateral - c.side * c.lineup_lateral)

    def _go(self, target: State, now: float, reason: str) -> None:
        self.transitions.append(Transition(now, self.state, target, reason))
        self.state = target
        self._entered = now
        self._timer_start = None
        self._speed_integral = 0.0

    def _held(self, condition: bool, now: float, duration: float) -> bool:
        """True once ``condition`` has been continuously true for ``duration`` s."""
        if not condition:
            self._timer_start = None
            return False
        if self._timer_start is None:
            self._timer_start = now
        return now - self._timer_start >= duration

    def _speed_command(self, current: float, desired: float) -> tuple[float, float]:
        c = self.config
        error = desired - current
        self._speed_integral = clamp(
            self._speed_integral + c.speed_ki * error, -c.integral_limit, c.integral_limit
        )
        demand = c.speed_kp * error + self._speed_integral
        return clamp(demand, 0.0, c.max_throttle), clamp(-demand, 0.0, c.max_brake)

    def _track_offset_line(
        self, pursuer: VehicleState, lead: VehicleState, lateral: float,
        lookahead: float, max_steering: float,
    ) -> float:
        """Pure-pursuit steering toward a line parallel to Lead at ``lateral`` m."""
        longitudinal, _ = self.lead_frame(pursuer, lead)
        ahead = longitudinal + lookahead
        aim_x = lead.x + lead.hx * ahead + lead.hy * lateral
        aim_y = lead.y + lead.hy * ahead - lead.hx * lateral
        to_x, to_y = aim_x - pursuer.x, aim_y - pursuer.y
        # Signed angle from Pursuer heading to the aim point, CCW (left) positive.
        angle = math.atan2(pursuer.hx * to_y - pursuer.hy * to_x,
                           pursuer.hx * to_x + pursuer.hy * to_y)
        return clamp(-self.config.steer_gain * angle, -max_steering, max_steering)

    def _hold_heading(self, pursuer: VehicleState, yaw_rate: float) -> float:
        """PD steering that holds the road heading and damps yaw."""
        c = self.config
        error = wrap_angle(pursuer.heading - self._road_heading)   # >0: turned left
        steering = c.heading_gain * error + c.yaw_rate_gain * yaw_rate
        return clamp(steering, -c.max_steering, c.max_steering)

    def loss_of_control_warnings(self) -> list[str]:
        """Pursuer signals predicted to exceed their PIT limits within the horizon."""
        c = self.config
        yaw_rate, slip, heading = self._stability.predict(c.prediction_horizon)
        checks = (("yaw rate", yaw_rate, c.pit_max_yaw_rate, " deg/s"),
                  ("sideslip", slip, c.pit_max_slip, " deg"),
                  ("heading", heading, c.pit_max_heading_error, " deg"))
        return [f"{name} {math.degrees(value):+.0f}{unit}"
                for name, value, limit, unit in checks if abs(value) > limit]

    def lead_pitted(self, now: float) -> bool:
        """Lead has been stopped for lead_stopped_hold s after at least one PIT attempt."""
        return (self.pit_attempts > 0 and self._lead_stopped_since is not None
                and now - self._lead_stopped_since >= self.config.lead_stopped_hold)

    def _track_lead_stopped(self, lead: VehicleState, now: float) -> None:
        if lead.speed >= self.config.lead_stopped_speed:
            self._lead_stopped_since = None
        elif self._lead_stopped_since is None:
            self._lead_stopped_since = now

    # ------------------------------------------------------------------- update

    def update(self, pursuer: VehicleState, lead: VehicleState) -> Command:
        c = self.config
        now = pursuer.time
        if self._entered is None:
            self._entered = now
        pursuer_yaw = self._pursuer_yaw.update(pursuer)
        reference = lead.heading if self._road_heading is None else self._road_heading
        self._stability.update(
            now, pursuer_yaw, pursuer.sideslip(c.min_slip_speed),
            wrap_angle(pursuer.heading - reference),
        )
        longitudinal, lateral = self.lead_frame(pursuer, lead)
        in_state = now - self._entered
        self._track_lead_stopped(lead, now)
        if self.state in (State.CHASE, State.LINE_UP) and self.lead_pitted(now):
            self._go(State.STOP, now, "Lead stopped")

        if self.state is State.CHASE:
            distance = self.lineup_distance(pursuer, lead)
            if distance > c.chase_distance:
                return Command(ai_chase=True)
            self._go(State.LINE_UP, now, f"{distance:.1f} m from line-up point")

        if self.state is State.LINE_UP:
            distance = self.lineup_distance(pursuer, lead)
            if distance > c.chase_distance + c.chase_hysteresis:
                self._go(State.CHASE, now, f"{distance:.1f} m from line-up point")
                return Command(ai_chase=True)
            speed_error = pursuer.forward_speed - lead.forward_speed
            aligned = (
                lead.forward_speed >= c.min_lead_speed
                and abs(speed_error) <= c.speed_tolerance
                and abs(longitudinal + c.lineup_behind) <= c.longitudinal_tolerance
                and abs(lateral - c.side * c.lineup_lateral) <= c.lateral_tolerance
                and abs(wrap_angle(pursuer.heading - lead.heading)) <= c.heading_tolerance
            )
            if self._held(aligned, now, c.entry_hold_time):
                self._road_heading = lead.heading
                self.pit_attempts += 1
                self.contact_made = False
                self._go(State.PIT, now, f"aligned (attempt {self.pit_attempts})")
            else:
                gap_error = -c.lineup_behind - longitudinal   # >0: Pursuer too far back
                desired = lead.forward_speed + clamp(
                    c.gap_gain * gap_error, -c.max_closing_speed, c.max_closing_speed
                )
                throttle, brake = self._speed_command(pursuer.forward_speed, max(0.0, desired))
                steering = self._track_offset_line(
                    pursuer, lead, c.side * c.lineup_lateral, c.lookahead, c.max_steering
                )
                return Command(steering, throttle, brake)

        if self.state is State.PIT:
            if abs(lateral) <= c.contact_lateral and abs(longitudinal) <= c.contact_longitudinal:
                self.contact_made = True
            tag = "after contact" if self.contact_made else "no contact"
            warnings = self.loss_of_control_warnings()
            if warnings:
                self._go(State.RECOVER, now,
                         f"predicted loss of control: {', '.join(warnings)} ({tag})")
            elif abs(wrap_angle(lead.heading - self._road_heading)) > c.spin_heading:
                self._go(State.RECOVER, now, f"Lead spun out ({tag})")
            elif in_state >= c.pit_timeout:
                self._go(State.RECOVER, now, f"PIT timeout ({tag})")
            else:
                throttle = min(c.pit_max_throttle,
                               c.pit_throttle_start + c.pit_throttle_ramp * in_state)
                steering = self._track_offset_line(
                    pursuer, lead, c.side * c.pit_lateral, c.pit_lookahead, c.pit_max_steering
                )
                return Command(steering, throttle, 0.0)

        if self.state is State.RECOVER:
            heading_error = wrap_angle(pursuer.heading - self._road_heading)
            stable = (abs(pursuer_yaw) <= c.stable_yaw_rate
                      and abs(heading_error) <= c.stable_heading_error)
            settled = in_state >= c.recover_min_time and self._held(
                stable, now, c.stable_hold_time
            )
            if settled or in_state >= c.recover_timeout:
                why = "stable" if settled else "recover timeout"
                if self.lead_pitted(now):
                    self._go(State.STOP, now, f"{why}; Lead stopped")
                else:
                    self._go(State.LINE_UP, now, f"{why}; Lead still driving")
                    # Coast for this tick; LINE_UP speed control starts next update.
                    return Command(self._track_offset_line(
                        pursuer, lead, c.side * c.lineup_lateral, c.lookahead, c.max_steering
                    ))
            else:
                return Command(self._hold_heading(pursuer, pursuer_yaw), 0.0, c.recover_brake)

        # State.STOP
        parked = abs(pursuer.forward_speed) < c.stop_speed
        return Command(
            0.0 if parked else self._hold_heading(pursuer, pursuer_yaw),
            0.0,
            1.0,
            1.0 if parked else 0.0,
        )
