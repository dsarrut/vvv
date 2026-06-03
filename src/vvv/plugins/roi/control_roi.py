from typing import Optional, Any
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin


class RoiPluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self.api: Optional[PluginAPI] = None
        self.ui = None

        # State Persistence (similar to native RoiUI)
        self.active_roi_id = None
        self.roi_filters = {}
        self.roi_sort_orders = {}

        self._last_image_id = None
        self._last_roi_ids = set()
        self._scroll_to_active = False

    def bind(self, api: PluginAPI) -> None:
        self.api = api

    def bind_ui(self, ui) -> None:
        self.ui = ui

    def update(self, api: PluginAPI) -> None:
        if not self.ui:
            return
        viewer = api.get_active_viewer()
        image_id = viewer.image_id if (viewer and viewer.image_id) else None
        roi_ids = set(viewer.view_state.rois.keys()) if (viewer and viewer.view_state and viewer.view_state.rois) else set()

        if api._controller.ui_needs_refresh or image_id != self._last_image_id or roi_ids != self._last_roi_ids:
            self._last_image_id = image_id
            self._last_roi_ids = roi_ids
            self.ui.refresh_rois_ui()

    def on_image_loaded(self, image_id: str) -> None:
        if self.ui:
            self.ui.refresh_rois_ui()

    def on_image_removed(self, image_id: str) -> None:
        if self.active_roi_id == image_id:
            self.active_roi_id = None
        self.roi_filters.pop(image_id, None)
        self.roi_sort_orders.pop(image_id, None)
        if self.ui:
            self.ui.close_rtstruct_modal()
            self.ui.close_all_stats_windows()
            self.ui.refresh_rois_ui()

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return {
            "roi_filter": self.roi_filters.get(image_id, ""),
            "roi_sort_order": self.roi_sort_orders.get(image_id, 0),
        }

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        if "roi_filter" in data:
            self.roi_filters[image_id] = data["roi_filter"]
        if "roi_sort_order" in data:
            self.roi_sort_orders[image_id] = data["roi_sort_order"]

    def save_settings(self, api: PluginAPI) -> None:
        if self.ui:
            self.ui.save_settings(api)

    def load_settings(self, api: PluginAPI) -> None:
        if self.ui:
            self.ui.load_settings(api)

    def destroy(self) -> None:
        if self.ui:
            self.ui.close_rtstruct_modal()
            self.ui.close_all_stats_windows()

    # --- Actions called from UI ---

    def on_roi_filter_changed(self, filter_text: str) -> None:
        assert self.api is not None
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            self.roi_filters[viewer.image_id] = filter_text.lower() if filter_text else ""
            if self.ui:
                self.ui.refresh_rois_ui()

    def on_clear_roi_filter(self) -> None:
        assert self.api is not None
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            self.roi_filters[viewer.image_id] = ""
            if self.ui:
                self.ui.refresh_rois_ui()

    def on_sort_rois(self) -> None:
        assert self.api is not None
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id
        current = self.roi_sort_orders.get(vs_id, 0)
        if current == 0:
            self.roi_sort_orders[vs_id] = 1
        elif current == 1:
            self.roi_sort_orders[vs_id] = -1
        else:
            self.roi_sort_orders[vs_id] = 0
        if self.ui:
            self.ui.refresh_rois_ui()

    def on_roi_selected(self, roi_id: str) -> None:
        self.active_roi_id = roi_id
        if self.ui:
            self.ui.refresh_rois_ui()

    def move_roi_selection(self, delta: int) -> None:
        if not self.api:
            return
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state or not viewer.view_state.rois:
            return

        vs_id = viewer.image_id
        filter_text = self.roi_filters.get(vs_id, "")
        sort_order = self.roi_sort_orders.get(vs_id, 0)

        roi_items = list(viewer.view_state.rois.items())
        if sort_order == 1:
            roi_items.sort(key=lambda x: x[1].name.lower())
        elif sort_order == -1:
            roi_items.sort(key=lambda x: x[1].name.lower(), reverse=True)

        # Filter the items
        filtered_roi_ids = []
        for roi_id, roi in roi_items:
            if filter_text and filter_text not in roi.name.lower():
                continue
            filtered_roi_ids.append(roi_id)

        if not filtered_roi_ids:
            return

        try:
            current_idx = filtered_roi_ids.index(self.active_roi_id)
        except ValueError:
            current_idx = -1

        if current_idx == -1:
            if delta > 0:
                new_idx = 0
            else:
                new_idx = len(filtered_roi_ids) - 1
        else:
            new_idx = current_idx + delta
            new_idx = max(0, min(new_idx, len(filtered_roi_ids) - 1))

        self._scroll_to_active = True
        self.on_roi_selected(filtered_roi_ids[new_idx])

    def compute_detailed_roi_stats(self, base_vs_id: str, roi_id: str) -> dict | None:
        if not self.api:
            return None
        volumes = self.api.get_volumes()
        if base_vs_id not in volumes or roi_id not in volumes:
            return None

        base_vol = volumes[base_vs_id]
        roi_vol = volumes[roi_id]

        view_states = self.api.get_view_states()
        base_vs = view_states.get(base_vs_id) if view_states else None
        roi_state = base_vs.rois.get(roi_id) if (base_vs and hasattr(base_vs, "rois")) else None

        filepath = getattr(roi_vol, "path", None)
        if not isinstance(filepath, str):
            filepath = None
        file_paths = getattr(roi_vol, "file_paths", None)
        if not filepath and isinstance(file_paths, list) and len(file_paths) > 0:
            candidate = file_paths[0]
            if isinstance(candidate, str):
                filepath = candidate
        import os
        filename = os.path.basename(filepath) if filepath else "Memory/Unknown"

        source_type = "Unknown"
        if roi_state and type(roi_state).__name__ != "MagicMock":
            stype = getattr(roi_state, "source_type", "Binary")
            smode = getattr(roi_state, "source_mode", "Ignore BG (val)")
            sval = getattr(roi_state, "source_val", 0.0)
            
            if isinstance(sval, (int, float)):
                val_str = str(int(sval)) if sval.is_integer() else f"{sval:.1f}"
            else:
                val_str = str(sval)
                
            if stype == "Label Map":
                source_type = f"label={val_str}"
            elif stype == "RT-Struct":
                source_type = "rt_struct"
            elif stype == "Binary":
                if smode == "Target FG (val)":
                    source_type = f"binary mask with FG={val_str}"
                else:
                    source_type = f"binary mask with FG!={val_str}"
            else:
                source_type = stype


        import numpy as np

        # 1. Voxel geometry calculations
        mask = roi_vol.data > 0
        voxel_count = int(np.count_nonzero(mask))
        voxel_vol_mm3 = abs(np.prod(roi_vol.spacing))
        vol_cc = (voxel_count * voxel_vol_mm3) / 1000.0

        # Center of mass in pixel and physical coordinates
        indices = np.argwhere(mask)  # shape (N, 3), rows are (z, y, x)
        if len(indices) > 0:
            com_z, com_y, com_x = np.mean(indices, axis=0)
            com_pixel_cropped = [float(com_x), float(com_y), float(com_z)]
            com_mm = list(roi_vol.sitk_image.TransformContinuousIndexToPhysicalPoint(com_pixel_cropped))
            com_pixel = list(base_vol.sitk_image.TransformPhysicalPointToContinuousIndex(com_mm))
        else:
            com_pixel = [0.0, 0.0, 0.0]
            com_mm = [0.0, 0.0, 0.0]

        # Size and spacing
        nz, ny, nx = base_vol.shape3d
        size_str = f"{nx} x {ny} x {nz}"
        sx, sy, sz = base_vol.spacing
        spacing_str = f"{sx:.3f} x {sy:.3f} x {sz:.3f}"

        # Cropped size if applicable
        cropped_size_str = None
        if roi_vol.shape3d != base_vol.shape3d:
            rnz, rny, rnx = roi_vol.shape3d
            cropped_size_str = f"{rnx} x {rny} x {rnz}"

        # 2. Intensity statistics
        target_data = base_vol.data
        if base_vol.num_timepoints > 1:
            viewer = self.api.get_active_viewer()
            t = 0
            if viewer and viewer.view_state:
                t = min(viewer.view_state.camera.time_idx, base_vol.num_timepoints - 1)
            target_data = target_data[t]

        roi_bbox = getattr(roi_vol, "roi_bbox", None)
        if roi_bbox is not None and isinstance(roi_bbox, (list, tuple, np.ndarray)) and len(roi_bbox) == 6:
            z0, z1, y0, y1, x0, x1 = roi_bbox
            if z0 != z1:
                target_data = target_data[z0:z1, y0:y1, x0:x1]

        if voxel_count > 0:
            pixels = target_data[mask]
            mean_val = float(np.mean(pixels))
            std_val = float(np.std(pixels))
            median_val = float(np.median(pixels))
            min_val = float(np.min(pixels))
            max_val = float(np.max(pixels))
            peak_val = float(np.percentile(pixels, 95))
        else:
            mean_val = 0.0
            std_val = 0.0
            median_val = 0.0
            min_val = 0.0
            max_val = 0.0
            peak_val = 0.0

        density_g_cc = (mean_val / 1000.0) + 1.0
        mass_g = vol_cc * density_g_cc

        # Fusion/Overlay Intensity statistics
        overlay_stats = None
        view_states = self.api.get_view_states()
        base_vs = view_states.get(base_vs_id)
        overlay_id = base_vs.display.overlay.image_id if (base_vs and base_vs.display.overlay) else None
        if overlay_id and overlay_id in volumes:
            overlay_vol = volumes[overlay_id]
            overlay_data = base_vs.display.overlay_data if base_vs else None
            if overlay_data is not None:
                if overlay_vol and overlay_vol.num_timepoints > 1:
                    viewer = self.api.get_active_viewer()
                    t = 0
                    if viewer and viewer.view_state:
                        t = min(viewer.view_state.camera.time_idx, overlay_vol.num_timepoints - 1)
                    overlay_data = overlay_data[t]
                
                if roi_bbox is not None and isinstance(roi_bbox, (list, tuple, np.ndarray)) and len(roi_bbox) == 6:
                    z0, z1, y0, y1, x0, x1 = roi_bbox
                    if z0 != z1:
                        overlay_data = overlay_data[z0:z1, y0:y1, x0:x1]
                
                if voxel_count > 0:
                    ov_pixels = overlay_data[mask]
                    ov_mean = float(np.mean(ov_pixels))
                    ov_std = float(np.std(ov_pixels))
                    ov_median = float(np.median(ov_pixels))
                    ov_min = float(np.min(ov_pixels))
                    ov_max = float(np.max(ov_pixels))
                    ov_peak = float(np.percentile(ov_pixels, 95))
                else:
                    ov_mean = 0.0
                    ov_std = 0.0
                    ov_median = 0.0
                    ov_min = 0.0
                    ov_max = 0.0
                    ov_peak = 0.0
                
                overlay_stats = {
                    "name": overlay_vol.name if overlay_vol else overlay_id,
                    "mean": ov_mean,
                    "std": ov_std,
                    "median": ov_median,
                    "min": ov_min,
                    "max": ov_max,
                    "peak": ov_peak,
                }

        return {
            "vol_cc": vol_cc,
            "voxel_count": voxel_count,
            "com_pixel": com_pixel,
            "com_mm": com_mm,
            "size": size_str,
            "spacing": spacing_str,
            "cropped_size": cropped_size_str,
            "mean": mean_val,
            "std": std_val,
            "median": median_val,
            "min": min_val,
            "max": max_val,
            "peak": peak_val,
            "mass": mass_g,
            "overlay_stats": overlay_stats,
            "source_filename": filename,
            "source_filepath": filepath,
            "source_type": source_type,
        }
