from __future__ import annotations

from typing import Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from vvv.core.view_state import ViewState



import numpy as np


class PluginTagMixin:
    """Provides DPG tag namespacing for plugin controllers and UIs."""

    _plugin_id: str

    def _t(self, name: str) -> str:
        return f"{self._plugin_id}_{name}"


@runtime_checkable
class PluginProtocol(Protocol):
    """Structural interface every plugin must satisfy."""

    plugin_id: str
    label: str
    order: int

    def create_ui(self, parent, api: PluginAPI) -> None: ...
    def update(self, api: PluginAPI) -> None: ...
    def on_image_loaded(self, image_id: str) -> None: ...
    def on_image_removed(self, image_id: str) -> None: ...
    def serialize_image_state(self, image_id: str, context: str = "history") -> dict: ...
    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None: ...
    def save_settings(self, api: PluginAPI) -> None: ...
    def load_settings(self, api: PluginAPI) -> None: ...
    def destroy(self) -> None: ...


class PluginAPI:
    """Restricted surface area exposed to plugins. Plugins must not hold a reference to gui or controller."""

    def __init__(self, gui):
        self._gui = gui
        self._controller = gui.controller

    @property
    def is_dirty(self):
        if self._controller.ui_needs_refresh:
            return True
        viewer = self._gui.context_viewer
        if not viewer or not viewer.view_state:
            return False
        if viewer.view_state.is_data_dirty:
            return True
        ov_id = viewer.view_state.display.overlay.image_id
        if ov_id:
            ov_vs = self._controller.view_states.get(ov_id)
            if ov_vs and ov_vs.is_data_dirty:
                return True
        return False

    def get_ui_config(self):
        return self._gui.ui_cfg

    # --- Beginner-mode surface (allows passing api as the `gui` arg to ui_components) ---

    @property
    def ui_cfg(self):
        return self._gui.ui_cfg

    @property
    def is_beginner_mode(self) -> bool:
        return self._gui.is_beginner_mode

    @property
    def beginner_tags(self) -> list:
        return self._gui.beginner_tags

    @property
    def beginner_sliders(self) -> list:
        return self._gui.beginner_sliders

    def create_labeled_field(self, label, tag, help_text=None):
        self._gui.create_labeled_field(label, tag, help_text=help_text)

    def get_active_image_name(self):
        viewer = self._gui.context_viewer
        if viewer and viewer.image_id:
            name, _ = self._controller.get_image_display_name(viewer.image_id)
            return name
        return "None"

    def get_crosshair_world(self):
        viewer = self._gui.context_viewer
        if viewer and viewer.view_state and viewer.view_state.camera.crosshair_phys_coord is not None:
            return viewer.view_state.camera.crosshair_phys_coord
        return [0.0, 0.0, 0.0]

    def get_mouse_position(self):
        if hasattr(self._gui.interaction, "last_mouse_pos"):
            return self._gui.interaction.last_mouse_pos
        return [0, 0]

    def get_active_viewer(self):
        return self._gui.context_viewer

    def get_viewers(self):
        return self._controller.viewers

    def get_volumes(self):
        return self._controller.volumes

    def get_image_display_name(self, image_id):
        return self._controller.get_image_display_name(image_id)

    def get_view_states(self) -> dict[str, ViewState]:
        return self._controller.view_states


    def request_refresh(self):
        self._controller.ui_needs_refresh = True

    def notify(self, msg, color=None):
        self._gui.show_status_message(msg, color=color)

    # --- Sync actions (wraps controller internals; keeps plugins off the controller directly) ---

    def propagate_window_level(self, image_id):
        self._controller.sync.propagate_window_level(image_id)

    def propagate_colormap(self, image_id):
        self._controller.sync.propagate_colormap(image_id)

    def propagate_sync(self, image_id):
        self._controller.sync.propagate_sync(image_id)

    def get_sync_group_vs_ids(self, image_id, active_only=False) -> list[str]:
        return self._controller.sync.get_sync_group_vs_ids(image_id, active_only=active_only)

    def get_profile_data(self, image_id, profile):
        return self._controller.profiles.get_profile_data(image_id, profile)

    def get_full_export_data(self, image_id, profile):
        return self._controller.profiles.get_full_export_data(image_id, profile)

    # --- Registration operations ---

    def load_transform(self, image_id, file_path) -> bool:
        return self._controller.load_transform(image_id, file_path)

    def save_transform(self, image_id, file_path) -> bool:
        return self._controller.save_transform(image_id, file_path)

    def resample_image(self, image_id) -> None:
        self._controller.resample_image(image_id)

    def bake_transform_to_volume(self, image_id) -> None:
        self._controller.bake_transform_to_volume(image_id)

    def update_transform_manual(self, image_id, tx, ty, tz, rx, ry, rz) -> None:
        self._controller.update_transform_manual(image_id, tx, ty, tz, rx, ry, rz)

    def get_volume_physical_center(self, volume) -> list[float]:
        return self._controller.get_volume_physical_center(volume)

    def update_all_viewers_of_image(self, image_id, data_dirty=True) -> None:
        self._controller.update_all_viewers_of_image(image_id, data_dirty=data_dirty)

    def update_sidebar_crosshair(self, viewer) -> None:
        self._gui.update_sidebar_crosshair(viewer)

    def set_async_status(self, msg):
        """Set a status message from a background thread (picked up by the main loop)."""
        self._controller.status_message = msg

    def run_on_main_thread(self, callback):
        """Schedule a callback to be executed on the main GUI thread."""
        self._gui.schedule_main_thread(callback)

    def scan_dicom_folder(self, folder, recursive=True):
        return self._controller.file.scan_dicom_folder(folder, recursive=recursive)

    def load_dicom_series(self, file_list: list[str]) -> None:
        from vvv.ui.ui_sequences import load_batch_images_sequence
        self._gui.tasks.append(
            load_batch_images_sequence(self._gui, self._controller, [file_list])
        )

    # --- ROI operations ---

    def parse_rtstruct(self, filepath) -> list[dict]:
        return self._controller.roi.parse_rtstruct(filepath)

    def close_roi(self, image_id, roi_id) -> None:
        self._controller.roi.close_roi(image_id, roi_id)

    def reload_roi(self, image_id, roi_id) -> None:
        self._controller.roi.reload_roi(image_id, roi_id)

    def center_on_roi(self, image_id, roi_id) -> None:
        self._controller.roi.center_on_roi(image_id, roi_id)

    def get_roi_stats(self, base_vs_id, roi_id, is_overlay) -> dict | None:
        return self._controller.roi.get_roi_stats(base_vs_id=base_vs_id, roi_id=roi_id, is_overlay=is_overlay)

    def save_image(self, image_id, file_path) -> None:
        self._controller.save_image(image_id, file_path)

    def load_rtstruct(self, image_id, filepath, selected_rois) -> None:
        from vvv.ui.ui_sequences import load_rtstruct_sequence
        self._gui.tasks.append(
            load_rtstruct_sequence(self._gui, self._controller, image_id, filepath, selected_rois)
        )

    def load_label_map(self, image_id, file_paths) -> None:
        from vvv.ui.ui_sequences import load_label_map_sequence
        self._gui.tasks.append(
            load_label_map_sequence(self._gui, self._controller, image_id, file_paths)
        )

    def load_batch_rois(self, image_id, file_paths, source_type, mode, val) -> None:
        from vvv.ui.ui_sequences import load_batch_rois_sequence
        self._gui.tasks.append(
            load_batch_rois_sequence(self._gui, self._controller, image_id, file_paths, source_type, mode, val)
        )

    # --- Image mounting ---

    def mount_generated_image(self, new_vol, new_vs) -> str:
        """Register a newly created volume+view_state and assign it to the active viewer."""
        with self._controller._state_lock:
            new_id = str(self._controller.next_image_id)
            self._controller.next_image_id += 1
            self._controller.volumes[new_id] = new_vol
            self._controller.view_states[new_id] = new_vs
        viewer = self._gui.context_viewer
        if viewer:
            self._controller.layout[viewer.tag] = new_id
        self._gui.notify_plugins_image_loaded(new_id)
        return new_id

    # --- Contour operations ---

    def add_contour(self, image_id: str, contour_roi) -> None:
        self._controller.contours.add_contour(image_id, contour_roi)

    def remove_contour(self, image_id: str, contour_id: str) -> None:
        self._controller.contours.remove_contour(image_id, contour_id)

    # --- Plugin settings (persisted in the app settings file under "plugins.<namespace>") ---

    def get_settings(self, namespace: str) -> dict:
        return self._controller.settings.data.get("plugins", {}).get(namespace, {})

    def set_settings(self, namespace: str, data: dict) -> None:
        self._controller.settings.data.setdefault("plugins", {})[namespace] = data
