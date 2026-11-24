SPEED_LIMIT_MPH = 60
METRES_PER_SECOND_PER_MPH = 0.44704

# Southern Highway is a spawn point. Its closest road segment supplies the AI waypoint.
FIND_WAYPOINT = """
local spawn = scenetree.findObject("spawn_highway_south")
if not spawn then return "" end

local position = spawn:getPosition()
local first, second = map.findClosestRoad(position)
if not first or not second then return "" end

local nodes = map.getMap().nodes
if nodes[first].pos:squaredDistance(position) <= nodes[second].pos:squaredDistance(position) then
    return first
end
return second
"""


def run(beamng, scenario, trial, speed_limit_mph=SPEED_LIMIT_MPH, speed_mode="limit"):
    """Start Lead's route to Southern Highway and leave Pursue under player control.

    ``speed_limit_mph`` is the AI's route speed. ``speed_mode`` is BeamNG's
    route speed mode: "limit" drives at up to that speed as the AI sees fit;
    "set" tries to hold it at all times (jv_hw_2 uses this with a speed far
    above any car's top speed, i.e. flat out).
    """
    missing = {"lead", "pursue"}.difference(scenario.vehicles)
    if missing:
        raise RuntimeError(f"Johnson Valley trial {trial} is missing vehicles: {', '.join(sorted(missing))}")

    waypoint = beamng.control.queue_lua_command(FIND_WAYPOINT, response=True)
    if not waypoint:
        raise RuntimeError("No road waypoint found for the Southern Highway spawn in Johnson Valley.")

    lead = scenario.vehicles["lead"]
    beamng.vehicles.switch("pursue")
    lead.set_shift_mode("arcade")
    lead.ai.drive_using_waypoints(
        [waypoint],
        route_speed=speed_limit_mph * METRES_PER_SECOND_PER_MPH,
        route_speed_mode=speed_mode,
        drive_in_lane=True,
        avoid_cars=True,
    )
    print(f"  Player vehicle: pursue. Lead is driving to Southern Highway ({waypoint}) at {'up to ' if speed_mode == 'limit' else ''}{speed_limit_mph:g} mph ({speed_mode}).", flush=True)
