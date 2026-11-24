# jv_hw_2: Johnson Valley highway, faster police car

Same map, spawn points and route as [`jv_hw_1`](../jv_hw_1/README.md), with different cars:

| | Car | Stock figures |
|---|---|---|
| `pursue` | ETK 800 854 police (`etk800/854_police_A`) | AWD, 1696 kg, 0–60 mph 6.1 s, 151 mph |
| `lead` | Ibishu Covet DXi auto (`covet/DXi_A`) | FWD, 1046 kg, 0–60 mph 11.1 s, 114 mph |

```powershell
py -V:3.12 Scripts/run_trials.py Configs/jv_hw_2_pit.yaml
```

With `manual: n`, lead's AI drives flat out: route speed 450 mph in `set` mode, so it holds full throttle. `manual: y` and **R** work as in `jv_hw_1`.
