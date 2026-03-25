import os
import copy
import json
from pathlib import Path
from vvv.config import DEFAULT_SETTINGS


class SettingsManager:
    def __init__(self):
        if os.name == "nt":
            self.config_dir = Path(os.getenv("APPDATA")) / "VVV"
        else:
            self.config_dir = Path.home() / ".config" / "vvv"

        self.config_path = self.config_dir / ".vv_settings"
        self.data = copy.deepcopy(DEFAULT_SETTINGS)
        self.load()

    def _deep_update(self, default_dict, user_dict):
        for key, value in user_dict.items():
            if (
                isinstance(value, dict)
                and key in default_dict
                and isinstance(default_dict[key], dict)
            ):
                self._deep_update(default_dict[key], value)
            else:
                default_dict[key] = value

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    user_settings = json.load(f)
                    self._deep_update(self.data, user_settings)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def reset(self):
        self.data = copy.deepcopy(DEFAULT_SETTINGS)

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.data, f, indent=4)
        return str(self.config_path)
