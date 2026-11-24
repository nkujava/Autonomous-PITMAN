# Autonomous-PITMAN

BeamNG.tech simulation of an autonomous police car performing a PIT maneuver and recovering afterwards. All vehicle state comes from simulator ground truth; there's no perception.

## Setup and run

From the repository root:

```powershell
py -V:3.12 -m pip install -r requirements.txt
py -V:3.12 Scripts/run_trials.py Configs/jv_hw_2_pit.yaml
py -V:3.12 -m unittest discover tests          # offline tests, no simulator needed
```
## PIT controller (`controller/`)

`pit_state_machine.py` drives the police car through these states:

`CHASE` → `LINE_UP` → `PIT` → `RECOVER` → `LINE_UP` (lead still moving) or `STOP` (lead stopped)

- **CHASE:** BeamNG's chase AI drives while the police car is more than 5 m from the line-up point. It returns only after 1 s more than 15 m back, and not within 5 s of a collision with lead (`chase_cooldown`).
- **LINE_UP:** matches lead's speed beside its rear quarter.
- **PIT:** steers into lead with rising throttle until it predicts its own loss of control.
- **RECOVER:** damps yaw and matches lead's speed. While lead is under 10 mph it never accelerates; it brakes and waits until lead passes 12 mph again.
- **STOP:** ends once lead's speed is about 0 after at least one PIT attempt.

All tunable parameters are in `controller/configs/*.yaml`, with angles in degrees. `pit_trial.py` runs the simulator loop.

## Scenarios

| Scenario | Map | Pursue vs. lead | Config |
|---|---|---|---|
| [`jv_hw_1`](Scenarios/jv_hw_1/README.md) | Johnson Valley | Grand Marshal police vs. Cherrier FCV | `jv_hw_1_pit.yaml` |
| [`jv_hw_2`](Scenarios/jv_hw_2/README.md) | Johnson Valley | ETK 800 police vs. Ibishu Covet | `jv_hw_2_pit.yaml` |

To run a scenario that has no config, copy `Configs/jv_hw_2_pit.yaml` and change `scenario`, `level` and `prefab`.
