import os
import json
import numpy as np
from pathlib import Path


class HistoryManager:
    def __init__(self):
        appdata = os.getenv("APPDATA")
        if os.name == "nt" and appdata:
            self.config_dir = Path(appdata) / "VVV"
        else:
            self.config_dir = Path.home() / ".config" / "vvv"

        self.history_path = self.config_dir / "history.json"
        self.data = {}
        self.max_history_files = 100  # Enforce limit
        self.load()

    def _portable_key(self, path):
        """Converts an absolute path to a portable ~ path."""
        home = os.path.expanduser("~")
        abs_p = os.path.abspath(path)
        if abs_p.startswith(home):
            return abs_p.replace(home, "~", 1)
        return abs_p

    def load(self):
        if self.history_path.exists():
            try:
                with open(self.history_path, "r") as f:
                    self.data = json.load(f)
            except Exception as e:
                pass

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w") as f:
            json.dump(self.data, f, indent=4)

    def save_image_state(self, controller, vs_id):
        vs = controller.view_states[vs_id]
        vol = controller.volumes[vs_id]
        primary_path = vol.file_paths[0]
        key = self._portable_key(primary_path)

        # Remove the key if it exists so we can push it to the "end" of the dictionary (LRU logic)
        if key in self.data:
            del self.data[key]

        # Only save intrinsic physical and display state. No Overlays or ROIs.
        self.data[key] = {
            "shape3d": [int(x) for x in vol.shape3d],
            "spacing": [float(x) for x in vol.spacing],
            "origin": [float(x) for x in vol.origin],
            "camera": vs.camera.to_dict(),
            "display": vs.display.to_dict(),
            "sync_group": vs.sync_group,
            "sync_wl_group": getattr(vs, "sync_wl_group", 0),
        }

        # Enforce the 100 files limit by deleting the oldest item(s) at the front of the dict
        while len(self.data) > self.max_history_files:
            oldest_key = next(iter(self.data))
            del self.data[oldest_key]

        self.save()

    def get_image_state(self, volume):
        primary_path = volume.file_paths[0]
        key = self._portable_key(primary_path)

        if key not in self.data:
            return None

        entry = self.data[key]

        # Strict Geometry Validation (If the image was cropped/resampled externally, drop history)
        if entry.get("shape3d") != list(volume.shape3d):
            return None

        if not np.allclose(entry.get("spacing"), volume.spacing, atol=1e-4):
            return None

        if "origin" in entry:
            if not np.allclose(entry.get("origin"), volume.origin, atol=1e-4):
                return None

        return entry
