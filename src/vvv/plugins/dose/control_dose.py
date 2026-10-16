from dataclasses import dataclass, field, asdict
from typing import Optional, TYPE_CHECKING, Tuple, Any, List, Dict
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginTagMixin, PluginAPI
from vvv.maths.contours import ContourROI, extract_2d_contours_from_slice
from vvv.maths.image import SliceRenderer
from vvv.utils import compute_adaptive_step_and_speed

if TYPE_CHECKING:
    from .ui_dose import DosePluginUI

DOSE_UNITS = {"gy", "mgy", "gy/decay"}

# Standard clinical radiotherapy isodose colors
DEFAULT_ISODOSE_LEVELS = [
    (107.0, [255, 0, 0, 255]),      # 107% Hotspot (Red)
    (100.0, [0, 255, 0, 255]),      # 100% Prescription (Green)
    (95.0,  [0, 200, 255, 255]),    # 95% Target coverage (Cyan)
    (90.0,  [0, 100, 255, 255]),    # 90% High dose (Blue)
    (80.0,  [180, 50, 255, 255]),   # 80% Medium-high dose (Purple)
    (50.0,  [255, 200, 0, 255]),    # 50% Medium dose (Yellow/Orange)
    (20.0,  [255, 120, 0, 255]),    # 20% Low dose (Orange)
    (10.0,  [150, 150, 150, 255]),  # 10% Peripheral low dose (Gray)
]


@dataclass
class DoseIsocontourLevel:
    value: float                     # Relative % (or Gy in absolute mode)
    color: List[int]                 # RGBA [0-255]
    enabled: bool = True
    thickness: float = 1.5


@dataclass
class DoseIsocontourState:
    is_enabled: bool = True
    colorwash_enabled: bool = False
    colorwash_opacity: float = 0.5
    subpixel_accurate: bool = True
    levels: List[DoseIsocontourLevel] = field(default_factory=list)

    def __post_init__(self):
        if not self.levels:
            self.levels = [
                DoseIsocontourLevel(val, list(col), True, 1.5)
                for val, col in DEFAULT_ISODOSE_LEVELS
            ]


class DosePluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui: Optional["DosePluginUI"] = None
        self._states: Dict[str, DoseIsocontourState] = {}
        self._contour_rois: Dict[str, Dict[int, ContourROI]] = {}  # target_id -> {level_idx: ContourROI}
        self._cache_version: int = 0

    def get_isocontour_state(self, image_id: Optional[str]) -> DoseIsocontourState:
        if not image_id:
            return DoseIsocontourState()
        if image_id not in self._states:
            self._states[image_id] = DoseIsocontourState()
        return self._states[image_id]

    def get_isocontour_cache_token(self, viewer=None) -> Any:
        is_active, _, _, _, target_id, _ = self.get_dose_target_info(viewer)
        if not is_active or not target_id:
            return None
        state = self.get_isocontour_state(target_id)
        if not state.is_enabled and not state.colorwash_enabled:
            return (target_id, False)
        levels_tuple = tuple(
            (lvl.value, lvl.enabled, tuple(lvl.color), lvl.thickness)
            for lvl in state.levels
        )
        scaling_state = None
        if self._ui and hasattr(self._ui, "scaling_comp"):
            sc = self._ui.scaling_comp.get_state(target_id)
            scaling_state = (sc.norm_mode, sc.scaling_factor, sc.norm_target_value, sc.norm_roi_id)
        return (
            target_id,
            state.is_enabled,
            state.colorwash_enabled,
            state.colorwash_opacity,
            state.subpixel_accurate,
            levels_tuple,
            scaling_state,
            self._cache_version,
        )

    @staticmethod
    def is_dose_unit(unit: Optional[str]) -> bool:
        if not unit:
            return False
        return str(unit).strip().lower() in DOSE_UNITS

    def get_colorwash_bands(
        self, image_id: Optional[str], is_overlay: bool = False
    ) -> Optional[List[Tuple[float, List[float]]]]:
        if not image_id:
            return None
        state = self._states.get(str(image_id))
        if not state or not state.colorwash_enabled:
            return None

        vols = self._api.get_volumes() if self._api else {}
        vol = vols.get(image_id) or vols.get(str(image_id))
        if not vol:
            return None

        unit_str = getattr(vol, "unit", "") or ""
        if not self.is_dose_unit(unit_str):
            is_active, _, _, _, target_id, _ = self.get_dose_target_info()
            if not is_active or str(target_id) != str(image_id):
                return None

        bands = []
        op = 1.0 if is_overlay else float(state.colorwash_opacity)
        for lvl in state.levels:
            if not lvl.enabled:
                continue
            raw_thr = self.compute_raw_threshold_for_level(lvl, vol, is_overlay, str(image_id))
            col = [
                lvl.color[0] / 255.0,
                lvl.color[1] / 255.0,
                lvl.color[2] / 255.0,
                op,
            ]
            bands.append((raw_thr, col))

        if not bands:
            return None

        bands.sort(key=lambda x: x[0])
        return bands

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui: "DosePluginUI") -> None:
        self._ui = ui

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def get_dose_target_info(
        self, viewer=None
    ) -> Tuple[bool, Any, bool, Optional[str], Optional[str], Optional[Any]]:
        """
        Evaluates the active viewer (or provided viewer) to identify the dose target image and its ViewState.
        Returns:
            (is_active, target_volume, is_overlay, unit_string, target_id, target_vs)
        Priority:
            1. Fused overlay image if unit in {'gy', 'mgy', 'gy/decay'} or 'dose' in name/path.
            2. Base image if unit in {'gy', 'mgy', 'gy/decay'} or 'dose' in name/path.
            3. Fallback (inactive): overlay if present, else base.
        """
        if not self._api:
            return False, None, False, None, None, None

        if viewer is None:
            viewer = self._api.get_active_viewer()
        if not viewer or not viewer.volume:
            return False, None, False, None, None, None

        base_vol = viewer.volume
        base_id = getattr(viewer, "image_id", None)
        base_vs = viewer.view_state
        base_unit = getattr(base_vol, "unit", None)
        base_unit_str = str(base_unit).strip() if base_unit else None

        def is_dose_vol(vol, unit_str):
            if unit_str and unit_str.lower() in DOSE_UNITS:
                return True
            if vol:
                name = (getattr(vol, "name", "") or "").lower()
                first_path = vol.file_paths[0].lower() if (getattr(vol, "file_paths", None) and len(vol.file_paths) > 0) else ""
                if "dose" in name or "dose" in first_path:
                    return True
            return False

        # 1. Check fused overlay first
        if base_vs and base_vs.display.overlay:
            ov_id = base_vs.display.overlay.image_id
            if ov_id:
                vols = self._api.get_volumes()
                ov_vol = vols.get(ov_id) or vols.get(str(ov_id))
                view_states = self._api.get_view_states()
                ov_vs = view_states.get(ov_id) or view_states.get(str(ov_id))
                if ov_vol:
                    ov_unit = getattr(ov_vol, "unit", None)
                    ov_unit_str = str(ov_unit).strip() if ov_unit else None
                    if is_dose_vol(ov_vol, ov_unit_str):
                        if not ov_unit_str or ov_unit_str.lower() not in DOSE_UNITS:
                            ov_vol.unit = "Gy"
                            ov_unit_str = "Gy"
                        return True, ov_vol, True, ov_unit_str, str(ov_id), ov_vs

        # 2. Check base image
        if is_dose_vol(base_vol, base_unit_str):
            if not base_unit_str or base_unit_str.lower() not in DOSE_UNITS:
                base_vol.unit = "Gy"
                base_unit_str = "Gy"
            return True, base_vol, False, base_unit_str, str(base_id) if base_id is not None else None, base_vs

        # 3. Fallback inactive target (overlay if present, else base)
        if base_vs and base_vs.display.overlay:
            ov_id = base_vs.display.overlay.image_id
            if ov_id:
                vols = self._api.get_volumes()
                ov_vol = vols.get(ov_id) or vols.get(str(ov_id))
                view_states = self._api.get_view_states()
                ov_vs = view_states.get(ov_id) or view_states.get(str(ov_id))
                if ov_vol:
                    ov_unit = getattr(ov_vol, "unit", None)
                    return False, ov_vol, True, str(ov_unit) if ov_unit else None, str(ov_id), ov_vs

        return False, base_vol, False, base_unit_str, str(base_id) if base_id is not None else None, base_vs

    def get_dose_status(self) -> Tuple[bool, Any, bool, Optional[str]]:
        """Backwards compatible status accessor."""
        is_active, target_vol, is_ov, unit_str, _, _ = self.get_dose_target_info()
        return is_active, target_vol, is_ov, unit_str

    def on_enable_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        """Sets unit to 'Gy' on the target volume and updates UI."""
        if not self._api:
            return

        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.volume:
            return

        target_vol = None
        if viewer.view_state and viewer.view_state.display.overlay:
            ov_id = viewer.view_state.display.overlay.image_id
            if ov_id:
                target_vol = self._api.get_volumes().get(ov_id)

        if target_vol is None:
            target_vol = viewer.volume

        if target_vol:
            target_vol.unit = "Gy"
            target_vol.unit_source = "modified, unsaved"
            target_vol._is_outdated = True

            for v in self._api.get_viewers().values():
                v.is_geometry_dirty = True
                v.drawer._last_leg_state = None
                if getattr(v, "show_legend", False):
                    v.drawer.draw_legend()

            self._api.request_refresh()



    def go_to_max(self) -> None:
        """Finds the maximum dose voxel in the active target volume and centers crosshair and camera on it."""
        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_vol or not self._api:
            return

        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return

        arr = target_vol.data
        if arr is None or arr.size == 0:
            return

        if arr.ndim == 4 and not getattr(target_vol, "is_rgb", False):
            t_idx = min(getattr(viewer.view_state.camera, "time_idx", 0), arr.shape[0] - 1)
            arr_3d = arr[t_idx]
        else:
            arr_3d = arr

        try:
            if np.isnan(arr_3d).any():
                idx_flat = int(np.nanargmax(arr_3d))
            else:
                idx_flat = int(np.argmax(arr_3d))
            z_idx, y_idx, x_idx = np.unravel_index(idx_flat, arr_3d.shape)
        except Exception:
            return

        if getattr(target_vol, "sitk_image", None):
            try:
                phys = target_vol.sitk_image.TransformIndexToPhysicalPoint([int(x_idx), int(y_idx), int(z_idx)])
                phys_coord = np.array(phys[:3], dtype=np.float64)
            except Exception:
                phys_coord = target_vol.voxel_coord_to_physic_coord(np.array([float(x_idx), float(y_idx), float(z_idx)]))
        else:
            phys_coord = target_vol.voxel_coord_to_physic_coord(np.array([float(x_idx), float(y_idx), float(z_idx)]))

        vs = viewer.view_state
        vs.camera.target_center = phys_coord
        vs.update_crosshair_from_phys(phys_coord)

        base_id = getattr(viewer, "image_id", None)
        if base_id and hasattr(self._api, "propagate_sync"):
            self._api.propagate_sync(base_id)

        self._api.request_refresh()
        if hasattr(self._api, "update_sidebar_crosshair"):
            self._api.update_sidebar_crosshair(viewer)

    def get_reference_dose(self, target_vol, is_overlay: bool, target_id: str) -> float:
        """Computes reference dose value (in physical/raw Gy) for the active target volume."""
        if not target_vol:
            return 1.0

        sc_state = None
        if self._ui and hasattr(self._ui, "scaling_comp"):
            sc_state = self._ui.scaling_comp.get_state(target_id)

        if not sc_state or not sc_state.norm_mode:
            # Absolute mode: reference is 1.0 Gy (or 100% of max)
            try:
                rng = target_vol.get_data_range()
                return float(rng[1]) if rng and len(rng) == 2 and rng[1] > 0 else 1.0
            except Exception:
                return 1.0

        if sc_state.norm_mode == "Max":
            try:
                rng = target_vol.get_data_range()
                return float(rng[1]) if rng and len(rng) == 2 and rng[1] > 0 else 1.0
            except Exception:
                return 1.0
        elif sc_state.norm_mode in ("Target Value", "Ref Value", "Prescription"):
            v_ref = float(sc_state.norm_target_value)
            user_s = float(sc_state.scaling_factor) if sc_state.scaling_factor != 0 else 1.0
            return (v_ref / user_s) if user_s != 0 else v_ref
        elif sc_state.norm_mode == "ROI Mean":
            if self._ui and hasattr(self._ui, "scaling_comp"):
                mean_val = self._ui.scaling_comp.compute_roi_mean(target_vol, is_overlay, sc_state.norm_roi_id)
                return mean_val if mean_val > 0 else 1.0
            return 1.0

        return 1.0

    def compute_raw_threshold_for_level(
        self, level: DoseIsocontourLevel, target_vol, is_overlay: bool, target_id: str
    ) -> float:
        """
        Converts the isodose level value (%) to raw voxel threshold:
        raw_threshold = (level.value / 100.0) * D_ref
        where D_ref is determined by get_reference_dose() (Prescription, Max, ROI Mean, or raw Max).
        """
        d_ref = self.get_reference_dose(target_vol, is_overlay, target_id)
        raw_thr = float((level.value / 100.0) * d_ref)
        try:
            rng = target_vol.get_data_range()
            raw_max = float(rng[1]) if rng and len(rng) == 2 else None
            if raw_max is not None and abs(level.value - 100.0) < 1e-3 and abs(raw_thr - raw_max) < 1e-3 * abs(raw_max):
                # Nudge 100% level slightly below absolute peak so marching squares
                # finds the closed contour enclosing the maximum voxel(s)
                raw_thr = raw_max * 0.999
        except Exception:
            pass
        return raw_thr

    def _sync_isocontour_rois(self, target_id: str, target_vs, state: DoseIsocontourState) -> Dict[int, ContourROI]:
        """Ensures ContourROI instances exist in target_vs.contours matching state.levels."""
        if not self._api:
            return {}

        if target_id not in self._contour_rois:
            self._contour_rois[target_id] = {}
        rois_map = self._contour_rois[target_id]

        if not state.is_enabled:
            # Remove all isocontour ROIs from ViewState
            for idx, c_roi in list(rois_map.items()):
                if c_roi.id and hasattr(target_vs, "contours") and c_roi.id in target_vs.contours:
                    self._api.remove_contour(target_id, c_roi.id)
            rois_map.clear()
            return {}

        # Remove extra indices if levels were deleted
        current_indices = set(range(len(state.levels)))
        for idx in list(rois_map.keys()):
            if idx not in current_indices:
                c_roi = rois_map.pop(idx)
                if c_roi.id and hasattr(target_vs, "contours") and c_roi.id in target_vs.contours:
                    self._api.remove_contour(target_id, c_roi.id)

        # Update or create ContourROI for each level
        for idx, lvl in enumerate(state.levels):
            name = f"Isodose {lvl.value:g}%"
            if idx not in rois_map:
                c_roi = ContourROI(name=name, color=list(lvl.color), thickness=lvl.thickness)
                c_roi.is_dose_isocontour = True
                c_roi.visible = lvl.enabled
                self._api.add_contour(target_id, c_roi)
                rois_map[idx] = c_roi
            else:
                c_roi = rois_map[idx]
                c_roi.name = name
                c_roi.color = list(lvl.color)
                c_roi.thickness = lvl.thickness
                c_roi.visible = lvl.enabled
                if not hasattr(target_vs, "contours") or c_roi.id not in target_vs.contours:
                    self._api.add_contour(target_id, c_roi)

        return rois_map

    def clear_isocontours(self, target_id: str, target_vs) -> None:
        """Removes all dose isocontours for the given target."""
        if not self._api or not target_vs:
            return
        rois_map = self._contour_rois.pop(target_id, {})
        for c_roi in rois_map.values():
            if c_roi.id and hasattr(target_vs, "contours") and c_roi.id in target_vs.contours:
                self._api.remove_contour(target_id, c_roi.id)

    def invalidate_isocontour_cache(self) -> None:
        """Invalidates all cached isocontour slice polygons across all targets."""
        self._cache_version += 1
        for rois_map in self._contour_rois.values():
            for c_roi in rois_map.values():
                c_roi.invalidate()

    def update_isocontours(self, viewer) -> None:
        """Computes missing isocontour slice polygons on the fly during slice rendering."""
        if not self._api or not viewer or not viewer.view_state:
            return

        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info(viewer)
        if not is_active or not target_vol or not target_id or not target_vs:
            return

        # The viewer must be showing the target image (either as base or as fused overlay)
        v_img_id = str(viewer.image_id) if viewer.image_id is not None else ""
        t_img_id = str(target_id)
        ov_img_id = str(getattr(viewer.view_state.display.overlay, "image_id", None) or "")
        if v_img_id != t_img_id and ov_img_id != t_img_id:
            return

        state = self.get_isocontour_state(target_id)
        if not state.is_enabled:
            return

        rois_map = self._sync_isocontour_rois(target_id, target_vs, state)
        if not rois_map:
            return

        time_idx = 0
        cam = getattr(target_vs, "camera", None)
        if cam is not None and isinstance(getattr(cam, "time_idx", None), (int, np.integer)):
            time_idx = int(cam.time_idx)

        # Extract 2D slice data from the dose target volume
        slice_data = None
        data_token = None
        if is_overlay:
            # Resampled overlay data matching base geometry
            base_vs = viewer.view_state
            ov_data = getattr(base_vs.display, "overlay_data", None)
            if isinstance(ov_data, np.ndarray):
                data_token = id(ov_data)
                slice_data = SliceRenderer.get_raw_slice(
                    ov_data, False, time_idx, viewer.slice_idx, viewer.orientation
                )
            elif isinstance(target_vol.data, np.ndarray):
                data_token = id(target_vol.data)
                slice_data = SliceRenderer.get_raw_slice(
                    target_vol.data, False, time_idx, viewer.slice_idx, viewer.orientation
                )
        else:
            display_data = getattr(target_vs, "base_display_data", None)
            if not isinstance(display_data, np.ndarray):
                display_data = target_vol.data
            if isinstance(display_data, np.ndarray):
                data_token = id(display_data)
                slice_data = SliceRenderer.get_raw_slice(
                    display_data, False, time_idx, viewer.slice_idx, viewer.orientation
                )

        if slice_data is None or slice_data.size == 0:
            return

        sw, sh = viewer.volume.get_physical_aspect_ratio(viewer.orientation)
        ori = viewer.orientation
        s_idx = viewer.slice_idx

        # Compute each enabled level
        c_max = np.max(slice_data) if slice_data.size > 0 else 0.0

        for idx, lvl in enumerate(state.levels):
            c_roi = rois_map.get(idx)
            if not c_roi or not lvl.enabled:
                if c_roi:
                    c_roi.polygons[ori][s_idx] = []
                continue

            raw_thr = self.compute_raw_threshold_for_level(lvl, target_vol, is_overlay, target_id)

            # Check if threshold value, subpixel, or data array changed
            if (
                getattr(c_roi, "last_computed_level", None) != raw_thr
                or getattr(c_roi, "last_computed_subpixel", None) != state.subpixel_accurate
                or getattr(c_roi, "last_computed_data_token", None) != data_token
            ):
                c_roi.invalidate()
                c_roi.last_computed_level = raw_thr
                c_roi.last_computed_subpixel = state.subpixel_accurate
                c_roi.last_computed_data_token = data_token

            if s_idx in c_roi.polygons[ori]:
                continue

            if c_max >= raw_thr:
                if state.subpixel_accurate:
                    c_roi.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                        slice_data, raw_thr, sw, sh
                    )
                else:
                    mask = (slice_data >= raw_thr).astype(np.uint8)
                    if np.any(mask):
                        c_roi.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                            mask, 0.5, sw, sh
                        )
                    else:
                        c_roi.polygons[ori][s_idx] = []
            else:
                c_roi.polygons[ori][s_idx] = []

    # -------------------------------------------------------------
    # UI Interaction Callbacks for Isocontours
    # -------------------------------------------------------------
    def on_toggle_isocontours(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, _, _, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_id:
            return
        state = self.get_isocontour_state(target_id)
        state.is_enabled = bool(app_data)
        if not state.is_enabled:
            self.clear_isocontours(target_id, target_vs)
        self.invalidate_isocontour_cache()
        self._refresh_all_viewers()

    def on_toggle_subpixel(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, _, _, _, target_id, _ = self.get_dose_target_info()
        if not is_active or not target_id:
            return
        state = self.get_isocontour_state(target_id)
        state.subpixel_accurate = bool(app_data)
        self.invalidate_isocontour_cache()
        self._refresh_all_viewers()

    def on_toggle_shading(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_id:
            return
        state = self.get_isocontour_state(target_id)
        state.colorwash_enabled = bool(app_data)
        self.invalidate_isocontour_cache()
        if target_vs:
            target_vs.is_data_dirty = True
        if self._ui and hasattr(self._ui, "_t"):
            slider_tag = self._ui._t("slider_shading_opacity")
            if dpg.does_item_exist(slider_tag):
                dpg.configure_item(slider_tag, enabled=is_overlay or state.colorwash_enabled)
        self._refresh_all_viewers()

    def on_shading_opacity_changed(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_id or app_data is None:
            return
        try:
            val = max(0.0, min(1.0, float(app_data)))
        except (ValueError, TypeError):
            return

        state = self.get_isocontour_state(target_id)
        state.colorwash_opacity = val

        if is_overlay and self._api:
            for v in self._api.get_viewers().values():
                if v.view_state and v.view_state.display.overlay:
                    if str(v.view_state.display.overlay.image_id) == str(target_id):
                        v.view_state.display.overlay.opacity = val
                        v.view_state.is_data_dirty = True
                if hasattr(v, "drawer") and hasattr(v.drawer, "_last_leg_state"):
                    v.drawer._last_leg_state = None
                if hasattr(v, "update_render"):
                    v.update_render(force_reblend=False)

            if dpg.does_item_exist("slider_fusion_opacity") and not dpg.is_item_active("slider_fusion_opacity"):
                dpg.set_value("slider_fusion_opacity", val)

            active_v = self._api.get_active_viewer()
            if active_v and active_v.image_id is not None:
                if hasattr(self._api, "propagate_overlay_opacity"):
                    self._api.propagate_overlay_opacity(active_v.image_id)

            self._api.request_refresh()
            return

        if target_vs:
            target_vs.is_data_dirty = True
        self._refresh_all_viewers()

    def on_level_enabled_toggle(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, _, _, _, target_id, _ = self.get_dose_target_info()
        if not is_active or not target_id or user_data is None:
            return
        idx = int(user_data)
        state = self.get_isocontour_state(target_id)
        if 0 <= idx < len(state.levels):
            state.levels[idx].enabled = bool(app_data)
            rois_map = self._contour_rois.get(target_id, {})
            if idx in rois_map:
                rois_map[idx].visible = state.levels[idx].enabled
            self.invalidate_isocontour_cache()
            self._refresh_all_viewers()

    def on_level_value_changed(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, _, _, _, target_id, _ = self.get_dose_target_info()
        if not is_active or not target_id or user_data is None or app_data is None:
            return
        idx = int(user_data)
        try:
            val = float(app_data)
        except (ValueError, TypeError):
            return
        state = self.get_isocontour_state(target_id)
        if 0 <= idx < len(state.levels):
            state.levels[idx].value = val
            rois_map = self._contour_rois.get(target_id, {})
            if idx in rois_map:
                rois_map[idx].name = f"Isodose {val:g}%"
            self.invalidate_isocontour_cache()
            self._refresh_all_viewers()

    def on_level_color_changed(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, _, _, _, target_id, _ = self.get_dose_target_info()
        if not is_active or not target_id or user_data is None or not app_data:
            return
        from vvv.ui.ui_components import normalize_rgba_to_int
        idx = int(user_data)
        state = self.get_isocontour_state(target_id)
        if 0 <= idx < len(state.levels):
            col = normalize_rgba_to_int(app_data)
            state.levels[idx].color = col
            rois_map = self._contour_rois.get(target_id, {})
            if idx in rois_map:
                rois_map[idx].color = list(col)
            self.invalidate_isocontour_cache()
            self._refresh_all_viewers()

    def on_dose_threshold_toggle(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, target_vol, is_overlay, current_unit, target_id, target_vs = (
            self.get_dose_target_info()
        )
        if not is_active or not target_vs or not target_id:
            return

        is_enabled = bool(app_data)
        if is_enabled:
            val = dpg.get_value(self._t("drag_dose_threshold"))
            target_vs.display.min_threshold = float(val) if val is not None else 0.0
        else:
            target_vs.display.min_threshold = None

        target_vs.is_data_dirty = True
        if self._api:
            viewer = self._api.get_active_viewer()
            if viewer and viewer.view_state:
                viewer.view_state.is_data_dirty = True
            self._api.update_all_viewers_of_image(target_id)
            self._api.request_refresh()

    def on_dose_threshold_changed(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, target_vol, is_overlay, current_unit, target_id, target_vs = (
            self.get_dose_target_info()
        )
        if not is_active or not target_vs or not target_id or app_data is None:
            return

        try:
            val = float(app_data)
        except (ValueError, TypeError):
            return

        target_vs.display.min_threshold = val
        if dpg.does_item_exist(self._t("check_dose_threshold")):
            dpg.set_value(self._t("check_dose_threshold"), True)

        target_vs.is_data_dirty = True
        if self._api:
            viewer = self._api.get_active_viewer()
            if viewer and viewer.view_state:
                viewer.view_state.is_data_dirty = True
            self._api.update_all_viewers_of_image(target_id)
            self._api.request_refresh()

    def on_step_button_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        if not user_data or not isinstance(user_data, dict):
            return
        target_tag = user_data.get("tag")
        direction = user_data.get("dir", 1.0)
        if not target_tag or not dpg.does_item_exist(target_tag):
            return

        is_active, target_vol, is_overlay, current_unit, target_id, target_vs = (
            self.get_dose_target_info()
        )
        step_size = 1.0
        if target_vs and hasattr(target_vs.display, "ww") and target_vs.display.ww > 0:
            step_size, _, _ = compute_adaptive_step_and_speed(target_vs.display.ww)
        elif target_vol:
            rng = target_vol.get_data_range()
            if rng and rng[1] > rng[0]:
                step_size, _, _ = compute_adaptive_step_and_speed(rng[1] - rng[0])

        current_val = dpg.get_value(target_tag) or 0.0
        new_val = current_val + (step_size * direction)
        dpg.set_value(target_tag, new_val)

        if target_tag == self._t("drag_dose_threshold"):
            self.on_dose_threshold_changed(sender, new_val, user_data)

    def on_delete_level_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, _, _, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_id or user_data is None:
            return
        idx = int(user_data)
        state = self.get_isocontour_state(target_id)
        if 0 <= idx < len(state.levels):
            state.levels.pop(idx)
            self.clear_isocontours(target_id, target_vs)
            self.invalidate_isocontour_cache()
            if self._ui:
                self._ui.rebuild_levels_ui(self._api)
            self._refresh_all_viewers()

    def on_reset_levels_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        is_active, _, _, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_id:
            return
        state = self.get_isocontour_state(target_id)
        state.levels = [
            DoseIsocontourLevel(val, list(col), True, 1.5)
            for val, col in DEFAULT_ISODOSE_LEVELS
        ]
        self.clear_isocontours(target_id, target_vs)
        self.invalidate_isocontour_cache()
        if self._ui:
            self._ui.rebuild_levels_ui(self._api)
        self._refresh_all_viewers()

    def _refresh_all_viewers(self) -> None:
        if not self._api:
            return
        viewers = self._api.get_viewers() if hasattr(self._api, "get_viewers") else {}
        for v in viewers.values():
            v.is_geometry_dirty = True
            v.is_viewer_data_dirty = True
            if getattr(v, "view_state", None):
                v.view_state.is_data_dirty = True
            if hasattr(v, "drawer") and hasattr(v.drawer, "_last_contour_image"):
                v.drawer._last_contour_image = None
            if hasattr(v, "drawer") and hasattr(v.drawer, "_last_leg_state"):
                v.drawer._last_leg_state = None
            if hasattr(v, "update_render"):
                v.update_render(force_reblend=True)
        self._api.request_refresh()

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        self._states.pop(image_id, None)
        self._contour_rois.pop(image_id, None)
        if self._ui and hasattr(self._ui, "dvh_win") and self._ui.dvh_win:
            if dpg.does_item_exist(self._ui.dvh_win.window_tag):
                is_active, dose_vol, _, _, target_id, _ = self.get_dose_target_info()
                if not is_active or not dose_vol or target_id == image_id:
                    self._ui.dvh_win.on_window_close()
                else:
                    self._ui.dvh_win.recompute_and_update(fit_axes=False)

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        state = self._states.get(image_id)
        scaling_data = None
        if self._ui and hasattr(self._ui, "scaling_comp"):
            scaling_data = self._ui.scaling_comp.serialize_state(image_id)

        res = {}
        if state:
            res["is_enabled"] = state.is_enabled
            res["colorwash_enabled"] = state.colorwash_enabled
            res["colorwash_opacity"] = state.colorwash_opacity
            res["subpixel_accurate"] = state.subpixel_accurate
            res["levels"] = [
                {
                    "value": lvl.value,
                    "color": list(lvl.color),
                    "enabled": lvl.enabled,
                    "thickness": lvl.thickness,
                }
                for lvl in state.levels
            ]
        if scaling_data:
            res["scaling"] = scaling_data

        return res

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        if not data:
            return
        levels_data = data.get("levels", [])
        if levels_data or "is_enabled" in data or "colorwash_enabled" in data:
            levels = [
                DoseIsocontourLevel(
                    value=float(ld.get("value", 100.0)),
                    color=list(ld.get("color", [255, 0, 0, 255])),
                    enabled=bool(ld.get("enabled", True)),
                    thickness=float(ld.get("thickness", 1.5)),
                )
                for ld in levels_data
            ]
            self._states[image_id] = DoseIsocontourState(
                is_enabled=bool(data.get("is_enabled", True)),
                colorwash_enabled=bool(data.get("colorwash_enabled", False)),
                colorwash_opacity=float(data.get("colorwash_opacity", 0.5)),
                subpixel_accurate=bool(data.get("subpixel_accurate", True)),
                levels=levels,
            )

        scaling_data = data.get("scaling")
        if scaling_data and self._ui and hasattr(self._ui, "scaling_comp"):
            target_vol = None
            if self._api:
                target_vol = self._api.get_volumes().get(image_id)
            self._ui.scaling_comp.restore_state(image_id, scaling_data, target_vol=target_vol)

        self.invalidate_isocontour_cache()
        if self._ui:
            self._ui.rebuild_levels_ui(self._api)
        self._refresh_all_viewers()

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        if self._ui and hasattr(self._ui, "dvh_win") and self._ui.dvh_win:
            self._ui.dvh_win.on_window_close()
        if self._api:
            for target_id, rois_map in list(self._contour_rois.items()):
                target_vs = self._api.get_view_states().get(target_id)
                if target_vs:
                    self.clear_isocontours(target_id, target_vs)
        self._states.clear()
        self._contour_rois.clear()
