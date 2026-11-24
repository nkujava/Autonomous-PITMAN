import argparse
import inspect
import json
import os
import re
import runpy
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

import yaml
from beamngpy import BeamNGpy, Scenario


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PIPELINE = ["cleanup", "setup", "run"]
PIT_CONFIG_DIR = ROOT / "controller" / "configs"


@dataclass(frozen=True)
class TrialConfig:
    scenario: str
    trials: int
    pipeline: list[str]
    level: str
    prefab: Path
    player_vehicle: str
    script: Path
    replay_on_reset: bool = False
    pit_config: Path | None = None
    manual: bool | None = None
    manual_vehicle: str | None = None

    @property
    def driven_vehicle(self) -> str:
        """The vehicle the player sits in: manual_vehicle when manual: y."""
        return self.manual_vehicle if self.manual and self.manual_vehicle else self.player_vehicle


def scenario_file(directory: Path, value: str) -> Path:
    path = (directory / value).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError(f"Expected an existing file in {directory}, got {value!r}.")
    return path


def pit_config_file(value) -> Path:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError("pit_config must be a file name in controller/configs/, such as default.")
    name = value if value.endswith((".yaml", ".yml")) else f"{value}.yaml"
    path = PIT_CONFIG_DIR / name
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in PIT_CONFIG_DIR.glob("*.yaml"))) or "none"
        raise ValueError(f"pit_config {value!r} not found in controller/configs/. Available: {available}.")
    return path


def yes_no(key: str, value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("y", "yes", "n", "no"):
        return value.strip().lower().startswith("y")
    raise ValueError(f"{key} must be y or n.")


def read_config(path: Path) -> TrialConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("The YAML config must contain a mapping.")

    for key in ("scenario", "level"):
        value = data.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_-]+", value):
            raise ValueError(f"{key} must be a lowercase scenario or level identifier.")
    for key in ("prefab", "player_vehicle", "script"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"{key} must be a nonempty string.")
    if type(data.get("trials")) is not int or data["trials"] < 1:
        raise ValueError("trials must be a positive integer.")
    if data.get("pipeline") != PIPELINE:
        raise ValueError("pipeline must list cleanup, setup, and run in that order.")
    replay_on_reset = data.get("replay_on_reset", False)
    if not isinstance(replay_on_reset, bool):
        raise ValueError("replay_on_reset must be true or false.")

    pit_config = pit_config_file(data["pit_config"]) if "pit_config" in data else None
    if "manuel" in data:
        raise ValueError("Unknown key 'manuel'; did you mean 'manual'?")
    manual = yes_no("manual", data["manual"]) if "manual" in data else None
    manual_vehicle = data.get("manual_vehicle")
    if manual_vehicle is not None and (not isinstance(manual_vehicle, str) or not manual_vehicle.strip()):
        raise ValueError("manual_vehicle must be a vehicle name from the prefab, such as lead.")
    if manual and manual_vehicle is None:
        raise ValueError("manual: y needs manual_vehicle: the vehicle you want to drive, such as lead.")

    directory = ROOT / "Scenarios" / data["scenario"]
    prefab = scenario_file(directory, data["prefab"])
    script = scenario_file(directory, data["script"])
    if not prefab.name.endswith((".prefab", ".prefab.json")) or script.suffix != ".py":
        raise ValueError("Expected a BeamNG prefab and a Python trial script.")

    return TrialConfig(
        data["scenario"], data["trials"], data["pipeline"], data["level"],
        prefab, data["player_vehicle"], script, replay_on_reset=replay_on_reset,
        pit_config=pit_config, manual=manual, manual_vehicle=manual_vehicle,
    )


def stage_scenario(user_folder: Path, config: TrialConfig, name: str) -> str:
    relative_folder = Path("levels") / config.level / "scenarios" / name
    folder = user_folder / relative_folder
    folder.mkdir(parents=True)
    # Keep the filename distinct from the scenario name to avoid auto-discovery
    # loading the same prefab a second time.
    prefab_suffix = ".prefab.json" if config.prefab.name.endswith(".json") else ".prefab"
    prefab_name = f"setup{prefab_suffix}"
    shutil.copyfile(config.prefab, folder / prefab_name)

    scenario_info = {
        "name": config.scenario,
        "scenarioName": name,
        "forceNoCountDown": True,
        "vehicles": {
            config.driven_vehicle: {"playerUsable": True, "startFocus": True},
        },
        "prefabs": [(relative_folder / prefab_name).as_posix()],
    }
    scenario_path = relative_folder / f"{name}.json"
    (user_folder / scenario_path).write_text(
        json.dumps([scenario_info], indent=2), encoding="utf-8"
    )
    return f"/{scenario_path.as_posix()}"


