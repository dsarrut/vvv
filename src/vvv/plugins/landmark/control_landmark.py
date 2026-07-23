import uuid
from typing import Optional, Dict, List
import dearpygui.dearpygui as dpg

from vvv.config import ROI_COLORS
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from .landmark_state import Landmark


class LandmarkPluginController(PluginTagMixin):
    """Controller managing landmark data, CRUD actions, and UI callbacks."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None
        self.landmark_filters: Dict[str, str] = {}
        self.landmark_counters: Dict[str, int] = {}

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

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return {}

    def restore_image_state(
        self, image_id: str, data: dict, context: str = "history"
    ) -> None:
        pass

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
            vs.is_geometry_dirty = True
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
            vs.update_crosshair_from_phys(lm.pt_phys)
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
            if self._api:
                self._api.request_refresh()

    def update_landmark_color(self, landmark_id: str, color: List[int], image_id: Optional[str] = None) -> None:
        landmarks = self.get_landmarks(image_id)
        if landmark_id in landmarks:
            landmarks[landmark_id].color = list(color)
            vs_id = image_id or self._get_active_vs_id()
            if self._api and vs_id:
                vs = self._api.get_view_states().get(vs_id)
                if vs:
                    vs.is_geometry_dirty = True
                self._api.request_refresh()

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

    # --- UI Callbacks ---

    def on_btn_add_clicked(self, sender, app_data, user_data) -> None:
        self.add_landmark()

    def on_btn_load_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_btn_save_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_btn_snap_all_clicked(self, sender, app_data, user_data) -> None:
        pass

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
        color_255 = [int(c * 255) for c in color_rgba[:4]] if max(color_rgba) <= 1.0 else [int(c) for c in color_rgba[:4]]

        for lm_id, lm in landmarks.items():
            if not filter_text or filter_text in lm.name.lower():
                lm.color = color_255

        if self._api:
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()

    def on_batch_show_clicked(self) -> None:
        vs_id = self._get_active_vs_id()
        if not vs_id:
            return
        landmarks = self.get_landmarks(vs_id)
        filter_text = self.landmark_filters.get(vs_id, "").lower()
        for lm_id, lm in landmarks.items():
            if not filter_text or filter_text in lm.name.lower():
                lm.visible = True
        if self._api:
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()

    def on_batch_hide_clicked(self) -> None:
        vs_id = self._get_active_vs_id()
        if not vs_id:
            return
        landmarks = self.get_landmarks(vs_id)
        filter_text = self.landmark_filters.get(vs_id, "").lower()
        for lm_id, lm in landmarks.items():
            if not filter_text or filter_text in lm.name.lower():
                lm.visible = False
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
        if self._api:
            vs = self._api.get_view_states().get(vs_id)
            if vs:
                vs.is_geometry_dirty = True
            self._api.request_refresh()
