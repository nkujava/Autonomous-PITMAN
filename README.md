# Autonomous-PITMAN

BeamNG.tech simulation of an autonomous police car performing a PIT maneuver and recovering afterwards. All vehicle state comes from simulator ground truth; there's no perception.

## Setup and run

From the repository root:

```powershell
py -V:3.12 -m pip install -r requirements.txt
py -V:3.12 Scripts/run_trials.py Configs/jv_hw_2_pit.yaml
py -V:3.12 -m unittest discover tests          # offline tests, no simulator needed
```

The runner finds BeamNG.tech through `--beamng-home`, `BNG_HOME`, or a single `BeamNG.tech.v*` folder next to this repo. Add `--headless` to run without a window. Press **Ctrl+C** to close the simulator.

## Trial configs (`Configs/*.yaml`)

| Key | Meaning |
|---|---|
| `scenario` | Folder under `Scenarios/` holding the prefab and script |
| `level` | BeamNG map, e.g. `johnson_valley` |
| `prefab`, `script` | Files in that scenario folder |
| `player_vehicle` | Car you sit in when `manual: n` |
| `trials` | Number of back-to-back runs. Each reloads the map and prefab, then calls the script's `run()` |
| `replay_on_reset` | `true`: pressing **R** restarts the current trial from the spawn points |
| `pit_config` | Controller parameter file in `controller/configs/` (`default`, `georgia_state_police`) |
| `manual` | `n`: BeamNG AI drives lead. `y`: you drive `manual_vehicle` in real time |
| `pipeline` | Always `[cleanup, setup, run]` |

## PIT controller (`controller/`)

`pit_state_machine.py` drives the police car through these states:

`CHASE` → `LINE_UP` → `PIT` → `RECOVER` → `LINE_UP` (lead still moving) or `STOP` (lead stopped)

- **CHASE:** BeamNG's chase AI drives while the police car is more than 5 m from the line-up point.
- **LINE_UP:** matches lead's speed beside its rear quarter.
- **PIT:** steers into lead with rising throttle until it predicts its own loss of control.
- **RECOVER:** brakes and damps yaw.
- **STOP:** ends once lead's speed is about 0 after at least one PIT attempt.

All tunable parameters are in `controller/configs/*.yaml`, with angles in degrees. `pit_trial.py` runs the simulator loop.

## Scenarios

| Scenario | Map | Pursue vs. lead | Config |
|---|---|---|---|
| [`att`](Scenarios/att/README.md) | Automation Test Track | Grand Marshal police vs. Grand Marshal | none |
| [`jv_hw_1`](Scenarios/jv_hw_1/README.md) | Johnson Valley | Grand Marshal police vs. Cherrier FCV | `jv_hw_1_pit.yaml` |
| [`jv_hw_2`](Scenarios/jv_hw_2/README.md) | Johnson Valley | ETK 800 police vs. Ibishu Covet | `jv_hw_2_pit.yaml` |
| [`wcusa_city_1`](Scenarios/wcusa_city_1/README.md) | West Coast USA | ETK 800 police vs. Ibishu Covet | none |

To run a scenario that has no config, copy `Configs/jv_hw_2_pit.yaml` and change `scenario`, `level` and `prefab`.
