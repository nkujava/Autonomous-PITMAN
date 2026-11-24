def run(beamng, scenario, trial):
    """Check that both ATT vehicles loaded and report their spawn positions."""
    expected_ids = ("Lead", "Pursuer")
    missing_ids = set(expected_ids).difference(scenario.vehicles)
    if missing_ids:
        raise RuntimeError(f"ATT trial {trial} is missing vehicles: {', '.join(sorted(missing_ids))}")

    for vehicle_id in expected_ids:
        vehicle = scenario.vehicles[vehicle_id]
        vehicle.sensors.poll("state")
        position = vehicle.state["pos"]
        print(f"  {vehicle_id} position: {tuple(position)}", flush=True)
