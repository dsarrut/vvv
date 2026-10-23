import threading
from typing import Optional
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.ui.ui_components import name_matches, next_sort_order, sort_by_name

# Source key of the ROIs made in vvv (sphere, box), which have no file
CREATED_SOURCE = ""


def roi_source(roi, vol) -> str:
    """The file an ROI was read from (its source key), CREATED_SOURCE if none."""
    if getattr(roi, "source_type", None) == "Created":
        return CREATED_SOURCE
    paths = getattr(vol, "file_paths", None)
    if isinstance(paths, (list, tuple)) and paths and isinstance(paths[0], str):
        return paths[0]
    return CREATED_SOURCE


class RoiPluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self.api: Optional[PluginAPI] = None
        self.ui = None

        # State Persistence (similar to native RoiUI)
        self.active_roi_id = None
        self.selected_roi_ids: set[str] = set()
        self.roi_filters = {}
        self.roi_filter_inverts = {}  # image_id -> bool
        self.roi_sort_orders = {}
        # image_id -> source key of the listed ROIs (absent: all); not saved
        self.roi_source_filters = {}

        self._last_image_id = None
        self._last_roi_ids = set()
        self._scroll_to_active = False
        self._stop_event = threading.Event()
        self._detailed_stats_cache = {}

    def invalidate_stats_cache(self, roi_id: Optional[str] = None) -> None:
        if roi_id is None:
            self._detailed_stats_cache.clear()
        else:
            self._detailed_stats_cache = {
                k: v for k, v in self._detailed_stats_cache.items() if k[1] != roi_id
            }

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

        if api.ui_needs_refresh or image_id != self._last_image_id or roi_ids != self._last_roi_ids:
            self._last_image_id = image_id
            self._last_roi_ids = roi_ids
            # Prune any selected_roi_ids that no longer exist
            if self.selected_roi_ids:
                self.selected_roi_ids.intersection_update(roi_ids)
                if self.active_roi_id and self.active_roi_id not in self.selected_roi_ids:
                    self.active_roi_id = next(iter(self.selected_roi_ids), None)
            self.ui.refresh_rois_ui()

    def on_image_loaded(self, image_id: str) -> None:
        if self.ui:
            self.ui.refresh_rois_ui()

    def on_image_removed(self, image_id: str) -> None:
        # active_roi_id is a roi_id, not an image_id — always clear it;
        # the UI list is fully rebuilt right after.
        self.active_roi_id = None
        self.selected_roi_ids.clear()
        self.roi_filters.pop(image_id, None)
        self.roi_filter_inverts.pop(image_id, None)
        self.roi_sort_orders.pop(image_id, None)
        self.roi_source_filters.pop(image_id, None)
        self.invalidate_stats_cache()
        if self.ui:
            self.ui.close_rtstruct_modal()
            self.ui.close_all_stats_windows()
            self.ui.refresh_rois_ui()

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return {
            "roi_filter": self.roi_filters.get(image_id, ""),
            "roi_filter_invert": self.roi_filter_inverts.get(image_id, False),
            "roi_sort_order": self.roi_sort_orders.get(image_id, 0),
        }

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        if "roi_filter" in data:
            self.roi_filters[image_id] = data["roi_filter"]
        if "roi_filter_invert" in data:
            self.roi_filter_inverts[image_id] = data["roi_filter_invert"]
        if "roi_sort_order" in data:
            self.roi_sort_orders[image_id] = data["roi_sort_order"]

    def save_settings(self, api: PluginAPI) -> None:
        if self.ui:
            self.ui.save_settings(api)

    def load_settings(self, api: PluginAPI) -> None:
        if self.ui:
            self.ui.load_settings(api)

    def destroy(self) -> None:
        self._stop_event.set()
        if self.ui:
            self.ui.close_rtstruct_modal()
            self.ui.close_all_stats_windows()

    # --- Actions called from UI ---

    def on_toggle_roi_filter_invert(self) -> None:
        if not self.api:
            return
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            vs_id = viewer.image_id
            self.roi_filter_inverts[vs_id] = not self.roi_filter_inverts.get(vs_id, False)
            if self.ui:
                self.ui.refresh_rois_ui()

    def on_roi_filter_changed(self, filter_text: str) -> None:
        if not self.api:
            return
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            self.roi_filters[viewer.image_id] = filter_text.lower() if filter_text else ""
            if self.ui:
                self.ui.refresh_rois_ui()

    def on_clear_roi_filter(self) -> None:
        if not self.api:
            return
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            self.roi_filters[viewer.image_id] = ""
            self.roi_filter_inverts[viewer.image_id] = False
            if self.ui:
                self.ui.refresh_rois_ui()

    def is_roi_listed(self, vs_id, roi_id, roi, volumes) -> bool:
        """The rule of the listed ROIs (list, navigation, batch actions, save):
        name filter, then source filter."""
        if not name_matches(
            roi.name,
            self.roi_filters.get(vs_id, ""),
            self.roi_filter_inverts.get(vs_id, False),
        ):
            return False
        source = self.roi_source_filters.get(vs_id)
        return source is None or roi_source(roi, volumes.get(roi_id)) == source

    @staticmethod
    def list_roi_sources(rois, volumes) -> dict:
        """source key -> (source_type of its first ROI, number of ROIs), in load order."""
        sources = {}
        for roi_id, roi in rois.items():
            key = roi_source(roi, volumes.get(roi_id))
            kind, count = sources.get(key, (getattr(roi, "source_type", "Binary"), 0))
            sources[key] = (kind, count + 1)
        return sources

    def prune_roi_source_filter(self, vs_id, sources) -> None:
        """Forget the source filter once its file is gone or only one source is left."""
        source = self.roi_source_filters.get(vs_id)
        if source is not None and (source not in sources or len(sources) <= 1):
            del self.roi_source_filters[vs_id]

    def on_roi_source_changed(self, source) -> None:
        """source: a source key, or None for all the ROIs."""
        if not self.api:
            return
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            if source is None:
                self.roi_source_filters.pop(viewer.image_id, None)
            else:
                self.roi_source_filters[viewer.image_id] = source
            if self.ui:
                self.ui.refresh_rois_ui()

    def on_sort_rois(self) -> None:
        if not self.api:
            return
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id
        self.roi_sort_orders[vs_id] = next_sort_order(self.roi_sort_orders.get(vs_id, 0))
        if self.ui:
            self.ui.refresh_rois_ui()

    def clear_roi_selection(self) -> None:
        self.selected_roi_ids.clear()
        self.active_roi_id = None
        if self.ui:
            self.ui.refresh_rois_ui()

    def on_roi_selected(
        self,
        roi_id: str,
        ctrl: bool = False,
        shift: bool = False,
        visible_ids: list[str] | None = None,
    ) -> None:
        if shift and visible_ids and roi_id in visible_ids:
            # Range selection
            anchor = self.active_roi_id if (self.active_roi_id and self.active_roi_id in visible_ids) else (visible_ids[0] if visible_ids else roi_id)
            try:
                idx_start = visible_ids.index(anchor)
                idx_end = visible_ids.index(roi_id)
                low, high = min(idx_start, idx_end), max(idx_start, idx_end)
                range_ids = set(visible_ids[low : high + 1])
                if ctrl:
                    self.selected_roi_ids.update(range_ids)
                else:
                    self.selected_roi_ids = range_ids
                self.active_roi_id = roi_id
            except ValueError:
                self.selected_roi_ids = {roi_id}
                self.active_roi_id = roi_id
        elif ctrl:
            # Toggle individual ROI
            if roi_id in self.selected_roi_ids:
                self.selected_roi_ids.remove(roi_id)
                if self.active_roi_id == roi_id:
                    self.active_roi_id = next(iter(self.selected_roi_ids), None)
            else:
                self.selected_roi_ids.add(roi_id)
                self.active_roi_id = roi_id
        else:
            # Normal single selection
            self.selected_roi_ids = {roi_id}
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
        sort_order = self.roi_sort_orders.get(vs_id, 0)
        volumes = self.api.get_volumes()

        roi_items = sort_by_name(
            viewer.view_state.rois.items(), sort_order, name=lambda x: x[1].name
        )
        filtered_roi_ids = [
            roi_id
            for roi_id, roi in roi_items
            if self.is_roi_listed(vs_id, roi_id, roi, volumes)
        ]

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

        viewer = self.api.get_active_viewer()
        t_base = 0
        if viewer and viewer.view_state and base_vol.num_timepoints > 1:
            t_base = min(viewer.view_state.camera.time_idx, base_vol.num_timepoints - 1)

        overlay_id = base_vs.display.overlay.image_id if (base_vs and hasattr(base_vs, "display") and base_vs.display.overlay) else None
        ov_data = getattr(base_vs.display, "overlay_data", None) if (base_vs and hasattr(base_vs, "display")) else None
        ov_data_id = id(ov_data) if ov_data is not None else None
        t_ov = 0
        if overlay_id and overlay_id in volumes:
            ov_vol = volumes[overlay_id]
            if ov_vol and ov_vol.num_timepoints > 1 and viewer and viewer.view_state:
                t_ov = min(viewer.view_state.camera.time_idx, ov_vol.num_timepoints - 1)

        cache_key = (
            base_vs_id,
            roi_id,
            id(base_vol.data),
            id(roi_vol.data),
            t_base,
            overlay_id,
            ov_data_id,
            t_ov,
            getattr(roi_state, "source_type", None),
            getattr(roi_state, "source_mode", None),
            getattr(roi_state, "source_val", None),
        )
        if cache_key in self._detailed_stats_cache:
            return self._detailed_stats_cache[cache_key]

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
        if roi_state:
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
            elif isinstance(stype, str):
                source_type = stype


        import numpy as np
        import SimpleITK as sitk

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
            if isinstance(getattr(roi_vol, "sitk_image", None), sitk.Image):
                roi_dim = int(roi_vol.sitk_image.GetDimension())
            else:
                roi_dim = 3

            if len(com_pixel_cropped) < roi_dim:
                com_pixel_cropped_padded = com_pixel_cropped + [0.0] * (roi_dim - len(com_pixel_cropped))
            elif len(com_pixel_cropped) > roi_dim:
                com_pixel_cropped_padded = com_pixel_cropped[:roi_dim]
            else:
                com_pixel_cropped_padded = com_pixel_cropped

            com_mm_full = list(roi_vol.sitk_image.TransformContinuousIndexToPhysicalPoint(com_pixel_cropped_padded))
            com_mm = com_mm_full[:3]

            if isinstance(getattr(base_vol, "sitk_image", None), sitk.Image):
                base_dim = int(base_vol.sitk_image.GetDimension())
            else:
                base_dim = 3

            if len(com_mm) < base_dim:
                com_mm_padded = com_mm + [0.0] * (base_dim - len(com_mm))
            elif len(com_mm) > base_dim:
                com_mm_padded = com_mm[:base_dim]
            else:
                com_mm_padded = com_mm

            com_pixel_full = list(base_vol.sitk_image.TransformPhysicalPointToContinuousIndex(com_mm_padded))
            com_pixel = com_pixel_full[:3]
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
        elif target_data.ndim == 4 and not base_vol.is_rgb:
            target_data = target_data[0]

        roi_bbox = getattr(roi_vol, "roi_bbox", None)
        if roi_bbox is not None and isinstance(roi_bbox, (list, tuple, np.ndarray)) and len(roi_bbox) == 6:
            z0, z1, y0, y1, x0, x1 = roi_bbox
            if z0 != z1:
                target_data = target_data[z0:z1, y0:y1, x0:x1]

        if voxel_count > 0 and target_data.shape == mask.shape:
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
                elif overlay_data.ndim == 4 and overlay_vol and not overlay_vol.is_rgb:
                    overlay_data = overlay_data[0]
                
                if roi_bbox is not None and isinstance(roi_bbox, (list, tuple, np.ndarray)) and len(roi_bbox) == 6:
                    z0, z1, y0, y1, x0, x1 = roi_bbox
                    if z0 != z1:
                        overlay_data = overlay_data[z0:z1, y0:y1, x0:x1]
                
                if voxel_count > 0 and overlay_data.shape == mask.shape:
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

        res = {
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
        self._detailed_stats_cache[cache_key] = res
        return res

    def on_add_spheroid(self, base_id: str) -> None:
        import numpy as np
        import dearpygui.dearpygui as dpg
        import SimpleITK as sitk

        assert self.api is not None
        viewer = self.api.get_active_viewer()
        if not viewer or viewer.image_id != base_id:
            return

        # 1. Get physical center from crosshair
        phys_center = self.api.get_crosshair_world()
        if phys_center is None:
            phys_center = [0.0, 0.0, 0.0]
        phys_center = np.array(phys_center)

        # 2. Get FOV and calculate radius (1/10 of FOV)
        ppm = getattr(viewer.view_state.camera, "target_ppm", None) or viewer.get_pixels_per_mm()
        win_w = getattr(viewer, "quad_w", 0) or (dpg.get_item_width(f"win_{viewer.tag}") if dpg.does_item_exist(f"win_{viewer.tag}") else 0)
        win_h = getattr(viewer, "quad_h", 0) or (dpg.get_item_height(f"win_{viewer.tag}") if dpg.does_item_exist(f"win_{viewer.tag}") else 0)
        if not win_w or win_w <= 0:
            win_w = 300
        if not win_h or win_h <= 0:
            win_h = 300
        if not ppm or ppm <= 0:
            ppm = 1.0
        fov = min(win_w / ppm, win_h / ppm)
        if fov <= 0:
            fov = 100.0
        r_mm = max(1.0, 0.1 * fov)

        # 3. Get base image volume
        base_vol = self.api.get_volumes().get(base_id)
        if not base_vol:
            return

        # Ensure center is within image FOV
        center_vox = base_vol.physic_coord_to_voxel_coord(phys_center)
        base_sz, base_sy, base_sx = base_vol.shape3d
        cx = np.clip(center_vox[0], 0.0, float(base_sx - 1))
        cy = np.clip(center_vox[1], 0.0, float(base_sy - 1))
        cz = np.clip(center_vox[2], 0.0, float(base_sz - 1))
        clipped_center_vox = np.array([cx, cy, cz])
        phys_center = base_vol.voxel_coord_to_physic_coord(clipped_center_vox)

        # 4. Find bounding box corners in voxel space
        corners = []
        for dx in [-r_mm, r_mm]:
            for dy in [-r_mm, r_mm]:
                for dz in [-r_mm, r_mm]:
                    pt = phys_center + np.array([dx, dy, dz])
                    corners.append(base_vol.physic_coord_to_voxel_coord(pt))
        corners = np.array(corners)
        min_vox = np.floor(corners.min(axis=0)).astype(int)
        max_vox = np.ceil(corners.max(axis=0)).astype(int)

        base_sz, base_sy, base_sx = base_vol.shape3d
        min_x = max(0, min_vox[0])
        max_x = min(base_sx, max_vox[0])
        min_y = max(0, min_vox[1])
        max_y = min(base_sy, max_vox[1])
        min_z = max(0, min_vox[2])
        max_z = min(base_sz, max_vox[2])

        if min_x >= max_x or min_y >= max_y or min_z >= max_z:
            self.api.notify("Error: Spheroid is completely outside the image.")
            return

        # 5. Create binary mask in the sub-grid
        zs = np.arange(min_z, max_z)
        ys = np.arange(min_y, max_y)
        xs = np.arange(min_x, max_x)
        grid_z, grid_y, grid_x = np.meshgrid(zs, ys, xs, indexing='ij')

        voxels = np.column_stack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()])
        phys_pts = base_vol.origin + (base_vol.matrix @ (voxels * base_vol.spacing).T).T

        diff = phys_pts - phys_center
        dist_sq = np.sum(diff ** 2, axis=1)

        mask_flat = dist_sq <= r_mm ** 2
        mask_data = mask_flat.reshape((max_z - min_z, max_y - min_y, max_x - min_x)).astype(np.uint8)

        if not np.any(mask_data):
            center_voxel = base_vol.physic_coord_to_voxel_coord(phys_center)
            cx_idx = int(round(center_voxel[0]))
            cy_idx = int(round(center_voxel[1]))
            cz_idx = int(round(center_voxel[2]))
            sub_z = cz_idx - min_z
            sub_y = cy_idx - min_y
            sub_x = cx_idx - min_x
            if 0 <= sub_z < (max_z - min_z) and 0 <= sub_y < (max_y - min_y) and 0 <= sub_x < (max_x - min_x):
                mask_data[sub_z, sub_y, sub_x] = 1

        # 6. Create SimpleITK image
        ref_origin = base_vol.voxel_coord_to_physic_coord(np.array([min_x, min_y, min_z]))
        mask_img = sitk.GetImageFromArray(mask_data)
        mask_img.SetSpacing(base_vol.spacing.tolist())
        mask_img.SetDirection(base_vol.sitk_image.GetDirection())
        mask_img.SetOrigin(ref_origin.tolist())

        # 7. Register new ROI
        rois_count = len(self.api.get_view_states()[base_id].rois)
        roi_name = f"Sphere_{rois_count + 1}"
        from vvv.config import ROI_COLORS
        color = ROI_COLORS[rois_count % len(ROI_COLORS)]

        roi_id = self.api.create_memory_roi(
            base_id=base_id,
            filepath="spheroid_roi",
            name=roi_name,
            mask_img=mask_img,
            mask_data=mask_data,
            skip_crop=False,
            is_contour=False,
            color=color,
            source_type="Created"
        )

        if roi_id:
            vs = self.api.get_view_states()[base_id]
            roi_state = vs.rois[roi_id]
            roi_state.is_spheroid = True
            roi_state.spheroid_center = phys_center.tolist()
            roi_state.spheroid_radius_x = r_mm
            roi_state.spheroid_radius_y = r_mm
            roi_state.spheroid_radius_z = r_mm
            roi_state.spheroid_radius_xy = r_mm
            roi_state.spheroid_radius = r_mm
            vs.is_geometry_dirty = True
            vs.is_data_dirty = True
            self.api.request_refresh()
            self.api.update_all_viewers_of_image(base_id)
            self.api.notify(f"Created spheroid ROI: {roi_name}")
            if self.ui:
                self.ui.on_roi_stats_toggle(None, None, roi_id)

    def update_spheroid_mask(self, base_vol, roi_vol, roi_state, new_r_x_mm: float | None = None, new_r_y_mm: float | None = None, new_r_z_mm: float | None = None) -> None:
        import numpy as np
        import SimpleITK as sitk

        if new_r_x_mm is None:
            new_r_x_mm = getattr(roi_state, "spheroid_radius_x", None) or getattr(roi_state, "spheroid_radius_xy", None) or getattr(roi_state, "spheroid_radius", None) or 10.0
        new_r_x_mm = max(0.5, float(new_r_x_mm))

        if new_r_y_mm is None:
            new_r_y_mm = getattr(roi_state, "spheroid_radius_y", None) or getattr(roi_state, "spheroid_radius_xy", None) or getattr(roi_state, "spheroid_radius", None) or 10.0
        new_r_y_mm = max(0.5, float(new_r_y_mm))

        if new_r_z_mm is None:
            new_r_z_mm = getattr(roi_state, "spheroid_radius_z", None) or getattr(roi_state, "spheroid_radius", None) or 10.0
        new_r_z_mm = max(0.5, float(new_r_z_mm))

        # Ensure center is within image FOV
        curr_center = getattr(roi_state, "spheroid_center", None) or [0.0, 0.0, 0.0]
        phys_center = np.array(curr_center)
        center_vox = base_vol.physic_coord_to_voxel_coord(phys_center)
        base_sz, base_sy, base_sx = base_vol.shape3d
        cx = np.clip(center_vox[0], 0.0, float(base_sx - 1))
        cy = np.clip(center_vox[1], 0.0, float(base_sy - 1))
        cz = np.clip(center_vox[2], 0.0, float(base_sz - 1))
        clipped_center_vox = np.array([cx, cy, cz])
        clipped_center_phys = base_vol.voxel_coord_to_physic_coord(clipped_center_vox)
        phys_center = clipped_center_phys

        # 1. Find bounding box corners in voxel space
        corners = []
        for dx in [-new_r_x_mm, new_r_x_mm]:
            for dy in [-new_r_y_mm, new_r_y_mm]:
                for dz in [-new_r_z_mm, new_r_z_mm]:
                    pt = phys_center + np.array([dx, dy, dz])
                    corners.append(base_vol.physic_coord_to_voxel_coord(pt))
        corners = np.array(corners)
        min_vox = np.floor(corners.min(axis=0)).astype(int)
        max_vox = np.ceil(corners.max(axis=0)).astype(int)

        base_sz, base_sy, base_sx = base_vol.shape3d
        min_x = max(0, min_vox[0])
        max_x = min(base_sx, max_vox[0])
        min_y = max(0, min_vox[1])
        max_y = min(base_sy, max_vox[1])
        min_z = max(0, min_vox[2])
        max_z = min(base_sz, max_vox[2])

        if min_x >= max_x or min_y >= max_y or min_z >= max_z:
            return

        roi_state.spheroid_radius_x = new_r_x_mm
        roi_state.spheroid_radius_y = new_r_y_mm
        roi_state.spheroid_radius_z = new_r_z_mm
        roi_state.spheroid_radius_xy = new_r_x_mm
        roi_state.spheroid_radius = new_r_x_mm
        roi_state.spheroid_center = clipped_center_phys.tolist()

        # 2. Create binary mask in the sub-grid
        zs = np.arange(min_z, max_z)
        ys = np.arange(min_y, max_y)
        xs = np.arange(min_x, max_x)
        grid_z, grid_y, grid_x = np.meshgrid(zs, ys, xs, indexing='ij')

        voxels = np.column_stack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()])
        phys_pts = base_vol.origin + (base_vol.matrix @ (voxels * base_vol.spacing).T).T

        diff = phys_pts - phys_center
        dist_sq = (diff[:, 0] ** 2) / (new_r_x_mm ** 2) + (diff[:, 1] ** 2) / (new_r_y_mm ** 2) + (diff[:, 2] ** 2) / (new_r_z_mm ** 2)

        mask_flat = dist_sq <= 1.0
        mask_data = mask_flat.reshape((max_z - min_z, max_y - min_y, max_x - min_x)).astype(np.uint8)

        if not np.any(mask_data):
            center_voxel = base_vol.physic_coord_to_voxel_coord(phys_center)
            cx_idx = int(round(center_voxel[0]))
            cy_idx = int(round(center_voxel[1]))
            cz_idx = int(round(center_voxel[2]))
            sub_z = cz_idx - min_z
            sub_y = cy_idx - min_y
            sub_x = cx_idx - min_x
            if 0 <= sub_z < (max_z - min_z) and 0 <= sub_y < (max_y - min_y) and 0 <= sub_x < (max_x - min_x):
                mask_data[sub_z, sub_y, sub_x] = 1

        # 3. Create SimpleITK image if base_vol has a valid sitk_image
        ref_origin = base_vol.voxel_coord_to_physic_coord(np.array([min_x, min_y, min_z]))
        if isinstance(getattr(base_vol, "sitk_image", None), sitk.Image):
            mask_img = sitk.GetImageFromArray(mask_data)
            mask_img.SetSpacing(base_vol.spacing.tolist())
            mask_img.SetDirection(base_vol.sitk_image.GetDirection())
            mask_img.SetOrigin(ref_origin.tolist())
            roi_vol.sitk_image = mask_img

        roi_vol.data = mask_data
        roi_vol.origin = ref_origin
        roi_vol.roi_bbox = (min_z, max_z, min_y, max_y, min_x, max_x)
        self.invalidate_stats_cache(roi_id=getattr(roi_state, "volume_id", None))

    def on_add_box(self, base_id: str) -> None:
        import numpy as np
        import dearpygui.dearpygui as dpg
        import SimpleITK as sitk

        assert self.api is not None
        viewer = self.api.get_active_viewer()
        if not viewer or viewer.image_id != base_id:
            return

        # 1. Get physical center from crosshair
        phys_center = self.api.get_crosshair_world()
        if phys_center is None:
            phys_center = [0.0, 0.0, 0.0]
        phys_center = np.array(phys_center)

        # 2. Get FOV and calculate size (0.2 * FOV, meaning radius/half-length is 0.1 * FOV)
        ppm = getattr(viewer.view_state.camera, "target_ppm", None) or viewer.get_pixels_per_mm()
        win_w = getattr(viewer, "quad_w", 0) or (dpg.get_item_width(f"win_{viewer.tag}") if dpg.does_item_exist(f"win_{viewer.tag}") else 0)
        win_h = getattr(viewer, "quad_h", 0) or (dpg.get_item_height(f"win_{viewer.tag}") if dpg.does_item_exist(f"win_{viewer.tag}") else 0)
        if not win_w or win_w <= 0:
            win_w = 300
        if not win_h or win_h <= 0:
            win_h = 300
        if not ppm or ppm <= 0:
            ppm = 1.0
        fov = min(win_w / ppm, win_h / ppm)
        if fov <= 0:
            fov = 100.0
        half_x = max(0.5, 0.1 * fov)
        half_y = max(0.5, 0.1 * fov)
        half_z = max(0.5, 0.1 * fov)
        size_x = 2.0 * half_x
        size_y = 2.0 * half_y
        size_z = 2.0 * half_z

        # 3. Get base image volume
        base_vol = self.api.get_volumes().get(base_id)
        if not base_vol:
            return

        # Ensure center is within image FOV
        center_vox = base_vol.physic_coord_to_voxel_coord(phys_center)
        base_sz, base_sy, base_sx = base_vol.shape3d
        cx = np.clip(center_vox[0], 0.0, float(base_sx - 1))
        cy = np.clip(center_vox[1], 0.0, float(base_sy - 1))
        cz = np.clip(center_vox[2], 0.0, float(base_sz - 1))
        clipped_center_vox = np.array([cx, cy, cz])
        phys_center = base_vol.voxel_coord_to_physic_coord(clipped_center_vox)

        # 4. Find bounding box corners in voxel space
        corners = []
        for dx in [-half_x, half_x]:
            for dy in [-half_y, half_y]:
                for dz in [-half_z, half_z]:
                    pt = phys_center + np.array([dx, dy, dz])
                    corners.append(base_vol.physic_coord_to_voxel_coord(pt))
        corners = np.array(corners)
        min_vox = np.floor(corners.min(axis=0)).astype(int)
        max_vox = np.ceil(corners.max(axis=0)).astype(int)

        base_sz, base_sy, base_sx = base_vol.shape3d
        min_x = max(0, min_vox[0])
        max_x = min(base_sx, max_vox[0])
        min_y = max(0, min_vox[1])
        max_y = min(base_sy, max_vox[1])
        min_z = max(0, min_vox[2])
        max_z = min(base_sz, max_vox[2])

        if min_x >= max_x or min_y >= max_y or min_z >= max_z:
            self.api.notify("Error: Box is completely outside the image.")
            return

        # 5. Create binary mask in the sub-grid (using voxel coordinates)
        zs = np.arange(min_z, max_z)
        ys = np.arange(min_y, max_y)
        xs = np.arange(min_x, max_x)
        grid_z, grid_y, grid_x = np.meshgrid(zs, ys, xs, indexing='ij')

        voxels = np.column_stack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()])
        phys_pts = base_vol.origin + (base_vol.matrix @ (voxels * base_vol.spacing).T).T

        diff = phys_pts - phys_center
        mask_flat = (
            (np.abs(diff[:, 0]) <= half_x)
            & (np.abs(diff[:, 1]) <= half_y)
            & (np.abs(diff[:, 2]) <= half_z)
        )
        mask_data = mask_flat.reshape((max_z - min_z, max_y - min_y, max_x - min_x)).astype(np.uint8)

        if not np.any(mask_data):
            center_voxel = base_vol.physic_coord_to_voxel_coord(phys_center)
            cx_idx = int(round(center_voxel[0]))
            cy_idx = int(round(center_voxel[1]))
            cz_idx = int(round(center_voxel[2]))
            sub_z = cz_idx - min_z
            sub_y = cy_idx - min_y
            sub_x = cx_idx - min_x
            if 0 <= sub_z < (max_z - min_z) and 0 <= sub_y < (max_y - min_y) and 0 <= sub_x < (max_x - min_x):
                mask_data[sub_z, sub_y, sub_x] = 1

        # 6. Create SimpleITK image
        ref_origin = base_vol.voxel_coord_to_physic_coord(np.array([min_x, min_y, min_z]))
        mask_img = sitk.GetImageFromArray(mask_data)
        mask_img.SetSpacing(base_vol.spacing.tolist())
        mask_img.SetDirection(base_vol.sitk_image.GetDirection())
        mask_img.SetOrigin(ref_origin.tolist())

        # 7. Register new ROI
        rois_count = len(self.api.get_view_states()[base_id].rois)
        roi_name = f"Box_{rois_count + 1}"
        from vvv.config import ROI_COLORS
        color = ROI_COLORS[rois_count % len(ROI_COLORS)]

        roi_id = self.api.create_memory_roi(
            base_id=base_id,
            filepath="box_roi",
            name=roi_name,
            mask_img=mask_img,
            mask_data=mask_data,
            skip_crop=False,
            is_contour=False,
            color=color,
            source_type="Created"
        )

        if roi_id:
            vs = self.api.get_view_states()[base_id]
            roi_state = vs.rois[roi_id]
            roi_state.is_box = True
            roi_state.box_center = phys_center.tolist()
            roi_state.box_size_x = size_x
            roi_state.box_size_y = size_y
            roi_state.box_size_z = size_z
            vs.is_geometry_dirty = True
            vs.is_data_dirty = True
            self.api.request_refresh()
            self.api.update_all_viewers_of_image(base_id)
            self.api.notify(f"Created box ROI: {roi_name}")
            if self.ui:
                self.ui.on_roi_stats_toggle(None, None, roi_id)

    def update_box_mask(self, base_vol, roi_vol, roi_state, new_size_x: float | None = None, new_size_y: float | None = None, new_size_z: float | None = None) -> None:
        import numpy as np
        import SimpleITK as sitk

        if new_size_x is None:
            new_size_x = getattr(roi_state, "box_size_x", None) or getattr(roi_state, "box_size", None) or 20.0
        new_size_x = max(1.0, float(new_size_x))
        if new_size_y is None:
            new_size_y = getattr(roi_state, "box_size_y", None) or getattr(roi_state, "box_size", None) or 20.0
        new_size_y = max(1.0, float(new_size_y))
        if new_size_z is None:
            new_size_z = getattr(roi_state, "box_size_z", None) or getattr(roi_state, "box_size", None) or 20.0
        new_size_z = max(1.0, float(new_size_z))

        # Ensure center is within image FOV
        curr_center = getattr(roi_state, "box_center", None) or [0.0, 0.0, 0.0]
        phys_center = np.array(curr_center)
        center_vox = base_vol.physic_coord_to_voxel_coord(phys_center)
        base_sz, base_sy, base_sx = base_vol.shape3d
        cx = np.clip(center_vox[0], 0.0, float(base_sx - 1))
        cy = np.clip(center_vox[1], 0.0, float(base_sy - 1))
        cz = np.clip(center_vox[2], 0.0, float(base_sz - 1))
        clipped_center_vox = np.array([cx, cy, cz])
        clipped_center_phys = base_vol.voxel_coord_to_physic_coord(clipped_center_vox)
        phys_center = clipped_center_phys

        half_x = new_size_x / 2.0
        half_y = new_size_y / 2.0
        half_z = new_size_z / 2.0

        # 1. Find bounding box corners in voxel space
        corners = []
        for dx in [-half_x, half_x]:
            for dy in [-half_y, half_y]:
                for dz in [-half_z, half_z]:
                    pt = phys_center + np.array([dx, dy, dz])
                    corners.append(base_vol.physic_coord_to_voxel_coord(pt))
        corners = np.array(corners)
        min_vox = np.floor(corners.min(axis=0)).astype(int)
        max_vox = np.ceil(corners.max(axis=0)).astype(int)

        base_sz, base_sy, base_sx = base_vol.shape3d
        min_x = max(0, min_vox[0])
        max_x = min(base_sx, max_vox[0])
        min_y = max(0, min_vox[1])
        max_y = min(base_sy, max_vox[1])
        min_z = max(0, min_vox[2])
        max_z = min(base_sz, max_vox[2])

        if min_x >= max_x or min_y >= max_y or min_z >= max_z:
            return

        roi_state.box_size_x = new_size_x
        roi_state.box_size_y = new_size_y
        roi_state.box_size_z = new_size_z
        roi_state.box_center = clipped_center_phys.tolist()

        # 2. Create binary mask in the sub-grid
        zs = np.arange(min_z, max_z)
        ys = np.arange(min_y, max_y)
        xs = np.arange(min_x, max_x)
        grid_z, grid_y, grid_x = np.meshgrid(zs, ys, xs, indexing='ij')

        voxels = np.column_stack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()])
        phys_pts = base_vol.origin + (base_vol.matrix @ (voxels * base_vol.spacing).T).T

        diff = phys_pts - phys_center
        mask_flat = (
            (np.abs(diff[:, 0]) <= half_x)
            & (np.abs(diff[:, 1]) <= half_y)
            & (np.abs(diff[:, 2]) <= half_z)
        )
        mask_data = mask_flat.reshape((max_z - min_z, max_y - min_y, max_x - min_x)).astype(np.uint8)

        if not np.any(mask_data):
            center_voxel = base_vol.physic_coord_to_voxel_coord(phys_center)
            cx_idx = int(round(center_voxel[0]))
            cy_idx = int(round(center_voxel[1]))
            cz_idx = int(round(center_voxel[2]))
            sub_z = cz_idx - min_z
            sub_y = cy_idx - min_y
            sub_x = cx_idx - min_x
            if 0 <= sub_z < (max_z - min_z) and 0 <= sub_y < (max_y - min_y) and 0 <= sub_x < (max_x - min_x):
                mask_data[sub_z, sub_y, sub_x] = 1

        # 3. Create SimpleITK image if base_vol has a valid sitk_image
        ref_origin = base_vol.voxel_coord_to_physic_coord(np.array([min_x, min_y, min_z]))
        if isinstance(getattr(base_vol, "sitk_image", None), sitk.Image):
            mask_img = sitk.GetImageFromArray(mask_data)
            mask_img.SetSpacing(base_vol.spacing.tolist())
            mask_img.SetDirection(base_vol.sitk_image.GetDirection())
            mask_img.SetOrigin(ref_origin.tolist())
            roi_vol.sitk_image = mask_img

        roi_vol.data = mask_data
        roi_vol.origin = ref_origin
        roi_vol.roi_bbox = (min_z, max_z, min_y, max_y, min_x, max_x)
        self.invalidate_stats_cache(roi_id=getattr(roi_state, "volume_id", None))

    def collect_filtered_rois(self, base_id: str):
        """Main thread: snapshot of what a batch ROI save needs, so the worker
        never reads the live vs.rois dict or a VolumeData. None if the base
        image is gone. The sitk images are kept to keep the arrays alive."""
        if not self.api:
            return None
        volumes = self.api.get_volumes()
        base_vol = volumes.get(base_id)
        base_vs = self.api.get_view_states().get(base_id)
        if not base_vol or not base_vs:
            return None

        rois = []
        for roi_id, roi_state in base_vs.rois.items():
            if not self.is_roi_listed(base_id, roi_id, roi_state, volumes):
                continue
            r_vol = volumes.get(roi_id)
            if not r_vol or r_vol.data is None:
                continue
            rois.append(
                {
                    "roi_id": roi_id,
                    "name": roi_state.name,
                    "color": getattr(roi_state, "color", None) or [255, 0, 0],
                    "data": r_vol.data[0] if r_vol.data.ndim == 4 else r_vol.data,
                    "bbox": getattr(r_vol, "roi_bbox", None),
                    "shape3d": tuple(r_vol.shape3d),
                    "sitk_image": getattr(r_vol, "sitk_image", None),
                }
            )
        return {
            "shape3d": tuple(base_vol.shape3d),
            "sitk_image": getattr(base_vol, "sitk_image", None),
            "rois": rois,
        }

    @staticmethod
    def _paste_roi_mask(roi, mask, out, value):
        """Write `value` where `mask` is set into `out` (base grid), using the ROI bbox."""
        mz, my, mx = out.shape
        if roi["bbox"]:
            z0, z1, y0, y1, x0, x1 = roi["bbox"]
            z0_c, z1_c = max(0, z0), min(mz, z1)
            y0_c, y1_c = max(0, y0), min(my, y1)
            x0_c, x1_c = max(0, x0), min(mx, x1)
            if z0_c < z1_c and y0_c < y1_c and x0_c < x1_c:
                sub_mask = mask[
                    (z0_c - z0) : (z1_c - z0),
                    (y0_c - y0) : (y1_c - y0),
                    (x0_c - x0) : (x1_c - x0),
                ]
                out[z0_c:z1_c, y0_c:y1_c, x0_c:x1_c][sub_mask] = value
        elif roi["shape3d"] == (mz, my, mx):
            out[mask] = value

    def write_rois_as_labels(self, snapshot, filepath: str, sort_by_volume: bool = True) -> str:
        """Worker-safe (uses only the snapshot): combine the ROIs into one
        multi-label image (.nii.gz) + a JSON sidecar {index: {name, color}}.
        If sort_by_volume, largest first so nested structures burn on top.
        Returns the status message; raises on write errors."""
        import os
        import json
        import numpy as np
        import SimpleITK as sitk

        rois = list(snapshot["rois"])
        if sort_by_volume and len(rois) > 1:
            rois.sort(key=lambda r: int(np.count_nonzero(r["data"])), reverse=True)

        labels_arr = np.zeros(snapshot["shape3d"], dtype=np.int32)
        label_json = {}
        for idx, roi in enumerate(rois, start=1):
            self._paste_roi_mask(roi, roi["data"] > 0, labels_arr, idx)
            try:
                rgb = [max(0, min(255, int(c))) for c in roi["color"][:3]]
            except Exception:
                rgb = [255, 0, 0]
            label_json[str(idx)] = {"name": roi["name"], "color": rgb}
            roi["saved_path"], roi["saved_label"] = filepath, idx

        if len(rois) < 256:
            dtype = np.uint8
        elif len(rois) < 65536:
            dtype = np.uint16
        else:
            dtype = np.int32

        dir_path = os.path.dirname(os.path.abspath(filepath))
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        sitk_img = sitk.GetImageFromArray(labels_arr.astype(dtype))
        base_sitk = snapshot["sitk_image"]
        if base_sitk is not None:
            sitk_img.SetSpacing(base_sitk.GetSpacing())
            sitk_img.SetOrigin(base_sitk.GetOrigin())
            sitk_img.SetDirection(base_sitk.GetDirection())
        sitk.WriteImage(sitk_img, filepath)

        # Side-car json: the label entries are replaced, other keys (unit...) kept
        from vvv.core.sidecar import update_sidecar

        def is_label_entry(key):
            return key.isdigit() or key in ("labels", "colors")

        json_path = update_sidecar(filepath, label_json, drop=is_label_entry)
        snapshot["saved_json_path"] = json_path

        side = f" (+ {os.path.basename(json_path)})" if json_path else ""
        return f"Saved: {os.path.basename(filepath)}{side}"

    def write_rois_as_individual_files(self, snapshot, out_dir: str, auto_crop: bool = True) -> str:
        """Worker-safe (uses only the snapshot): one binary mask file per ROI
        (<roi_name>.nii.gz) in out_dir; without auto_crop each mask has the
        base image grid. Returns the status message; raises on write errors."""
        import os
        import numpy as np
        import SimpleITK as sitk

        os.makedirs(out_dir, exist_ok=True)
        saved_count = 0
        for roi in snapshot["rois"]:
            # Sanitize filename
            clean_name = "".join(
                c for c in roi["name"] if c.isalnum() or c in (" ", "_", "-")
            ).strip()
            if not clean_name:
                clean_name = f"roi_{saved_count + 1}"
            out_file = os.path.join(out_dir, f"{clean_name}.nii.gz")

            mask_arr = (roi["data"] > 0).astype(np.uint8)
            if auto_crop and roi["sitk_image"] is not None:
                # The ROI's own cropped grid
                sitk_crop = sitk.GetImageFromArray(mask_arr)
                sitk_crop.CopyInformation(roi["sitk_image"])
                sitk.WriteImage(sitk_crop, out_file)
                roi["saved_path"] = out_file
                saved_count += 1
                continue

            # Full uncropped volume
            full_mask = np.zeros(snapshot["shape3d"], dtype=np.uint8)
            self._paste_roi_mask(roi, mask_arr > 0, full_mask, 1)
            sitk_full = sitk.GetImageFromArray(full_mask)
            if snapshot["sitk_image"] is not None:
                sitk_full.CopyInformation(snapshot["sitk_image"])
            sitk.WriteImage(sitk_full, out_file)
            roi["saved_path"] = out_file
            saved_count += 1

        return f"Saved {saved_count} ROI files to {os.path.basename(out_dir)}/"

    def attach_saved_rois(self, base_id: str, snapshot) -> None:
        """Main thread, after a batch save: each saved ROI now comes from the
        file it was written to (its source, reload), as after a single ROI
        save; the file it was read from is left as it was."""
        import os

        if not self.api:
            return
        vs = self.api.get_view_states().get(base_id)
        volumes = self.api.get_volumes()
        if not vs:
            return
        json_path = snapshot.get("saved_json_path")
        for r in snapshot["rois"]:
            roi_id, path = r.get("roi_id"), r.get("saved_path")
            roi, vol = vs.rois.get(roi_id), volumes.get(roi_id)
            if not path or roi is None or vol is None:
                continue
            label = r.get("saved_label")
            vol.path = path
            vol.file_paths = [path]
            if label is not None and json_path and os.path.exists(json_path):
                vol.file_paths.append(json_path)
            vol.update_mtime_tracker()
            vol._is_outdated = False
            roi.rtstruct_info = None
            roi.source_type = "Binary" if label is None else "Label Map"
            roi.source_mode = "Target FG (val)"
            roi.source_val = 1.0 if label is None else float(label)
        self.api.request_refresh()

    def save_filtered_rois_as_labels(
        self, base_id: str, filepath: str, sort_by_volume: bool = True
    ) -> bool:
        """Main thread, synchronous: collect + write_rois_as_labels."""
        snapshot = self._collect_or_notify(base_id)
        if snapshot is None:
            return False
        self.api.notify(self.write_rois_as_labels(snapshot, filepath, sort_by_volume))
        self.attach_saved_rois(base_id, snapshot)
        return True

    def save_filtered_rois_as_individual_files(
        self, base_id: str, out_dir: str, auto_crop: bool = True
    ) -> bool:
        """Main thread, synchronous: collect + write_rois_as_individual_files."""
        snapshot = self._collect_or_notify(base_id)
        if snapshot is None:
            return False
        self.api.notify(self.write_rois_as_individual_files(snapshot, out_dir, auto_crop))
        self.attach_saved_rois(base_id, snapshot)
        return True

    def _collect_or_notify(self, base_id: str):
        """collect_filtered_rois, or None after telling the user why (main thread)."""
        snapshot = self.collect_filtered_rois(base_id)
        if snapshot is None:
            if self.api:
                self.api.notify("Base image not found.")
            return None
        if not snapshot["rois"]:
            self.api.notify("No filtered ROIs to save.")
            return None
        return snapshot

