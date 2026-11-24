# jv_hw_1: Johnson Valley highway

**Map:** `johnson_valley`. **Cars:** `pursue` (Gavril Grand Marshal police) and `lead` (Cherrier FCV Ardente 190d DCT), saved in [`jv_hw_1.prefab.json`](jv_hw_1.prefab.json).

```powershell
py -V:3.12 Scripts/run_trials.py Configs/jv_hw_1_pit.yaml
```

- **`manual: n`:** [`drive_to_southern_highway.py`](drive_to_southern_highway.py) sends lead's AI toward Southern Highway at up to 60 mph, staying in lane. The simulator is stepped deterministically.
- **`manual: y`:** you drive lead in real time.
- **Both modes:** the PIT controller drives pursue. Press **R** to restart the trial.

[`pit.py`](pit.py) provides `make_run()`, which the other Johnson Valley and city scenarios reuse with their own lead AI.
