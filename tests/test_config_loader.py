"""Tests for controller/configs/ parameter files."""

import math
import sys
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller import PitConfig  # noqa: E402
from controller.config_loader import CONFIG_DIR, load_pit_overrides  # noqa: E402


class ConfigFileTest(unittest.TestCase):
    def test_default_matches_code_defaults(self):
        loaded = PitConfig(**load_pit_overrides("default"))
        default = PitConfig()
        for f in fields(PitConfig):
            self.assertAlmostEqual(getattr(loaded, f.name), getattr(default, f.name),
                                   msg=f.name)

    def test_angles_are_degrees_in_file(self):
        self.assertAlmostEqual(load_pit_overrides("default")["pit_max_yaw_rate"],
                               math.radians(45))

    def test_every_config_file_loads(self):
        for path in CONFIG_DIR.glob("*.yaml"):
            PitConfig.for_vehicles(4.3, 1.8, 5.3, 2.0, **load_pit_overrides(path))

    def test_unknown_key_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "typo.yaml"
            path.write_text("pit_max_yawrate: 30\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pit_max_yawrate"):
                load_pit_overrides(path)

    def test_missing_config_lists_available(self):
        with self.assertRaisesRegex(FileNotFoundError, "default"):
            load_pit_overrides("does_not_exist")

    def test_geometry_knobs_drive_derived_values(self):
        c = PitConfig.for_vehicles(4.3, 1.8, 5.3, 2.0, pit_depth=1.0, lineup_gap=0.5)
        self.assertAlmostEqual(c.pit_lateral, 1.9 - 1.0)
        self.assertAlmostEqual(c.lineup_lateral, 1.9 + 0.5)


if __name__ == "__main__":
    unittest.main()
