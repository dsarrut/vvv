import json
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI
from vvv.utils import ViewMode
from vvv.config import ROI_COLORS
from vvv.ui.file_dialog import save_file_dialog


class MockProfile:
    """Mock profile representing the state of an intensity profile line."""

    def __init__(self, id_val, name, color, pt1, pt2, orientation, slice_idx):
        self.id = id_val
        self.name = name
        self.color = color
        self.pt1_phys = np.array(pt1, dtype=float)
        self.pt2_phys = np.array(pt2, dtype=float)
        self.orientation = orientation
        self.slice_idx = slice_idx
        self.plot_open = False
        self.use_log = False


class ProfilePluginState:
    """Per-image state for the profiles plugin."""

    def __init__(self):
        self.profiles = {}
        self.is_initialized = False


class ProfilePluginController:
    """Stub controller for mock interactive profiles in the plugin."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api = None
        self._ui = None
        self._states: dict[str, ProfilePluginState] = {}

    def _t(self, name: str) -> str:
        return f"{self._plugin_id}_{name}"

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def get_image_state(self, image_id: str) -> ProfilePluginState:
        if image_id not in self._states:
            self._states[image_id] = ProfilePluginState()
        state = self._states[image_id]
        if not state.is_initialized:
            # Pre-populate with two mock profiles to showcase the UI
            p1_id = f"{self._plugin_id}_mock_p1_{image_id}"
            p2_id = f"{self._plugin_id}_mock_p2_{image_id}"
            state.profiles[p1_id] = MockProfile(
                id_val=p1_id,
                name="Mock Profile 1",
                color=[255, 0, 0, 255],
                pt1=[10.0, 20.0, 30.0],
                pt2=[50.0, 20.0, 30.0],
                orientation=ViewMode.AXIAL,
                slice_idx=10,
            )
            state.profiles[p2_id] = MockProfile(
                id_val=p2_id,
                name="Mock Profile 2",
                color=[0, 0, 255, 255],
                pt1=[25.0, 15.0, 40.0],
                pt2=[25.0, 60.0, 40.0],
                orientation=ViewMode.AXIAL,
                slice_idx=10,
            )
            state.is_initialized = True
        return state

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def on_image_loaded(self, image_id: str) -> None:
        self.get_image_state(image_id)

    def on_image_removed(self, image_id: str) -> None:
        state = self._states.pop(image_id, None)
        if state:
            # Delete any floating plot windows for this image
            for p_id in state.profiles:
                win_tag = f"plot_win_{p_id}"
                if dpg.does_item_exist(win_tag):
                    dpg.delete_item(win_tag)

    def serialize_image_state(self, image_id: str) -> dict:
        state = self._states.get(image_id)
        if state is None:
            return {}
        return {
            "profiles": {
                p_id: {
                    "id": p.id,
                    "name": p.name,
                    "color": p.color,
                    "pt1_phys": list(p.pt1_phys),
                    "pt2_phys": list(p.pt2_phys),
                    "orientation": p.orientation.name,
                    "slice_idx": p.slice_idx,
                    "plot_open": p.plot_open,
                    "use_log": p.use_log,
                }
                for p_id, p in state.profiles.items()
            }
        }

    def restore_image_state(self, image_id: str, data: dict) -> None:
        if not data:
            return
        state = self.get_image_state(image_id)
        state.profiles = {}
        for p_id, p_data in data.get("profiles", {}).items():
            ori_name = p_data.get("orientation", "AXIAL")
            ori = getattr(ViewMode, ori_name, ViewMode.AXIAL)
            p = MockProfile(
                id_val=p_data["id"],
                name=p_data["name"],
                color=p_data["color"],
                pt1=p_data["pt1_phys"],
                pt2=p_data["pt2_phys"],
                orientation=ori,
                slice_idx=p_data["slice_idx"],
            )
            p.plot_open = p_data.get("plot_open", False)
            p.use_log = p_data.get("use_log", False)
            state.profiles[p_id] = p

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        # Delete any open plot windows
        for state in self._states.values():
            for p_id in state.profiles:
                win_tag = f"plot_win_{p_id}"
                if dpg.does_item_exist(win_tag):
                    dpg.delete_item(win_tag)

    # --- UI Interactions and Callbacks ---

    def get_mock_profile_data(self, profile: MockProfile):
        """Generates realistic look-alike mock distance and intensity curve data."""
        np.random.seed(hash(profile.id) % 2**32)
        length = float(np.linalg.norm(profile.pt2_phys - profile.pt1_phys))
        if length < 1e-3:
            length = 10.0
        num_points = int(max(10, length))
        distances = np.linspace(0.0, length, num_points)
        # Mock signal using a sine wave, trend, and minor high-frequency noise
        noise = np.random.normal(0, 5, num_points)
        trend = np.linspace(50, 150, num_points)
        wave = 50 * np.sin(distances * 0.2)
        intensities = trend + wave + noise
        return distances.tolist(), intensities.tolist()

    def on_btn_add_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            self._api.notify("Please load an image first.")
            return

        state = self.get_image_state(viewer.image_id)
        # Create a new unique mock profile
        new_id = f"{self._plugin_id}_mock_p_{dpg.generate_uuid()}"
        color_idx = len(state.profiles)
        color = list(ROI_COLORS[color_idx % len(ROI_COLORS)]) + [255]

        # Use current slice position if available
        slice_idx = viewer.slice_idx if hasattr(viewer, "slice_idx") else 0
        orientation = viewer.orientation if hasattr(viewer, "orientation") else ViewMode.AXIAL

        state.profiles[new_id] = MockProfile(
            id_val=new_id,
            name=f"Mock Profile {len(state.profiles) + 1}",
            color=color,
            pt1=[15.0, 15.0, 20.0],
            pt2=[45.0, 35.0, 20.0],
            orientation=orientation,
            slice_idx=slice_idx,
        )

        self._api.notify("Added a new mock profile line to list (no view wiring)")
        self._api.request_refresh()

    def on_color_changed(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer() if self._api else None
        if not viewer or not viewer.image_id:
            return
        state = self.get_image_state(viewer.image_id)
        p = state.profiles.get(user_data)
        if p:
            p.color = list(app_data[:4])
            self._api.request_refresh()

    def on_profile_name_changed(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer() if self._api else None
        if not viewer or not viewer.image_id:
            return
        state = self.get_image_state(viewer.image_id)
        p = state.profiles.get(user_data)
        if p:
            p.name = app_data
            win_tag = f"plot_win_{p.id}"
            if dpg.does_item_exist(win_tag):
                dpg.configure_item(win_tag, label=f"Profile: {p.name}")
            self._api.request_refresh()

    def on_delete_clicked(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer() if self._api else None
        if not viewer or not viewer.image_id:
            return
        state = self.get_image_state(viewer.image_id)
        p_id = user_data
        if p_id in state.profiles:
            del state.profiles[p_id]
            win_tag = f"plot_win_{p_id}"
            if dpg.does_item_exist(win_tag):
                dpg.delete_item(win_tag)
            self._api.notify("Deleted mock profile")
            self._api.request_refresh()

    def on_align_clicked(self, sender, app_data, user_data):
        p_id, direction = user_data
        self._api.notify(f"Stub align clicked ({direction.upper()}) for profile {p_id}")

    def on_snap_clicked(self, sender, app_data, user_data):
        p_id = user_data
        self._api.notify(f"Stub pixel snap clicked for profile {p_id}")

    def on_goto_clicked(self, sender, app_data, user_data):
        p_id = user_data
        self._api.notify(f"Stub camera goto clicked for profile {p_id}")

    def on_change_slice_clicked(self, sender, app_data, user_data):
        p_id, delta = user_data
        self._api.notify(f"Stub change slice clicked (delta {delta}) for profile {p_id}")

    def on_profile_coord_edited(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer() if self._api else None
        if not viewer or not viewer.image_id:
            return
        state = self.get_image_state(viewer.image_id)
        p_id, pt_idx = user_data["id"], user_data["pt"]
        p = state.profiles.get(p_id)
        if p:
            new_val = np.array(app_data)
            if pt_idx == 1:
                p.pt1_phys = new_val
            else:
                p.pt2_phys = new_val
            # Refresh plot contents
            self._ui.refresh_plot_series(p)

    def on_toggle_log_clicked(self, sender, app_data, user_data):
        p_id = user_data
        viewer = self._api.get_active_viewer() if self._api else None
        if not viewer or not viewer.image_id:
            return
        state = self.get_image_state(viewer.image_id)
        p = state.profiles.get(p_id)
        if p:
            p.use_log = not p.use_log
            if self._ui:
                self._ui.rebuild_plot_window_contents(p)

    def on_export_profile_clicked(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer() if self._api else None
        if not viewer or not viewer.image_id:
            return
        state = self.get_image_state(viewer.image_id)
        p = state.profiles.get(user_data)
        if not p:
            return

        default_name = f"profile_plugin_{p.name.replace(' ', '_')}.json"
        file_path = save_file_dialog("Export Profile Data", default_name=default_name)
        if file_path:
            distances, intensities = self.get_mock_profile_data(p)
            data = {
                "profile_name": p.name,
                "image_name": self._api.get_active_image_name(),
                "plugin_version": True,
                "data": [
                    {
                        "distance_mm": d,
                        "intensity": val,
                        "in_bounds": True,
                        "point_phys_mm": list(p.pt1_phys + (float(i) / max(1, len(distances) - 1)) * (p.pt2_phys - p.pt1_phys)),
                    }
                    for i, (d, val) in enumerate(zip(distances, intensities))
                ]
            }
            try:
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=4)
                self._api.notify(f"Exported: {p.name}")
            except Exception as e:
                self._api.notify(f"Export Failed: {e}")
