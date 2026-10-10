from dataclasses import dataclass
from typing import Optional, Callable, Tuple, Any, Dict
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI
from vvv.ui.ui_components import build_beginner_tooltip, build_help_button, build_section_title


@dataclass
class ScalingState:
    scaling_factor: float = 1.0          # Base user scaling multiplier S
    norm_mode: Optional[str] = None      # None (Absolute), "Max", "Ref Value", "ROI Mean"
    norm_target_value: float = 100.0     # Reference / Prescription value corresponding to 100% (or 1.0)
    norm_scale_type: str = "100 %"       # "100 %" (scale to 100) or "1.0" (scale to 1)
    norm_roi_id: Optional[str] = None    # Target ROI ID for "ROI Mean"


class IntensityScalingComponent:
    """
    Reusable UI & control component for intensity scaling and normalization.
    Shared across Intensity tool (base image), Fusion tool (fusion/overlay image),
    and Dose tool (active dose image).

    Features:
      - Always visible (no collapsing header).
      - Range displayed in clean white text.
      - User scaling factor S (e.g. calibration multiplier) and Prescription / Ref Value
        work together independently:
          S_effective = S_user * (Target_Scale / Prescription).
      - Quick toggling: None (Absolute), Max, Prescription / Ref Value, ROI Mean.
      - Status indicates active mode without repeating the scale factor.
      - Bake button to permanently multiply array in memory.
      - Reset button to restore original scaling.
    """

    def __init__(
        self,
        prefix: str,
        get_target_fn: Callable[[], Tuple[Any, Any, bool, Optional[str], Optional[str]]],
        default_target_value: float = 100.0,
        ref_label: str = "Ref Value",
    ):
        self._prefix = prefix
        self._get_target_fn = get_target_fn
        self._default_target_value = default_target_value
        self._ref_label = ref_label
        self._states: Dict[str, ScalingState] = {}
        self._api: Optional[Any] = None

    def _t(self, tag: str) -> str:
        return f"{self._prefix}_{tag}"

    def _bind_icon_font(self, item) -> None:
        if dpg.does_item_exist("icon_font_tag"):
            dpg.bind_item_font(item, "icon_font_tag")

    def get_state(self, image_id: Optional[str]) -> ScalingState:
        if not image_id:
            return ScalingState(norm_target_value=self._default_target_value)
        if image_id not in self._states:
            self._states[image_id] = ScalingState(norm_target_value=self._default_target_value)
        return self._states[image_id]

    def create_ui(self, parent, api: Any) -> None:
        self._api = api
        cfg_c = self._get_colors(api)

        with dpg.group(parent=parent or 0, tag=self._t("group_root")):
            build_section_title(
                "Intensity Scaling & Normalization",
                cfg_c.get("text_header", [255, 255, 255, 255]),
            )

            # --- 1. Current Scaled Range (White text) ---
            with dpg.group(horizontal=True):
                dpg.add_text("Range:", color=cfg_c["text_dim"])
                dpg.add_text("[---, ---]", tag=self._t("text_range"), color=[255, 255, 255, 255])
            build_beginner_tooltip(
                self._t("text_range"),
                "Current voxel intensity range including the active scale factor.",
                api,
            )

            dpg.add_spacer(height=3)

            # --- 2. Scale Factor Input (No +- buttons, no multipliers) ---
            dpg.add_text("Scale factor:", color=cfg_c["text_dim"])
            inp_s = dpg.add_input_float(
                tag=self._t("input_scale_factor"),
                default_value=1.0,
                step=0.0,
                step_fast=0.0,
                format="%.4g",
                width=-1,
                callback=self._on_scale_factor_changed,
            )
            build_beginner_tooltip(
                inp_s,
                "User multiplier S: scales raw image values.\n"
                "Works independently with prescription dose for relative normalization.",
                api,
            )

            dpg.add_spacer(height=4)

            # --- 3. Normalization Controls ---
            dpg.add_text("Normalize:", color=cfg_c["text_dim"])
            with dpg.group(horizontal=True):
                b_none = dpg.add_button(
                    label="None",
                    tag=self._t("btn_norm_none"),
                    width=46,
                    callback=self._on_norm_none_clicked,
                )
                build_beginner_tooltip(b_none, "Display absolute values (Gy, mGy) using user scale factor.", api)

                b_max = dpg.add_button(
                    label="Max",
                    tag=self._t("btn_norm_max"),
                    width=46,
                    callback=self._on_norm_max_clicked,
                )
                build_beginner_tooltip(b_max, "Relative normalization: peak voxel equals 100%.", api)

                b_goto_max = dpg.add_button(
                    label="\uf05b",
                    tag=self._t("btn_goto_max"),
                    width=20,
                    callback=self._on_goto_max_clicked,
                )
                self._bind_icon_font(b_goto_max)
                build_beginner_tooltip(
                    b_goto_max,
                    "Go to Max: Center crosshair and camera on maximum dose voxel.",
                    api,
                )

                b_roi = dpg.add_button(
                    label="ROI Mean",
                    tag=self._t("btn_norm_roi"),
                    width=75,
                    enabled=False,
                    callback=self._on_norm_roi_clicked,
                )
                build_beginner_tooltip(b_roi, "Relative normalization: mean inside ROI equals 100%.", api)

            # Prescription / Reference Value row below
            dpg.add_spacer(height=2)
            with dpg.group(horizontal=True):
                b_val = dpg.add_button(
                    label=self._ref_label,
                    tag=self._t("btn_norm_val"),
                    width=90,
                    callback=self._on_norm_val_clicked,
                )
                build_beginner_tooltip(
                    b_val,
                    f"Relative normalization: specified {self._ref_label.lower()} equals 100%.",
                    api,
                )

            # Sub-panel for Prescription / Ref Value input
            with dpg.group(tag=self._t("group_norm_val"), show=False):
                dpg.add_spacer(height=2)
                with dpg.group(horizontal=True):
                    dpg.add_text(
                        f"{self._ref_label}:",
                        tag=self._t("label_norm_val"),
                        color=cfg_c["text_dim"],
                    )
                    inp_val = dpg.add_input_float(
                        tag=self._t("input_norm_val"),
                        default_value=self._default_target_value,
                        format="%.4g",
                        step=0.0,
                        step_fast=0.0,
                        width=-1,
                        callback=self._on_norm_val_changed,
                    )
                    build_beginner_tooltip(
                        inp_val,
                        f"Target {self._ref_label.lower()} value corresponding to 100% relative dose.",
                        api,
                    )

            # Sub-panel for ROI Mean
            with dpg.group(tag=self._t("group_norm_roi"), show=False):
                dpg.add_spacer(height=2)
                dpg.add_text("Target ROI:", color=cfg_c["text_dim"])
                dpg.add_combo(
                    items=["(None)"],
                    default_value="(None)",
                    tag=self._t("combo_norm_roi"),
                    width=-1,
                    callback=self._on_norm_roi_changed,
                )
                dpg.add_text(
                    "ROI Mean: ---",
                    tag=self._t("text_roi_mean"),
                    color=[255, 255, 255, 255],
                )

            dpg.add_spacer(height=3)
            with dpg.group(horizontal=True):
                dpg.add_text("Status:", color=cfg_c["text_dim"])
                dpg.add_text("Absolute", tag=self._t("text_norm_status"), color=cfg_c["text_dim"])

            # --- 4. Actions: Bake & Reset (No horizontal line) ---
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                btn_bake = dpg.add_button(
                    label="Bake",
                    tag=self._t("btn_bake"),
                    callback=self._on_bake_clicked,
                )
                build_beginner_tooltip(
                    btn_bake,
                    "Permanently multiplies the voxel array in memory by the effective scale factor\n"
                    "and resets virtual scaling to 1.0 (for export/saving).",
                    api,
                )
                btn_reset = dpg.add_button(
                    label="Reset",
                    tag=self._t("btn_reset"),
                    callback=self._on_reset_clicked,
                )
                build_beginner_tooltip(
                    btn_reset,
                    "Resets scale factor to 1.0 and unselects normalization.",
                    api,
                )

    # -------------------------------------------------------------
    # Logic & Calculations
    # -------------------------------------------------------------
    def _get_colors(self, api: Any) -> Dict[str, Any]:
        if hasattr(api, "get_ui_config"):
            return api.get_ui_config().get("colors", {})
        if hasattr(api, "ui_cfg"):
            return api.ui_cfg.get("colors", {})
        return {
            "text_dim": [150, 150, 150, 255],
            "text_active": [255, 255, 255, 255],
            "text_header": [255, 255, 255, 255],
            "warning": [255, 180, 50, 255],
        }

    def _get_active_viewer(self):
        if not self._api:
            return None
        if hasattr(self._api, "get_active_viewer"):
            return self._api.get_active_viewer()
        return getattr(self._api, "context_viewer", None)

    def _get_volumes(self):
        if not self._api:
            return {}
        if hasattr(self._api, "get_volumes"):
            return self._api.get_volumes()
        ctrl = getattr(self._api, "controller", None)
        return getattr(ctrl, "volumes", {}) if ctrl else {}

    def _get_viewers(self):
        if not self._api:
            return {}
        if hasattr(self._api, "get_viewers"):
            return self._api.get_viewers()
        ctrl = getattr(self._api, "controller", None)
        return getattr(ctrl, "viewers", {}) if ctrl else {}

    def _refresh(self):
        if not self._api:
            return

        viewers = self._get_viewers()
        for v in viewers.values():
            v.is_geometry_dirty = True
            if hasattr(v, "drawer"):
                v.drawer._last_leg_state = None
                if getattr(v, "show_legend", False):
                    v.drawer.draw_legend()

        if hasattr(self._api, "request_refresh"):
            self._api.request_refresh()
        elif hasattr(self._api, "request_render"):
            self._api.request_render()

    def compute_roi_mean(self, target_vol, is_overlay: bool, roi_id: Optional[str]) -> float:
        """Computes mean raw voxel value inside the specified ROI."""
        if not target_vol or not roi_id:
            return 0.0

        viewer = self._get_active_viewer()
        if not viewer or not viewer.view_state:
            return 0.0

        volumes = self._get_volumes()
        roi_vol = volumes.get(roi_id)
        if not roi_vol or roi_vol.data is None:
            return 0.0

        mask = roi_vol.data > 0
        if not np.any(mask):
            return 0.0

        target_data = None
        if is_overlay:
            target_data = viewer.view_state.display.overlay_data
            if target_data is None:
                target_data = target_vol.data
        else:
            target_data = target_vol.data

        if target_data is None:
            return 0.0

        num_tp = getattr(target_vol, "num_timepoints", 1)
        if isinstance(num_tp, int) and num_tp > 1:
            t = min(viewer.view_state.camera.time_idx, target_data.shape[0] - 1)
            target_data = target_data[t]
        elif target_data.ndim == 4 and not getattr(target_vol, "is_rgb", False):
            target_data = target_data[0]

        roi_bbox = getattr(roi_vol, "roi_bbox", None)
        if roi_bbox is not None and isinstance(roi_bbox, (list, tuple, np.ndarray)) and len(roi_bbox) == 6:
            z0, z1, y0, y1, x0, x1 = roi_bbox
            if z0 != z1:
                target_data = target_data[z0:z1, y0:y1, x0:x1]

        if target_data.shape == mask.shape:
            pixels = target_data[mask]
            if pixels.size > 0:
                return float(np.mean(pixels))
        return 0.0

    def compute_effective_scaling_factor(
        self, target_vol, is_overlay: bool, state: ScalingState
    ) -> float:
        """Computes the effective multiplier S applied to raw voxel data.

        Prescription works together with user scaling:
          V_phys = S_user * V_raw
          V_rel = (V_phys / Prescription) * Target_Scale
          S_effective = S_user * (Target_Scale / Prescription).
        """
        if not target_vol:
            return 1.0

        user_s = float(state.scaling_factor)
        if user_s == 0.0 or np.isnan(user_s):
            user_s = 1.0

        if not state.norm_mode:
            return user_s

        target_scale = 100.0

        if state.norm_mode == "Max":
            try:
                rng = target_vol.get_data_range()
                raw_max = float(rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else 1.0
            except Exception:
                raw_max = 1.0
            if raw_max != 0.0 and not np.isnan(raw_max):
                return float(target_scale / raw_max)
            return user_s

        elif state.norm_mode in ("Target Value", "Ref Value", "Prescription"):
            v_ref = float(state.norm_target_value)
            if v_ref != 0.0 and not np.isnan(v_ref):
                # Works independently with user scaling value
                return float(user_s * target_scale / v_ref)
            return user_s

        elif state.norm_mode == "ROI Mean":
            mean_val = self.compute_roi_mean(target_vol, is_overlay, state.norm_roi_id)
            if mean_val != 0.0 and not np.isnan(mean_val):
                return float(target_scale / mean_val)
            return user_s

        return user_s

    def compute_auto_scaling_factor(
        self, target_vol, is_overlay: bool, state: ScalingState
    ) -> float:
        return self.compute_effective_scaling_factor(target_vol, is_overlay, state)

    def _sync_volume_virtual_scale(self, target_vol, state: ScalingState) -> None:
        """Applies virtual scale_factor and scale_unit to the target VolumeData object."""
        if not target_vol:
            return
        target_vol.scale_factor = self.compute_effective_scaling_factor(
            target_vol, False, state
        )
        target_vol.scale_unit = "%" if state.norm_mode else None

    # -------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------
    def _on_scale_factor_changed(self, sender=None, app_data=None, user_data=None) -> None:
        target_vol, _, _, _, target_id = self._get_target_fn()
        if not target_id or app_data is None:
            return
        try:
            val = float(app_data)
        except (ValueError, TypeError):
            return

        state = self.get_state(target_id)
        state.scaling_factor = val

        # Max and ROI Mean auto-determine S, so manual edit switches them to None (Absolute).
        # Prescription / Ref Value is independent and works WITH user scaling!
        if state.norm_mode in ("Max", "ROI Mean"):
            state.norm_mode = None

        self._sync_volume_virtual_scale(target_vol, state)
        self.update_ui(self._api)
        self._refresh()

    def _set_scale_factor(self, val: float) -> None:
        target_vol, _, _, _, target_id = self._get_target_fn()
        if not target_id:
            return
        state = self.get_state(target_id)
        state.scaling_factor = float(val)
        if state.norm_mode in ("Max", "ROI Mean"):
            state.norm_mode = None
        self._sync_volume_virtual_scale(target_vol, state)
        self.update_ui(self._api)
        self._refresh()

    def _on_goto_max_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        target_vol, _, _, _, target_id = self._get_target_fn()
        if not target_vol or not self._api:
            return
        viewer = self._get_active_viewer()
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

        self._refresh()
        if hasattr(self._api, "update_sidebar_crosshair"):
            self._api.update_sidebar_crosshair(viewer)

    def _on_target_scale_changed(self, sender=None, app_data=None, user_data=None) -> None:
        pass

    def _on_norm_none_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        target_vol, _, _, _, target_id = self._get_target_fn()
        if not target_id or not target_vol:
            return
        state = self.get_state(target_id)
        state.norm_mode = None
        self._sync_volume_virtual_scale(target_vol, state)
        self.update_ui(self._api)
        self._refresh()

    def _on_norm_max_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        target_vol, _, is_ov, _, target_id = self._get_target_fn()
        if not target_id or not target_vol:
            return
        state = self.get_state(target_id)
        state.norm_mode = "Max"
        try:
            rng = target_vol.get_data_range()
            raw_max = float(rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else 1.0
        except Exception:
            raw_max = 1.0
        if raw_max != 0.0 and not np.isnan(raw_max):
            state.scaling_factor = float(100.0 / raw_max)

        self._sync_volume_virtual_scale(target_vol, state)
        self.update_ui(self._api)
        self._refresh()

    def _on_norm_val_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        target_vol, _, is_ov, _, target_id = self._get_target_fn()
        if not target_id or not target_vol:
            return
        state = self.get_state(target_id)
        state.norm_mode = "Ref Value"

        # If reference value is default and image max is available, default to image max
        if state.norm_target_value == 100.0 and self._default_target_value != 100.0:
            state.norm_target_value = float(self._default_target_value)
        elif state.norm_target_value == 100.0 and target_vol:
            try:
                rng = target_vol.get_data_range()
                if isinstance(rng, (tuple, list)) and len(rng) == 2 and float(rng[1]) > 0:
                    state.norm_target_value = float(rng[1])
            except Exception:
                pass

        self._sync_volume_virtual_scale(target_vol, state)
        self.update_ui(self._api)
        self._refresh()

    def _on_norm_val_changed(self, sender=None, app_data=None, user_data=None) -> None:
        target_vol, _, is_ov, _, target_id = self._get_target_fn()
        if not target_id or app_data is None:
            return
        state = self.get_state(target_id)
        try:
            state.norm_target_value = float(app_data)
        except (ValueError, TypeError):
            return
        state.norm_mode = "Ref Value"
        self._sync_volume_virtual_scale(target_vol, state)
        self.update_ui(self._api)
        self._refresh()

    def _on_norm_roi_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        target_vol, _, is_ov, _, target_id = self._get_target_fn()
        if not target_id or not target_vol:
            return
        state = self.get_state(target_id)
        state.norm_mode = "ROI Mean"
        mean_val = self.compute_roi_mean(target_vol, is_ov, state.norm_roi_id)
        if mean_val != 0.0 and not np.isnan(mean_val):
            state.scaling_factor = float(100.0 / mean_val)

        self._sync_volume_virtual_scale(target_vol, state)
        self.update_ui(self._api)
        self._refresh()

    def _on_norm_roi_changed(self, sender=None, app_data=None, user_data=None) -> None:
        target_vol, _, is_ov, _, target_id = self._get_target_fn()
        if not target_id or not app_data:
            return
        state = self.get_state(target_id)
        if app_data == "(None)":
            state.norm_roi_id = None
        else:
            parts = app_data.rsplit(" (", 1)
            if len(parts) == 2 and parts[1].endswith(")"):
                state.norm_roi_id = parts[1][:-1]
            else:
                state.norm_roi_id = app_data

        state.norm_mode = "ROI Mean"
        mean_val = self.compute_roi_mean(target_vol, is_ov, state.norm_roi_id)
        if mean_val != 0.0 and not np.isnan(mean_val):
            state.scaling_factor = float(100.0 / mean_val)

        self._sync_volume_virtual_scale(target_vol, state)
        self.update_ui(self._api)
        self._refresh()
        self.update_ui(self._api)
        self._refresh()

    def _on_bake_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        """Applies the effective scaling factor S permanently to the volume voxel data in memory."""
        target_vol, target_vs, is_ov, _, target_id = self._get_target_fn()
        if not target_vol or target_vol.data is None or not target_id:
            return

        state = self.get_state(target_id)
        s_eff = self.compute_effective_scaling_factor(target_vol, is_ov, state)
        if s_eff == 1.0 or s_eff == 0.0 or np.isnan(s_eff):
            return

        # Track cumulative scaling on volume
        current_cum = getattr(target_vol, "_cumulative_scale", 1.0)
        if not isinstance(current_cum, (int, float)):
            current_cum = 1.0
        target_vol._cumulative_scale = float(current_cum * s_eff)

        # Scale array
        target_vol.data = (target_vol.data * s_eff).astype(np.float32)

        # Invalidate range cache
        if hasattr(target_vol, "_data_range_cache"):
            delattr(target_vol, "_data_range_cache")
        target_vol._is_outdated = True

        # Scale Window / Level proportionally so visual appearance is preserved
        if target_vs and hasattr(target_vs, "display"):
            target_vs.display.ww *= s_eff
            target_vs.display.wl *= s_eff
            if target_vs.display.min_threshold is not None:
                target_vs.display.min_threshold *= s_eff
            target_vs.is_data_dirty = True

        # Reset virtual scaling back to 1.0
        state.scaling_factor = 1.0
        state.norm_mode = None
        target_vol.scale_factor = 1.0
        target_vol.scale_unit = None

        self.update_ui(self._api)
        self._refresh()

    def _on_reset_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        """Resets virtual scaling and restores original voxel values if previously baked."""
        target_vol, target_vs, _, _, target_id = self._get_target_fn()
        if not target_vol or not target_id:
            return

        state = self.get_state(target_id)
        state.scaling_factor = 1.0
        state.norm_mode = None
        target_vol.scale_factor = 1.0
        target_vol.scale_unit = None

        # Revert baked data if array was previously baked
        cum = getattr(target_vol, "_cumulative_scale", 1.0)
        if isinstance(cum, (int, float)) and abs(cum - 1.0) > 1e-6 and target_vol.data is not None:
            target_vol.data = (target_vol.data / cum).astype(np.float32)
            target_vol._cumulative_scale = 1.0
            if hasattr(target_vol, "_data_range_cache"):
                delattr(target_vol, "_data_range_cache")
            target_vol._is_outdated = True

            if target_vs and hasattr(target_vs, "display"):
                target_vs.display.ww /= cum
                target_vs.display.wl /= cum
                if target_vs.display.min_threshold is not None:
                    target_vs.display.min_threshold /= cum
                target_vs.is_data_dirty = True

        self.update_ui(self._api)
        self._refresh()

    # -------------------------------------------------------------
    # Update UI
    # -------------------------------------------------------------
    def update_ui(self, api: Any) -> None:
        if not dpg.does_item_exist(self._t("group_root")):
            return

        self._api = api or self._api
        cfg_c = self._get_colors(self._api)

        target_vol, _, is_ov, unit_str, target_id = self._get_target_fn()
        if not target_vol or not target_id:
            if dpg.does_item_exist(self._t("text_range")):
                dpg.set_value(self._t("text_range"), "[---, ---]")
            if dpg.does_item_exist(self._t("btn_goto_max")):
                dpg.configure_item(self._t("btn_goto_max"), enabled=False)
            if dpg.does_item_exist(self._t("input_scale_factor")):
                dpg.set_value(self._t("input_scale_factor"), 1.0)
            if dpg.does_item_exist(self._t("text_norm_status")):
                dpg.set_value(self._t("text_norm_status"), "Absolute")
            return

        if dpg.does_item_exist(self._t("btn_goto_max")):
            self._bind_icon_font(self._t("btn_goto_max"))
            dpg.configure_item(self._t("btn_goto_max"), enabled=True)

        state = self.get_state(target_id)
        try:
            rng = target_vol.get_data_range()
            if isinstance(rng, (tuple, list)) and len(rng) == 2:
                raw_min, raw_max = float(rng[0]), float(rng[1])
            else:
                raw_min, raw_max = 0.0, 1.0
        except Exception:
            raw_min, raw_max = 0.0, 1.0

        # Keep volume virtual scale synchronized
        self._sync_volume_virtual_scale(target_vol, state)

        s_eff = self.compute_effective_scaling_factor(target_vol, is_ov, state)
        scaled_min = raw_min * s_eff
        scaled_max = raw_max * s_eff

        unit_lbl = f" {unit_str}" if unit_str else ""
        scale_unit = " %" if state.norm_mode else unit_lbl

        # 1. Update Range Display (White text, including scale)
        if dpg.does_item_exist(self._t("text_range")):
            dpg.set_value(self._t("text_range"), f"[{scaled_min:.4g}, {scaled_max:.4g}]{scale_unit}")

        # 2. Update Scale Factor Input (only if user is not actively typing)
        if dpg.does_item_exist(self._t("input_scale_factor")):
            if not dpg.is_item_active(self._t("input_scale_factor")):
                dpg.set_value(self._t("input_scale_factor"), state.scaling_factor)

        # 3. Check ROIs availability (disable ROI Mean button if no ROIs)
        viewer = self._get_active_viewer()
        roi_dict = getattr(viewer.view_state, "rois", {}) if (viewer and viewer.view_state) else {}
        if not roi_dict and self._api:
            vols = self._get_volumes()
            roi_dict = {
                vid: v for vid, v in vols.items()
                if getattr(v, "is_roi", False) or getattr(v, "roi_bbox", None) is not None or "roi" in str(vid).lower()
            }
        has_rois = len(roi_dict) > 0
        if dpg.does_item_exist(self._t("btn_norm_roi")):
            dpg.configure_item(self._t("btn_norm_roi"), enabled=has_rois)
        if not has_rois and state.norm_mode == "ROI Mean":
            state.norm_mode = None
            self._sync_volume_virtual_scale(target_vol, state)

        # 4. Show/hide and update Ref Value and ROI panels
        is_val = state.norm_mode in ("Target Value", "Ref Value", "Prescription")
        is_roi = state.norm_mode == "ROI Mean"
        if dpg.does_item_exist(self._t("group_norm_val")):
            dpg.configure_item(self._t("group_norm_val"), show=is_val)
        if dpg.does_item_exist(self._t("group_norm_roi")):
            dpg.configure_item(self._t("group_norm_roi"), show=is_roi)

        if is_val:
            if dpg.does_item_exist(self._t("label_norm_val")):
                dpg.set_value(
                    self._t("label_norm_val"),
                    f"{self._ref_label}{unit_lbl}:",
                )
            if dpg.does_item_exist(self._t("input_norm_val")):
                if not dpg.is_item_active(self._t("input_norm_val")):
                    dpg.set_value(self._t("input_norm_val"), state.norm_target_value)

        if is_roi:
            roi_items = ["(None)"]
            curr_roi_str = "(None)"
            for r_id, r_state in roi_dict.items():
                r_name = getattr(r_state, "name", r_id)
                item_str = f"{r_name} ({r_id})"
                roi_items.append(item_str)
                if r_id == state.norm_roi_id:
                    curr_roi_str = item_str

            if dpg.does_item_exist(self._t("combo_norm_roi")):
                dpg.configure_item(self._t("combo_norm_roi"), items=roi_items)
                dpg.set_value(self._t("combo_norm_roi"), curr_roi_str)

            roi_mean = self.compute_roi_mean(target_vol, is_ov, state.norm_roi_id)
            if dpg.does_item_exist(self._t("text_roi_mean")):
                dpg.set_value(self._t("text_roi_mean"), f"ROI Mean: {roi_mean:.4g}{unit_lbl}")

        # 5. Status Text (White text when active, text_dim for Absolute)
        if dpg.does_item_exist(self._t("text_norm_status")):
            if state.norm_mode == "Max":
                dpg.set_value(self._t("text_norm_status"), "Max = 100 %")
                dpg.configure_item(self._t("text_norm_status"), color=[255, 255, 255, 255])
            elif state.norm_mode in ("Target Value", "Ref Value", "Prescription"):
                norm_lbl = f"{self._ref_label} ({state.norm_target_value:.4g}{unit_lbl}) = 100 %"
                dpg.set_value(self._t("text_norm_status"), norm_lbl)
                dpg.configure_item(self._t("text_norm_status"), color=[255, 255, 255, 255])
            elif state.norm_mode == "ROI Mean":
                roi_name_str = state.norm_roi_id or "ROI"
                norm_lbl = f"ROI ({roi_name_str}) = 100 %"
                dpg.set_value(self._t("text_norm_status"), norm_lbl)
                dpg.configure_item(self._t("text_norm_status"), color=[255, 255, 255, 255])
            else:
                dpg.set_value(self._t("text_norm_status"), "Absolute")
                dpg.configure_item(self._t("text_norm_status"), color=cfg_c["text_dim"])

        # 6. Enable / Disable Bake & Reset Buttons
        cum = getattr(target_vol, "_cumulative_scale", 1.0)
        has_baked = isinstance(cum, (int, float)) and abs(cum - 1.0) > 1e-6
        has_virtual = abs(s_eff - 1.0) > 1e-6 or (state.norm_mode is not None)
        if dpg.does_item_exist(self._t("btn_bake")):
            dpg.configure_item(self._t("btn_bake"), enabled=has_virtual)
        if dpg.does_item_exist(self._t("btn_reset")):
            dpg.configure_item(self._t("btn_reset"), enabled=(has_virtual or has_baked))
