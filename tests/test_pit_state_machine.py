"""Offline tests for controller.PitStateMachine (no simulator needed).

Run from the repository root:  py -V:3.12 -m unittest discover tests
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller import PitConfig, PitStateMachine, State, VehicleState  # noqa: E402

SPEED = 10.0  # m/s, both cars heading +y


def car(t, x, y, heading=math.pi / 2, speed=SPEED):
    hx, hy = math.cos(heading), math.sin(heading)
    return VehicleState(t, x, y, hx * speed, hy * speed, hx, hy)


def lead_at(t, heading=math.pi / 2, speed=SPEED):
    return car(t, 0.0, SPEED * t, heading, speed)


def run_until(machine, pursuer_fn, lead_fn, t_end, dt=0.05, t0=0.0):
    t = t0
    while t <= t_end + 1e-9:
        machine.update(pursuer_fn(t), lead_fn(t))
        t += dt
    return t


class LeadFrameTest(unittest.TestCase):
    def test_right_side_is_positive_lateral(self):
        m = PitStateMachine()
        longitudinal, lateral = m.lead_frame(car(0, 2.4, -3.5), lead_at(0))
        self.assertAlmostEqual(longitudinal, -3.5)
        self.assertAlmostEqual(lateral, 2.4)

    def test_line_up_steers_toward_configured_side(self):
        m = PitStateMachine()  # side = +1 (right)
        cmd = m.update(car(0, 0.0, -6.0), lead_at(0))  # ~3.5 m from line-up point
        self.assertIs(m.state, State.LINE_UP)
        self.assertGreater(cmd.steering, 0.0)  # positive = right
        self.assertGreater(cmd.throttle, 0.0)  # behind the line-up point -> speed up


class VehicleGeometryTest(unittest.TestCase):
    def test_compact_lead_and_fullsize_pursuer(self):
        c = PitConfig.for_vehicles(4.3, 1.8, 5.3, 2.0)  # FCV lead, Grand Marshal pursuer
        self.assertAlmostEqual(c.lineup_behind, 0.3 * 4.3 + 2.65)
        self.assertAlmostEqual(c.lineup_lateral, 1.9 + 0.3)
        self.assertGreater(c.lineup_lateral, c.contact_lateral)  # no contact while lining up
        self.assertLess(c.pit_lateral, c.contact_lateral)        # PIT target forces contact

    def test_overrides_win(self):
        self.assertEqual(PitConfig.for_vehicles(4, 2, 5, 2, side=-1).side, -1)


class TransitionTest(unittest.TestCase):
    def aligned(self, t):
        c = self.machine.config
        return car(t, c.lineup_lateral, SPEED * t - c.lineup_behind)

    def setUp(self):
        self.machine = PitStateMachine()

    def run_while(self, state, pursuer_fn, lead_fn, t0, t_max):
        """Step while the machine is in ``state``; return the next time."""
        t = t0
        while self.machine.state is state and t < t_max:
            self.machine.update(pursuer_fn(t), lead_fn(t))
            t += 0.05
        return t

    def enter_pit(self):
        t = 0.0
        while self.machine.state is not State.PIT and t < 2.0:
            self.machine.update(self.aligned(t), lead_at(t))
            t += 0.05
        self.assertIs(self.machine.state, State.PIT)
        return t

    def enter_recover(self):
        """PIT, then Pursuer starts yawing left at 40 deg/s -> predicted loss of control."""
        t0 = self.enter_pit()
        spinning = lambda t: car(t, 1.5, SPEED * t - 3.0,  # noqa: E731
                                 heading=math.pi / 2 + math.radians(40) * (t - t0))
        t = self.run_while(State.PIT, spinning, lead_at, t0, t0 + 0.5)
        self.assertIs(self.machine.state, State.RECOVER)
        self.assertIn("predicted loss of control", self.machine.transitions[-1].reason)
        self.assertIn("after contact", self.machine.transitions[-1].reason)
        return t

    def test_pit_keeps_pushing_through_contact(self):
        t0 = self.enter_pit()
        contact = lambda t: car(t, 1.5, SPEED * t - 3.0)  # noqa: E731
        first = self.machine.update(contact(t0), lead_at(t0))
        run_until(self.machine, contact, lead_at, t0 + 1.5, t0=t0 + 0.05)
        later = self.machine.update(contact(t0 + 1.55), lead_at(t0 + 1.55))
        self.assertIs(self.machine.state, State.PIT)  # stable -> no exit on contact
        self.assertTrue(self.machine.contact_made)
        self.assertGreater(later.throttle, first.throttle)  # throttle ramps up
        self.assertEqual(later.brake, 0.0)

    def test_predictor_extrapolates_before_limit_is_reached(self):
        # Yaw rate is still below the pit_max_yaw_rate limit but rising fast.
        t0 = self.enter_pit()
        rate = lambda t: math.radians(60) * (t - t0)  # noqa: E731
        heading = lambda t: math.pi / 2 + 0.5 * math.radians(60) * (t - t0) ** 2  # noqa: E731
        ramp = lambda t: car(t, 1.5, SPEED * t - 3.0, heading=heading(t))  # noqa: E731
        t = t0
        while self.machine.state is State.PIT:
            self.machine.update(ramp(t), lead_at(t))
            t += 0.05
        self.assertIn("yaw rate", self.machine.transitions[-1].reason)
        self.assertLess(rate(t - 0.05), self.machine.config.pit_max_yaw_rate)

    def test_lead_spin_ends_pit(self):
        t0 = self.enter_pit()
        spun = lambda t: lead_at(t, heading=math.pi)  # noqa: E731
        run_until(self.machine, self.aligned, spun, t0 + 0.2, t0=t0)
        self.assertIs(self.machine.state, State.RECOVER)
        self.assertIn("Lead spun out", self.machine.transitions[-1].reason)

    def test_far_away_uses_chase_ai(self):
        far = lambda t: car(t, 0.0, SPEED * t - 20.0)  # noqa: E731
        run_until(self.machine, far, lead_at, 2.0)
        self.assertIs(self.machine.state, State.CHASE)
        self.assertTrue(self.machine.update(far(2.05), lead_at(2.05)).ai_chase)

    def test_chase_hands_over_within_chase_distance(self):
        c = self.machine.config
        near = lambda t: car(t, c.lineup_lateral, SPEED * t - c.lineup_behind - 4.0)  # noqa: E731
        cmd = self.machine.update(near(0), lead_at(0))
        self.assertIs(self.machine.state, State.LINE_UP)
        self.assertFalse(cmd.ai_chase)
        self.assertEqual(self.machine.transitions[-1].source, State.CHASE)

    def test_line_up_returns_to_chase_only_past_hysteresis(self):
        c = self.machine.config
        behind = lambda gap: (lambda t: car(t, c.lineup_lateral,  # noqa: E731
                                            SPEED * t - c.lineup_behind - gap))
        self.machine.update(behind(0.0)(0), lead_at(0))
        self.assertIs(self.machine.state, State.LINE_UP)
        self.machine.update(behind(c.chase_distance + 1.0)(0.05), lead_at(0.05))
        self.assertIs(self.machine.state, State.LINE_UP)  # inside the hysteresis band
        cmd = self.machine.update(
            behind(c.chase_distance + c.chase_hysteresis + 1.0)(0.1), lead_at(0.1))
        self.assertIs(self.machine.state, State.CHASE)
        self.assertTrue(cmd.ai_chase)

    def test_alignment_must_hold_before_pit(self):
        hold = self.machine.config.entry_hold_time
        t = run_until(self.machine, self.aligned, lead_at, 0.5 * hold)
        self.assertIs(self.machine.state, State.LINE_UP)  # held < entry_hold_time
        run_until(self.machine, self.aligned, lead_at, hold + 0.1, t0=t)
        self.assertIs(self.machine.state, State.PIT)

    def test_pit_timeout_goes_to_recover(self):
        t0 = self.enter_pit()
        limit = t0 + self.machine.config.pit_timeout + 0.5
        self.run_while(State.PIT, self.aligned, lead_at, t0, limit)
        self.assertIs(self.machine.state, State.RECOVER)
        self.assertIn("PIT timeout", self.machine.transitions[-1].reason)

    def test_recover_to_line_up_when_lead_still_driving(self):
        t0 = self.enter_recover()
        self.run_while(State.RECOVER, self.aligned, lead_at, t0, t0 + 10.0)
        self.assertEqual(self.machine.transitions[-1].target, State.LINE_UP)
        self.assertIn("Lead still driving", self.machine.transitions[-1].reason)

    def test_spun_but_moving_lead_is_not_pitted(self):
        t0 = self.enter_recover()
        spun = lambda t: lead_at(t, heading=math.pi, speed=3.0)  # noqa: E731
        self.run_while(State.RECOVER, self.aligned, spun, t0, t0 + 10.0)
        self.assertEqual(self.machine.transitions[-1].target, State.LINE_UP)
        self.assertFalse(self.machine.done)

    def test_recover_to_stop_when_lead_stopped(self):
        t0 = self.enter_recover()
        stopped = lambda t: lead_at(t, heading=math.pi, speed=0.0)  # noqa: E731
        run_until(self.machine, self.aligned, stopped, t0 + 2.0, t0=t0)
        self.assertIs(self.machine.state, State.STOP)
        self.assertIn("Lead stopped", self.machine.transitions[-1].reason)

    def test_lead_stopping_after_attempt_ends_from_line_up(self):
        t0 = self.enter_recover()
        self.run_while(State.RECOVER, self.aligned, lead_at, t0, t0 + 10.0)
        self.assertIs(self.machine.state, State.LINE_UP)
        t1 = self.machine.transitions[-1].time + 0.05
        stopped = lambda t: lead_at(t, speed=0.0)  # noqa: E731
        run_until(self.machine, self.aligned, stopped, t1 + 1.0, t0=t1)
        self.assertIs(self.machine.state, State.STOP)

    def test_stationary_lead_before_any_attempt_is_not_pitted(self):
        stopped = lambda t: lead_at(t, speed=0.0)  # noqa: E731
        run_until(self.machine, self.aligned, stopped, 3.0)
        self.assertEqual(self.machine.pit_attempts, 0)
        self.assertIs(self.machine.state, State.LINE_UP)  # min_lead_speed blocks PIT, no STOP

    def test_stop_parks_when_slow(self):
        t0 = self.enter_recover()
        spun = lambda t: lead_at(t, heading=math.pi, speed=0.0)  # noqa: E731
        run_until(self.machine, self.aligned, spun, t0 + 2.0, t0=t0)
        cmd = self.machine.update(car(t0 + 3, 2.4, 0.0, speed=0.1), spun(t0 + 3))
        self.assertEqual((cmd.brake, cmd.parkingbrake), (1.0, 1.0))


if __name__ == "__main__":
    unittest.main()
