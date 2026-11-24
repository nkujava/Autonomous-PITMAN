from math import hypot, isclose


DURATION_SECONDS = 20
STEPS_PER_SECOND = 60
CONTROL_INTERVAL_STEPS = 15
METRES_PER_SECOND_PER_MPH = 0.44704
TARGET_SPEED_MPH = 30
TARGET_SPEED = TARGET_SPEED_MPH * METRES_PER_SECOND_PER_MPH
MIN_FORWARD_DISTANCE = 20.0  # m


def run(beamng, scenario, trial):
    """Drive Lead forward for 20 simulated seconds with Pursuer as the player car."""
    vehicle_ids = ("Lead", "Pursuer")
    missing_ids = set(vehicle_ids).difference(scenario.vehicles)
    if missing_ids:
        raise RuntimeError(f"ATT trial {trial} is missing vehicles: {', '.join(sorted(missing_ids))}")
    lead = scenario.vehicles["Lead"]
    beamng.vehicles.switch("Pursuer")
    print(
        f"  Player vehicle: Pursuer. Lead target: {TARGET_SPEED_MPH} mph for {DURATION_SECONDS} s.",
        flush=True,
    )

    beamng.control.pause()
    beamng.settings.set_deterministic(steps_per_second=STEPS_PER_SECOND)
    resetting = False
    try:
        lead.set_shift_mode("arcade")
        lead.control(throttle=0.0, brake=0.0, parkingbrake=0.0)
        lead.sensors.poll("state")
        start_time = lead.state["time"]
        start_position = tuple(lead.state["pos"])
        start_direction = tuple(lead.state["dir"])
        right_x, right_y = start_direction[1], -start_direction[0]

        simulation_steps = DURATION_SECONDS * STEPS_PER_SECOND
        speed_integral = 0.0
        for _ in range(0, simulation_steps, CONTROL_INTERVAL_STEPS):
            state = lead.state
            position = state["pos"]
            direction = state["dir"]
            lateral_offset = (
                (position[0] - start_position[0]) * right_x
                + (position[1] - start_position[1]) * right_y
            )
            heading_error = direction[0] * right_x + direction[1] * right_y
            steering = max(-0.15, min(0.15, -0.05 * lateral_offset - 0.9 * heading_error))
            forward_speed = sum(v * d for v, d in zip(state["vel"], direction))
            speed_error = TARGET_SPEED - forward_speed
            speed_integral = max(-0.25, min(0.25, speed_integral + 0.01 * speed_error))
            demand = 0.22 * speed_error + speed_integral
            lead.control(
                steering=steering,
                throttle=min(0.6, max(0.0, demand)),
                brake=min(0.4, max(0.0, -demand)),
                parkingbrake=0.0,
            )
            beamng.control.step(CONTROL_INTERVAL_STEPS)
            resetting = beamng.control.queue_lua_command(
                """
                local scenario = scenario_scenarios and scenario_scenarios.getScenario()
                return scenario ~= nil and (
                    scenario.state == "restart" or scenario.state == "pre-start"
                    or scenario.state == "pre-running"
                )
                """,
                response=True,
            ) == "true"
            if resetting:
                return
            lead.sensors.poll("state")

        elapsed = lead.state["time"] - start_time
        distance = sum(
            (end - start) * direction
            for end, start, direction in zip(lead.state["pos"], start_position, start_direction)
        )
        speed_mph = hypot(*lead.state["vel"]) / METRES_PER_SECOND_PER_MPH
        print(
            f"  Lead: {distance:.1f} m forward in {elapsed:.2f} s, ending at {speed_mph:.1f} mph.",
            flush=True,
        )
        if not isclose(elapsed, DURATION_SECONDS, abs_tol=1 / STEPS_PER_SECOND):
            raise RuntimeError(f"Lead recorded {elapsed:.3f} s, expected {DURATION_SECONDS} s.")
        if distance < MIN_FORWARD_DISTANCE:
            raise RuntimeError(f"Lead drove less than {MIN_FORWARD_DISTANCE:g} m forward.")
        if not isclose(speed_mph, TARGET_SPEED_MPH, abs_tol=2.0):
            raise RuntimeError(f"Lead finished at {speed_mph:.1f} mph, expected about {TARGET_SPEED_MPH} mph.")
    finally:
        if not resetting:
            lead.control(steering=0.0, throttle=0.0, brake=0.0, parkingbrake=1.0)
        beamng.settings.set_nondeterministic()
        beamng.settings.remove_step_limit()
        beamng.control.resume()
