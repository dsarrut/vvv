import threading
from typing import Optional
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin


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
            if self.ui:
                self.ui.refresh_rois_ui()

    def on_sort_rois(self) -> None:
        if not self.api:
            return
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
        filter_text = self.roi_filters.get(vs_id, "")
        invert = self.roi_filter_inverts.get(vs_id, False)
        sort_order = self.roi_sort_orders.get(vs_id, 0)

        roi_items = list(viewer.view_state.rois.items())
        if sort_order == 1:
            roi_items.sort(key=lambda x: x[1].name.lower())
        elif sort_order == -1:
            roi_items.sort(key=lambda x: x[1].name.lower(), reverse=True)

        # Filter the items
        filtered_roi_ids = []
        for roi_id, roi in roi_items:
            match = (filter_text in roi.name.lower()) if filter_text else True
            if filter_text and ((not match) if not invert else match):
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
        win_w = dpg.get_item_width(f"win_{viewer.tag}") if dpg.does_item_exist(f"win_{viewer.tag}") else 300
        win_h = dpg.get_item_height(f"win_{viewer.tag}") if dpg.does_item_exist(f"win_{viewer.tag}") else 300
        if not ppm or ppm <= 0:
            ppm = 1.0
        fov = min(win_w / ppm, win_h / ppm)
        r_mm = 0.1 * fov

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
        win_w = dpg.get_item_width(f"win_{viewer.tag}") if dpg.does_item_exist(f"win_{viewer.tag}") else 300
        win_h = dpg.get_item_height(f"win_{viewer.tag}") if dpg.does_item_exist(f"win_{viewer.tag}") else 300
        if not ppm or ppm <= 0:
            ppm = 1.0
        fov = min(win_w / ppm, win_h / ppm)
        half_x = 0.1 * fov
        half_y = 0.1 * fov
        half_z = 0.1 * fov
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

    def save_filtered_rois_as_labels(
        self, base_id: str, filepath: str, sort_by_volume: bool = True
    ) -> bool:
        """
        Combines all filtered ROIs on base_id into a single multi-label image (.nii.gz)
        and exports a JSON sidecar mapping each label index to {name, color}.
        If sort_by_volume is True, ROIs are sorted largest-to-smallest so smaller
        nested structures burn on top without being completely overwritten.
        """
        import os
        import json
        import numpy as np
        import SimpleITK as sitk

        if not self.api:
            return False

        volumes = self.api.get_volumes()
        view_states = self.api.get_view_states()

        base_vol = volumes.get(base_id)
        base_vs = view_states.get(base_id)
        if not base_vol or not base_vs:
            self.api.notify("Base image not found.")
            return False

        # Get filtered ROIs
        filter_text = self.roi_filters.get(base_id, "").strip().lower()
        invert = self.roi_filter_inverts.get(base_id, False)

        filtered_rois = []
        for roi_id, roi_state in base_vs.rois.items():
            if filter_text:
                match = filter_text in roi_state.name.lower()
                if (not match) if not invert else match:
                    continue
            filtered_rois.append((roi_id, roi_state))

        if not filtered_rois:
            self.api.run_on_main_thread(lambda: self.api.notify("No filtered ROIs to save."))
            return False

        # Calculate volumes for sorting if requested
        if sort_by_volume and len(filtered_rois) > 1:
            def _roi_volume(item):
                rid, _ = item
                r_vol = volumes.get(rid)
                if not r_vol or r_vol.data is None:
                    return 0
                r_data = r_vol.data[0] if r_vol.data.ndim == 4 else r_vol.data
                return int(np.count_nonzero(r_data))

            # Largest first (descending), so large bodies burn first and smaller organs burn on top
            filtered_rois.sort(key=_roi_volume, reverse=True)

        mz, my, mx = base_vol.shape3d
        labels_arr = np.zeros((mz, my, mx), dtype=np.int32)
        label_json = {}

        for idx, (roi_id, roi_state) in enumerate(filtered_rois, start=1):
            r_vol = volumes.get(roi_id)
            if not r_vol or r_vol.data is None:
                continue

            r_data = r_vol.data[0] if r_vol.data.ndim == 4 else r_vol.data
            mask = r_data > 0

            if hasattr(r_vol, "roi_bbox") and r_vol.roi_bbox:
                z0, z1, y0, y1, x0, x1 = r_vol.roi_bbox
                z0_c, z1_c = max(0, z0), min(mz, z1)
                y0_c, y1_c = max(0, y0), min(my, y1)
                x0_c, x1_c = max(0, x0), min(mx, x1)

                if z0_c < z1_c and y0_c < y1_c and x0_c < x1_c:
                    sub_mask = mask[
                        (z0_c - z0) : (z1_c - z0),
                        (y0_c - y0) : (y1_c - y0),
                        (x0_c - x0) : (x1_c - x0),
                    ]
                    sub_slice = labels_arr[z0_c:z1_c, y0_c:y1_c, x0_c:x1_c]
                    sub_slice[sub_mask] = idx
            else:
                rmz, rmy, rmx = r_vol.shape3d
                if (rmz, rmy, rmx) == (mz, my, mx):
                    labels_arr[mask] = idx

            color = getattr(roi_state, "color", None) or [255, 0, 0]
            try:
                rgb = [max(0, min(255, int(c))) for c in color[:3]]
            except Exception:
                rgb = [255, 0, 0]

            label_json[str(idx)] = {
                "name": roi_state.name,
                "color": rgb,
            }

        if len(filtered_rois) < 256:
            dtype = np.uint8
        elif len(filtered_rois) < 65536:
            dtype = np.uint16
        else:
            dtype = np.int32

        dir_path = os.path.dirname(os.path.abspath(filepath))
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        sitk_img = sitk.GetImageFromArray(labels_arr.astype(dtype))
        if hasattr(base_vol, "sitk_image") and base_vol.sitk_image is not None:
            try:
                sitk_img.SetSpacing(base_vol.sitk_image.GetSpacing())
            except Exception:
                pass
            try:
                sitk_img.SetOrigin(base_vol.sitk_image.GetOrigin())
            except Exception:
                pass
            try:
                sitk_img.SetDirection(base_vol.sitk_image.GetDirection())
            except Exception:
                pass

        sitk.WriteImage(sitk_img, filepath)

        # JSON sidecar
        if filepath.lower().endswith(".nii.gz"):
            json_path = filepath[:-7] + ".json"
        else:
            json_path = os.path.splitext(filepath)[0] + ".json"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(label_json, f, indent=4)

        base_name = os.path.basename(filepath)
        self.api.run_on_main_thread(lambda: self.api.notify(f"Saved: {base_name}"))
        return True

    def save_filtered_rois_as_individual_files(
        self, base_id: str, out_dir: str, auto_crop: bool = True
    ) -> bool:
        """
        Exports currently filtered ROIs on base_id as individual binary mask files
        into out_dir (<roi_name>.nii.gz).
        If auto_crop is False, each mask is saved matching base_vol shape/origin.
        """
        import os
        import numpy as np
        import SimpleITK as sitk

        if not self.api:
            return False

        volumes = self.api.get_volumes()
        view_states = self.api.get_view_states()

        base_vol = volumes.get(base_id)
        base_vs = view_states.get(base_id)
        if not base_vol or not base_vs:
            self.api.notify("Base image not found.")
            return False

        filter_text = self.roi_filters.get(base_id, "").strip().lower()
        invert = self.roi_filter_inverts.get(base_id, False)

        filtered_rois = []
        for roi_id, roi_state in base_vs.rois.items():
            if filter_text:
                match = filter_text in roi_state.name.lower()
                if (not match) if not invert else match:
                    continue
            filtered_rois.append((roi_id, roi_state))

        if not filtered_rois:
            self.api.run_on_main_thread(lambda: self.api.notify("No filtered ROIs to save."))
            return False

        os.makedirs(out_dir, exist_ok=True)
        saved_count = 0

        for roi_id, roi_state in filtered_rois:
            r_vol = volumes.get(roi_id)
            if not r_vol or r_vol.data is None:
                continue

            # Sanitize filename
            clean_name = "".join(
                c for c in roi_state.name if c.isalnum() or c in (" ", "_", "-")
            ).strip()
            if not clean_name:
                clean_name = f"roi_{saved_count + 1}"
            out_file = os.path.join(out_dir, f"{clean_name}.nii.gz")

            r_data = r_vol.data[0] if r_vol.data.ndim == 4 else r_vol.data
            mask_arr = (r_data > 0).astype(np.uint8)

            if auto_crop:
                # Use roi's own cropped sitk_image if available
                if hasattr(r_vol, "sitk_image") and r_vol.sitk_image is not None:
                    sitk_crop = sitk.GetImageFromArray(mask_arr)
                    sitk_crop.CopyInformation(r_vol.sitk_image)
                    sitk.WriteImage(sitk_crop, out_file)
                    saved_count += 1
                    continue

            # Full uncropped volume
            mz, my, mx = base_vol.shape3d
            full_mask = np.zeros((mz, my, mx), dtype=np.uint8)

            if hasattr(r_vol, "roi_bbox") and r_vol.roi_bbox:
                z0, z1, y0, y1, x0, x1 = r_vol.roi_bbox
                z0_c, z1_c = max(0, z0), min(mz, z1)
                y0_c, y1_c = max(0, y0), min(my, y1)
                x0_c, x1_c = max(0, x0), min(mx, x1)

                if z0_c < z1_c and y0_c < y1_c and x0_c < x1_c:
                    sub_m = mask_arr[
                        (z0_c - z0) : (z1_c - z0),
                        (y0_c - y0) : (y1_c - y0),
                        (x0_c - x0) : (x1_c - x0),
                    ]
                    full_mask[z0_c:z1_c, y0_c:y1_c, x0_c:x1_c] = sub_m
            else:
                rmz, rmy, rmx = r_vol.shape3d
                if (rmz, rmy, rmx) == (mz, my, mx):
                    full_mask = mask_arr

            sitk_full = sitk.GetImageFromArray(full_mask)
            if hasattr(base_vol, "sitk_image") and base_vol.sitk_image is not None:
                sitk_full.CopyInformation(base_vol.sitk_image)

            sitk.WriteImage(sitk_full, out_file)
            saved_count += 1

        out_name = os.path.basename(out_dir)
        self.api.run_on_main_thread(
            lambda: self.api.notify(f"Saved {saved_count} ROI files to {out_name}/")
        )
        return True

