import os
import json
import csv
import uuid
from typing import Optional, Dict, List, Any
import numpy as np
import dearpygui.dearpygui as dpg

from vvv.config import ROI_COLORS
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog
from .landmark_state import Landmark


class LandmarkPluginController(PluginTagMixin):
    """Controller managing landmark data, CRUD actions, and UI callbacks."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None
        self.landmark_filters: Dict[str, str] = {}
        self.landmark_counters: Dict[str, int] = {}
        self.landmarks_file_path: Dict[str, Optional[str]] = {}
        self.enhanced_vis: bool = False

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        self.landmark_filters.pop(image_id, None)
        self.landmarks_file_path.pop(image_id, None)

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        if context == "history":
            return {}
        file_path = self.landmarks_file_path.get(image_id)
        landmarks = self.get_landmarks(image_id)
        res: Dict[str, Any] = {"landmarks": [lm.to_dict() for lm in landmarks.values()]}
        if file_path:
            res["file_path"] = file_path
        return res

    def restore_image_state(
        self, image_id: str, data: dict, context: str = "history"
    ) -> None:
        if context == "history" or not data:
            return
        file_path = data.get("file_path")
        if file_path:
            self.landmarks_file_path[image_id] = file_path

        if file_path and os.path.exists(file_path):
            self.load_landmarks(file_path, image_id)
        elif "landmarks" in data:
            vs = self._api.get_view_states().get(image_id) if self._api else None
            if vs:
                new_landmarks = {}
                for idx, item in enumerate(data["landmarks"], start=1):
                    lm_id = item.get("id") or f"lm_{idx:03d}"
                    new_landmarks[lm_id] = Landmark.from_dict(item)
                vs.landmarks = new_landmarks
                self.landmark_counters[image_id] = len(new_landmarks)
                vs.is_geometry_dirty = True
                if self._api:
                    self._api.request_refresh()

    def on_toggle_enhanced_vis(self, sender, app_data, user_data=None) -> None:
        self.enhanced_vis = bool(app_data)
        if self._api:
            for vs in self._api.get_view_states().values():
                vs.is_geometry_dirty = True
            self._api.request_refresh()

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        pass

    # --- Helpers to access active image state ---

    def _get_active_vs_id(self) -> Optional[str]:
        if not self._api:
            return None
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id and viewer.view_state:
            return viewer.image_id
        return None

    def get_landmarks(self, image_id: Optional[str] = None) -> Dict[str, Landmark]:
        if not self._api:
            return {}
        vs_id = image_id or self._get_active_vs_id()
        if not vs_id:
            return {}
        vs = self._api.get_view_states().get(vs_id)
        if not vs:
            return {}
        if not hasattr(vs, "landmarks"):
            vs.landmarks = {}
        return vs.landmarks

    # --- Landmark CRUD Operations ---

    def add_landmark(
        self,
        image_id: Optional[str] = None,
        pt_phys: Optional[List[float]] = None,
        name: Optional[str] = None,
        color: Optional[List[int]] = None,
    ) -> Optional[Landmark]:
        if not self._api:
            return None

        target_id = image_id or self._get_active_vs_id()
        if not target_id:
            self._api.notify("Please select an active image volume first.")
            return None

        vs = self._api.get_view_states().get(target_id)
        if not vs:
            return None

        if not hasattr(vs, "landmarks"):
            vs.landmarks = {}

        if pt_phys is None:
            if vs.camera.crosshair_phys_coord is not None:
                pt_phys = list(vs.camera.crosshair_phys_coord)
            else:
                pt_phys = [0.0, 0.0, 0.0]

        curr_counter = self.landmark_counters.get(target_id, 0) + 1
        self.landmark_counters[target_id] = curr_counter

        if not name:
            name = f"Landmark {curr_counter}"

        if color is None:
            c = ROI_COLORS[(curr_counter - 1) % len(ROI_COLORS)]
            color = [c[0], c[1], c[2], 255] if len(c) == 3 else list(c)

        lm_id = f"lm_{uuid.uuid4().hex[:8]}"
        lm = Landmark(
            id=lm_id,
            name=name,
            pt_phys=pt_phys,
            color=color,
            visible=True,
        )

        vs.landmarks[lm_id] = lm
        vs.is_geometry_dirty = True
        self._api.request_refresh()
        self._api.notify(f"Added landmark '{lm.name}' at [{pt_phys[0]:.1f}, {pt_phys[1]:.1f}, {pt_phys[2]:.1f}]")
        return lm

    def remove_landmark(self, landmark_id: str, image_id: Optional[str] = None) -> None:
        if not self._api:
            return
        target_id = image_id or self._get_active_vs_id()
        if not target_id:
            return
        vs = self._api.get_view_states().get(target_id)
        if vs and hasattr(vs, "landmarks") and landmark_id in vs.landmarks:
            del vs.landmarks[landmark_id]
            if not vs.landmarks:
                self.landmarks_file_path[target_id] = None
                if self._ui:
                    self._ui._last_state_key = None
            vs.is_geometry_dirty = True
            self._api.request_refresh()

    def clear_all_landmarks(self, image_id: Optional[str] = None) -> None:
        if not self._api:
            return
        target_id = image_id or self._get_active_vs_id()
        if not target_id:
            return
        vs = self._api.get_view_states().get(target_id)
        if vs and hasattr(vs, "landmarks"):
            vs.landmarks.clear()
            self.landmarks_file_path[target_id] = None
            vs.is_geometry_dirty = True
            if self._ui:
                self._ui._last_state_key = None
            self._api.request_refresh()
            self._api.notify("Cleared all landmarks.")

    def center_on_landmark(self, landmark_id: str, image_id: Optional[str] = None) -> None:
        if not self._api:
            return
        target_id = image_id or self._get_active_vs_id()
        if not target_id:
            return
        landmarks = self.get_landmarks(target_id)
        lm = landmarks.get(landmark_id)
        if not lm:
            return

        vs = self._api.get_view_states().get(target_id)
        if vs and lm.pt_phys:
            vs.update_crosshair_from_phys(np.array(lm.pt_phys))
            self._api.propagate_sync(target_id)
            self._api.update_all_viewers_of_image(target_id, data_dirty=False)

            viewers = self._api.get_viewers()
            for viewer in viewers.values():
                if viewer.image_id == target_id:
                    viewer.center_on_physical_coord(lm.pt_phys)

            self._api.notify(f"Centered crosshair on landmark '{lm.name}'")

    def update_landmark_name(self, landmark_id: str, name: str, image_id: Optional[str] = None) -> None:
        landmarks = self.get_landmarks(image_id)
        if landmark_id in landmarks:
            landmarks[landmark_id].name = name
            vs_id = image_id or self._get_active_vs_id()
            if self._api and vs_id:
                vs = self._api.get_view_states().get(vs_id)
                if vs:
                    vs.is_geometry_dirty = True
                self._api.request_refresh()

    def update_landmark_color(self, landmark_id: str, color: List[int], image_id: Optional[str] = None) -> None:
        landmarks = self.get_landmarks(image_id)
        if landmark_id in landmarks:
            from vvv.ui.ui_components import normalize_rgba_to_int
            landmarks[landmark_id].color = normalize_rgba_to_int(color)
            vs_id = image_id or self._get_active_vs_id()
            if self._api and vs_id:
                vs = self._api.get_view_states().get(vs_id)
                if vs:
                    vs.is_geometry_dirty = True
                # Use update_all_viewers (not request_refresh) to avoid
                # rebuilding the sidebar table and destroying the active
                # color picker widget mid-interaction.
                self._api.update_all_viewers_of_image(vs_id, data_dirty=False)

    def update_landmark_visible(self, landmark_id: str, visible: bool, image_id: Optional[str] = None) -> None:
        landmarks = self.get_landmarks(image_id)
        if landmark_id in landmarks:
            landmarks[landmark_id].visible = visible
            vs_id = image_id or self._get_active_vs_id()
            if self._api and vs_id:
                vs = self._api.get_view_states().get(vs_id)
                if vs:
                    vs.is_geometry_dirty = True
                self._api.request_refresh()

    def update_landmark_show_name(self, landmark_id: str, show_name: bool, image_id: Optional[str] = None) -> None:
        landmarks = self.get_landmarks(image_id)
        if landmark_id in landmarks:
            landmarks[landmark_id].show_name = show_name
            vs_id = image_id or self._get_active_vs_id()
            if self._api and vs_id:
                vs = self._api.get_view_states().get(vs_id)
                if vs:
                    vs.is_geometry_dirty = True
                self._api.update_all_viewers_of_image(vs_id, data_dirty=False)

    def toggle_all_show_names(self, image_id: Optional[str] = None) -> None:
        """Toggle show_name for all landmarks. If any is True, set all False; else set all True."""
        landmarks = self.get_landmarks(image_id)
        if not landmarks:
            return
        any_on = any(lm.show_name for lm in landmarks.values())
        new_val = not any_on
        for lm in landmarks.values():
            lm.show_name = new_val
        vs_id = image_id or self._get_active_vs_id()
        if self._api and vs_id:
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()

    def snap_landmark_to_grid(self, landmark_id: str, image_id: Optional[str] = None) -> None:
        vs_id = image_id or self._get_active_vs_id()
        if not vs_id or not self._api:
            return
        vol = self._api.get_volumes().get(vs_id)
        landmarks = self.get_landmarks(vs_id)
        if landmark_id in landmarks and vol:
            landmarks[landmark_id].snap_to_voxel_grid(vol)
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()

    def snap_all_landmarks(self, image_id: Optional[str] = None) -> None:
        vs_id = image_id or self._get_active_vs_id()
        if not vs_id or not self._api:
            return
        vol = self._api.get_volumes().get(vs_id)
        landmarks = self.get_landmarks(vs_id)
        if vol and landmarks:
            for lm in landmarks.values():
                lm.snap_to_voxel_grid(vol)
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()

    def save_landmarks(self, filepath: str, image_id: Optional[str] = None) -> None:
        """Saves landmarks to a .json or .csv file (detected from extension)."""
        vs_id = image_id or self._get_active_vs_id()
        if not vs_id:
            return
        landmarks = self.get_landmarks(vs_id)
        path_str = str(filepath)

        if path_str.lower().endswith(".csv"):
            fieldnames = ["ID", "Name", "X_mm", "Y_mm", "Z_mm", "Color_R", "Color_G", "Color_B", "Color_A", "Visible", "ShowName"]
            with open(path_str, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for lm in landmarks.values():
                    writer.writerow(lm.to_csv_row())
        else:
            # Default to JSON
            data = {
                "landmarks": [lm.to_dict() for lm in landmarks.values()]
            }
            with open(path_str, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        self.landmarks_file_path[vs_id] = path_str
        if self._ui:
            self._ui._last_state_key = None
        if self._api:
            self._api.request_refresh()
            self._api.notify(f"Saved {len(landmarks)} landmark(s) to {os.path.basename(path_str)}")

    def load_landmarks(self, filepath: str, image_id: Optional[str] = None) -> None:
        """Loads landmarks from a .json or .csv file."""
        vs_id = image_id or self._get_active_vs_id()
        if not vs_id or not self._api:
            return
        vs = self._api.get_view_states().get(vs_id)
        if not vs:
            return

        path_str = str(filepath)
        if not os.path.exists(path_str):
            return

        current_landmarks = getattr(vs, "landmarks", {})
        count_added = 0

        if path_str.lower().endswith(".csv"):
            with open(path_str, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader, start=1):
                    fallback_id = f"lm_{len(current_landmarks) + idx:03d}"
                    lm_obj = Landmark.from_csv_row(row, fallback_id)
                    # If ID collides, generate a unique ID
                    if lm_obj.id in current_landmarks:
                        curr_c = self.landmark_counters.get(vs_id, 0) + 1
                        self.landmark_counters[vs_id] = curr_c
                        lm_obj.id = f"lm_{curr_c:03d}"
                    current_landmarks[lm_obj.id] = lm_obj
                    count_added += 1
        else:
            with open(path_str, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_list = data.get("landmarks", []) if isinstance(data, dict) else data
            for idx, item in enumerate(raw_list, start=1):
                curr_c = self.landmark_counters.get(vs_id, 0) + 1
                self.landmark_counters[vs_id] = curr_c
                lm_id = item.get("id") or f"lm_{curr_c:03d}"
                if lm_id in current_landmarks:
                    lm_id = f"lm_{curr_c:03d}"
                lm_obj = Landmark.from_dict(item)
                lm_obj.id = lm_id
                current_landmarks[lm_id] = lm_obj
                count_added += 1

        vs.landmarks = current_landmarks
        self.landmarks_file_path[vs_id] = path_str
        vs.is_geometry_dirty = True
        if self._ui:
            self._ui._last_state_key = None
        self._api.request_refresh()
        self._api.notify(f"Added {count_added} landmark(s) from {os.path.basename(path_str)}")

    # --- UI Callbacks ---

    def on_btn_add_clicked(self, sender, app_data, user_data) -> None:
        if not self._api:
            return
        self.add_landmark()

    def on_btn_load_clicked(self, sender, app_data, user_data) -> None:
        file_paths = open_file_dialog(
            "Load Landmark File (.json, .csv)",
            multiple=False,
            extensions=["json", "csv"],
        )
        if file_paths:
            fp = file_paths[0] if isinstance(file_paths, list) else file_paths
            if fp:
                self.load_landmarks(fp)

    def on_btn_save_clicked(self, sender, app_data, user_data) -> None:
        vs_id = self._get_active_vs_id()
        if not vs_id:
            return
        saved_path = self.landmarks_file_path.get(vs_id)
        if saved_path and os.path.exists(saved_path):
            self.save_landmarks(saved_path, image_id=vs_id)
        else:
            self.on_btn_save_as_clicked(sender, app_data, user_data)

    def on_btn_save_as_clicked(self, sender, app_data, user_data) -> None:
        vs_id = self._get_active_vs_id()
        default_name = f"landmarks_{vs_id}.json" if vs_id else "landmarks.json"
        file_path = save_file_dialog("Save Landmarks As (.json, .csv)", default_name=default_name)
        if file_path:
            self.save_landmarks(file_path, image_id=vs_id)

    def on_btn_snap_all_clicked(self, sender, app_data, user_data) -> None:
        self.snap_all_landmarks()

    def on_btn_clear_all_clicked(self, sender, app_data, user_data) -> None:
        self.clear_all_landmarks()

    def on_filter_changed(self, filter_text: str) -> None:
        vs_id = self._get_active_vs_id()
        if vs_id:
            self.landmark_filters[vs_id] = filter_text.strip().lower()
            if self._api:
                self._api.request_refresh()

    def on_clear_filter_clicked(self) -> None:
        vs_id = self._get_active_vs_id()
        if vs_id:
            self.landmark_filters[vs_id] = ""
            if self._api:
                self._api.request_refresh()

    def on_batch_color_changed(self, color_rgba) -> None:
        vs_id = self._get_active_vs_id()
        if not vs_id:
            return
        landmarks = self.get_landmarks(vs_id)
        filter_text = self.landmark_filters.get(vs_id, "").lower()
        from vvv.ui.ui_components import normalize_rgba_to_int
        color_255 = normalize_rgba_to_int(color_rgba)

        for lm_id, lm in landmarks.items():
            if not filter_text or filter_text in lm.name.lower():
                lm.color = color_255

        if self._api:
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()

    def on_batch_reset_colors(self) -> None:
        """Reset colors of landmarks sequentially according to ROI_COLORS palette."""
        vs_id = self._get_active_vs_id()
        if not vs_id:
            return
        landmarks = self.get_landmarks(vs_id)
        if not landmarks:
            return
        for idx, lm in enumerate(landmarks.values()):
            c = ROI_COLORS[idx % len(ROI_COLORS)]
            lm.color = [c[0], c[1], c[2], 255] if len(c) == 3 else list(c)

        if self._api:
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()

    def on_batch_toggle_visible(self) -> None:
        """Toggle visibility for filtered landmarks. If any visible, hide all; else show all."""
        vs_id = self._get_active_vs_id()
        if not vs_id:
            return
        landmarks = self.get_landmarks(vs_id)
        filter_text = self.landmark_filters.get(vs_id, "").lower()
        filtered = [lm for lm in landmarks.values() if not filter_text or filter_text in lm.name.lower()]
        any_visible = any(lm.visible for lm in filtered)
        new_val = not any_visible
        for lm in filtered:
            lm.visible = new_val
        if self._api:
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()

    def on_batch_delete_clicked(self) -> None:
        vs_id = self._get_active_vs_id()
        if not vs_id:
            return
        landmarks = self.get_landmarks(vs_id)
        filter_text = self.landmark_filters.get(vs_id, "").lower()
        to_delete = [lm_id for lm_id, lm in landmarks.items() if not filter_text or filter_text in lm.name.lower()]
        for lm_id in to_delete:
            del landmarks[lm_id]
        if not landmarks:
            self.landmarks_file_path[vs_id] = None
            if self._ui:
                self._ui._last_state_key = None
        if self._api:
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()
