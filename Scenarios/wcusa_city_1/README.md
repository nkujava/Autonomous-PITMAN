# wcusa_city_1: West Coast USA city streets

**Map:** `west_coast_usa`. **Cars:** the same as [`jv_hw_2`](../jv_hw_2/README.md): ETK 800 police as `pursue`, Ibishu Covet as `lead`.

- **Start:** right-hand lane of the straight street south-east of the Chinatown intersection, with pursue 15 m behind lead.
- **`manual: n`:** lead's AI flees from pursue in `limit` mode with no fixed cap. There's no fixed route, so each run takes different streets.
- **`manual: y` and R:** work as in `jv_hw_1`.

There's no config in `Configs/` yet. To run it, copy `Configs/jv_hw_2_pit.yaml` and set `scenario: wcusa_city_1`, `level: west_coast_usa` and `prefab: wcusa_city_1.prefab.json`.

The [prefab](wcusa_city_1.prefab.json) was generated from the map's road data, not saved in the World Editor. If a car spawns badly, re-place it in the editor and re-save.
