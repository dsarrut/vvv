import os
import copy
import json
from pathlib import Path
from vvv.config import DEFAULT_SETTINGS
from vvv.utils import get_config_dir, read_json_or_keep_aside, write_json_atomic
import logging

logger = logging.getLogger(__name__)


class SettingsManager:
    def __init__(self):
        self.config_dir = get_config_dir()
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
        user_settings = read_json_or_keep_aside(self.config_path, "settings")
        if isinstance(user_settings, dict):
            self._deep_update(self.data, user_settings)

    def reset(self):
        self.data = copy.deepcopy(DEFAULT_SETTINGS)

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.config_path, self.data)
        return str(self.config_path)
