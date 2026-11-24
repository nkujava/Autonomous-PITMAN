# att: Automation Test Track

**Map:** `automation_test_track`. **Cars:** `Pursuer` (Grand Marshal police) and `Lead` (Grand Marshal luxe), saved in [`pursuit_setup_att.prefab.json`](pursuit_setup_att.prefab.json).

| Script | What it does |
|---|---|
| [`run.py`](run.py) | Checks both cars spawned and prints their positions |
| [`drive_forward.py`](drive_forward.py) | Lead drives straight at 30 mph for 20 s, then reports distance and speed |
| [`pit.py`](pit.py) | Lead holds 25 mph straight ahead; the PIT controller drives Pursuer |

There's no config in `Configs/` for these scripts. To run one, create a config with `scenario: att`, `level: automation_test_track`, `prefab: pursuit_setup_att.prefab.json`, `player_vehicle: Pursuer` and the script.

**Manual load:** copy the prefab to `%LOCALAPPDATA%\BeamNG\BeamNG.tech\current\levels\automation_test_track\` and load the map. Then in the World Editor (**F11**), open **Window → Asset Browser** and use **Spawn prefab at origin**.
