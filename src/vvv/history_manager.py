import os
import json
import numpy as np
from pathlib import Path
from vvv.utils import get_history_path_key


class HistoryManager:
    def __init__(self):
        if os.name == "nt":
            self.config_dir = Path(os.getenv("APPDATA")) / "VVV"
        else:
            self.config_dir = Path.home() / ".config" / "vvv"

        self.history_path = self.config_dir / "history.json"
        self.data = {}
        self.max_history_files = 100  # Enforce limit
        self.load()

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
        key = get_history_path_key(primary_path)

        # Extract Overlay Path
        overlay_path = None
        if vs.display.overlay_id and vs.display.overlay_id in controller.volumes:
            ov_path = controller.volumes[vs.display.overlay_id].file_paths[0]
            overlay_path = get_history_path_key(ov_path)

        # Remove the key if it exists so we can push it to the "end" of the dictionary (LRU logic)
        if key in self.data:
            del self.data[key]

        # Extract ROI paths and states
        rois_list = []
        for roi_id, roi_state in vs.rois.items():
            if roi_id in controller.volumes:
                r_vol = controller.volumes[roi_id]
                if r_vol.file_paths:
                    r_path = get_history_path_key(r_vol.file_paths[0])
                    rois_list.append({"path": r_path, "state": roi_state.to_dict()})

        # Cast NumPy arrays to native Python types
        self.data[key] = {
            "shape3d": [int(x) for x in vol.shape3d],
            "spacing": [float(x) for x in vol.spacing],
            "origin": [float(x) for x in vol.origin],
            "camera": vs.camera.to_dict(),
            "display": vs.display.to_dict(),
            "overlay_path": overlay_path,
            "rois": rois_list,
        }

        # Enforce the 100 files limit by deleting the oldest item(s) at the front of the dict
        while len(self.data) > self.max_history_files:
            oldest_key = next(iter(self.data))
            del self.data[oldest_key]

        self.save()

    def get_image_state(self, volume):
        primary_path = volume.file_paths[0]
        key = get_history_path_key(primary_path)

        if key not in self.data:
            return None

        entry = self.data[key]

        # Strict Geometry Validation (No more mtime!)
        if entry.get("shape3d") != list(volume.shape3d):
            return None

        if not np.allclose(entry.get("spacing"), volume.spacing, atol=1e-4):
            return None

        # Validate origin (with a safe fallback if loading an old history file)
        if "origin" in entry:
            if not np.allclose(entry.get("origin"), volume.origin, atol=1e-4):
                return None

        return entry