def run_scenario_script(
    beamng: BeamNGpy, config: TrialConfig, scenario: Scenario, trial: int, name: str
) -> None:
    run = runpy.run_path(str(config.script)).get("run")
    if not callable(run):
        raise ValueError(f"{config.script} must define run(beamng, scenario, trial).")
    accepted = inspect.signature(run).parameters
    options = {}
    if config.pit_config is not None:
        options["pit_config"] = str(config.pit_config)
        print(f"  PIT config selected by trial config: {config.pit_config.name}", flush=True)
    if config.manual is not None:
        options["manual"] = config.manual
        print(f"  Manual mode: {'y' if config.manual else 'n'}; "
              f"player vehicle: {config.driven_vehicle}", flush=True)
    for key in options:
        if key not in accepted:
            raise ValueError(f"{config.script.name} does not accept {key}; remove it from the config.")
    # Optional: lets a long-running script stop early when the player presses R.
    if config.replay_on_reset and "reset_requested" in accepted:
        options["reset_requested"] = lambda: reset_is_ready(beamng, name)
    run(beamng, scenario, trial, **options)


def run_pipeline(
    beamng: BeamNGpy, config: TrialConfig, name: str, scenario_path: str
) -> Scenario:
    scenario = None
    for trial in range(1, config.trials + 1):
        for step in config.pipeline:
            print(f"[{config.scenario} {trial}/{config.trials}] {step}", flush=True)
            if step == "cleanup":
                if scenario is not None:
                    beamng.scenario.stop()
                    scenario = None
            elif step == "setup":
                scenario = Scenario(config.level, name, path=scenario_path)
                beamng.scenario.load(scenario, precompile_shaders=False)
                beamng.scenario.start()
            elif step == "run":
                run_scenario_script(beamng, config, scenario, trial, name)
    print(f"[{config.scenario}] Completed {config.trials} trial(s).", flush=True)
    return scenario


def reset_is_ready(beamng: BeamNGpy, name: str) -> bool:
    # Wait until the native restart has reset the vehicles and opened the start state.
    command = f"""
        local scenario = scenario_scenarios and scenario_scenarios.getScenario()
        return scenario ~= nil and scenario.scenarioName == {json.dumps(name)} and (
            scenario.state == "pre-running" or
            (scenario.state == "pre-start" and scenario.preStartStage == 2)
        )
    """
    return beamng.control.queue_lua_command(command, response=True) == "true"


def find_beamng_home(override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    if os.getenv("BNG_HOME"):
        return Path(os.environ["BNG_HOME"]).resolve()
    installs = [path for path in ROOT.parent.glob("BeamNG.tech.v*") if path.is_dir()]
    if len(installs) == 1:
        return installs[0]
    raise ValueError("Set BNG_HOME or pass --beamng-home with the BeamNG.tech install path.")


def run_trials(config: TrialConfig, home: Path, headless: bool) -> None:
    with socket.socket() as listener:
        listener.bind((HOST, 0))
        port = listener.getsockname()[1]

    with TemporaryDirectory(prefix="pitman-") as temp:
        sandbox = Path(temp).resolve()
        beamng = BeamNGpy(
            HOST, port, home=str(home), user=str(sandbox), headless=headless, socket_timeout=240
        )
        try:
            beamng.open()
            if beamng.process is None:
                raise RuntimeError("Expected a dedicated BeamNG.tech process.")
            user_folder = Path(beamng.user_with_version).resolve()
            if not user_folder.is_relative_to(sandbox):
                beamng.disconnect()
                raise RuntimeError(f"Simulator reported an unexpected user folder: {user_folder}")

            name = f"pitman_{config.scenario}"
            scenario_path = stage_scenario(user_folder, config, name)
            scenario = run_pipeline(beamng, config, name, scenario_path)
            if config.replay_on_reset:
                print("Press R in BeamNG.tech to reset and replay the final trial.", flush=True)
            print("BeamNG.tech is still open. Press Ctrl+C in this terminal to close it.", flush=True)
            while beamng.process.poll() is None:
                if config.replay_on_reset and reset_is_ready(beamng, name):
                    print(f"[{config.scenario}] Replaying after reset.", flush=True)
                    beamng.scenario.start()
                    for vehicle in scenario.vehicles.values():
                        vehicle.disconnect()
                    scenario.connect(beamng)
                    run_scenario_script(beamng, config, scenario, config.trials, name)
                sleep(0.25)
        except KeyboardInterrupt:
            print("\nClosing BeamNG.tech and cleaning up.", flush=True)
        finally:
            if beamng.process is not None:
                beamng.close()
            else:
                beamng.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BeamNG.tech trials from a YAML config.")
    parser.add_argument("config", type=Path, help="YAML file, such as Configs/att_drive_forward.yaml")
    parser.add_argument("--beamng-home", type=Path, help="BeamNG.tech installation directory")
    parser.add_argument("--headless", action="store_true", help="Run without a simulator window")
    args = parser.parse_args()

    try:
        config = read_config(args.config)
        home = find_beamng_home(args.beamng_home)
    except (ValueError, OSError, yaml.YAMLError) as error:
        parser.error(str(error))

    run_trials(config, home, args.headless)


if __name__ == "__main__":
    main()
