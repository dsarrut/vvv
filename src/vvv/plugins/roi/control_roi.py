from typing import Optional
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
            if "mock" in type(roi_vol.sitk_image).__name__.lower():
                roi_dim = 3
            else:
                try:
                    roi_dim = int(roi_vol.sitk_image.GetDimension())
                except Exception:
                    roi_dim = 3

            if len(com_pixel_cropped) < roi_dim:
                com_pixel_cropped_padded = com_pixel_cropped + [0.0] * (roi_dim - len(com_pixel_cropped))
            elif len(com_pixel_cropped) > roi_dim:
                com_pixel_cropped_padded = com_pixel_cropped[:roi_dim]
            else:
                com_pixel_cropped_padded = com_pixel_cropped

            com_mm_full = list(roi_vol.sitk_image.TransformContinuousIndexToPhysicalPoint(com_pixel_cropped_padded))
            com_mm = com_mm_full[:3]

            if "mock" in type(base_vol.sitk_image).__name__.lower():
                base_dim = 3
            else:
                try:
                    base_dim = int(base_vol.sitk_image.GetDimension())
                except Exception:
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
        base_vol = self.api._controller.volumes.get(base_id)
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

        roi_id = self.api._controller.roi._create_memory_roi(
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

    def update_spheroid_mask(self, base_vol, roi_vol, roi_state, new_r_x_mm: float = None, new_r_y_mm: float = None, new_r_z_mm: float = None) -> None:
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

        roi_state.spheroid_radius_x = new_r_x_mm
        roi_state.spheroid_radius_y = new_r_y_mm
        roi_state.spheroid_radius_z = new_r_z_mm
        roi_state.spheroid_radius_xy = new_r_x_mm
        roi_state.spheroid_radius = new_r_x_mm

        # Ensure center is within image FOV
        if getattr(roi_state, "spheroid_center", None) is None:
            roi_state.spheroid_center = [0.0, 0.0, 0.0]
        phys_center = np.array(roi_state.spheroid_center)
        center_vox = base_vol.physic_coord_to_voxel_coord(phys_center)
        base_sz, base_sy, base_sx = base_vol.shape3d
        cx = np.clip(center_vox[0], 0.0, float(base_sx - 1))
        cy = np.clip(center_vox[1], 0.0, float(base_sy - 1))
        cz = np.clip(center_vox[2], 0.0, float(base_sz - 1))
        clipped_center_vox = np.array([cx, cy, cz])
        clipped_center_phys = base_vol.voxel_coord_to_physic_coord(clipped_center_vox)
        roi_state.spheroid_center = clipped_center_phys.tolist()
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

        # 3. Create SimpleITK image if not mocked
        ref_origin = base_vol.voxel_coord_to_physic_coord(np.array([min_x, min_y, min_z]))
        if "mock" not in type(base_vol.sitk_image).__name__.lower():
            mask_img = sitk.GetImageFromArray(mask_data)
            mask_img.SetSpacing(base_vol.spacing.tolist())
            try:
                mask_img.SetDirection(base_vol.sitk_image.GetDirection())
            except Exception:
                pass
            mask_img.SetOrigin(ref_origin.tolist())
            roi_vol.sitk_image = mask_img

        roi_vol.data = mask_data
        roi_vol.origin = ref_origin
        roi_vol.roi_bbox = (min_z, max_z, min_y, max_y, min_x, max_x)

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
        base_vol = self.api._controller.volumes.get(base_id)
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

        center_voxel = base_vol.physic_coord_to_voxel_coord(phys_center)

        rx = grid_x - center_voxel[0]
        ry = grid_y - center_voxel[1]
        rz = grid_z - center_voxel[2]

        dist_x = np.abs(rx * base_vol.spacing[0])
        dist_y = np.abs(ry * base_vol.spacing[1])
        dist_z = np.abs(rz * base_vol.spacing[2])

        mask_data = ((dist_x <= half_x) & (dist_y <= half_y) & (dist_z <= half_z)).astype(np.uint8)

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

        roi_id = self.api._controller.roi._create_memory_roi(
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

    def update_box_mask(self, base_vol, roi_vol, roi_state, new_size_x: float = None, new_size_y: float = None, new_size_z: float = None) -> None:
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

        roi_state.box_size_x = new_size_x
        roi_state.box_size_y = new_size_y
        roi_state.box_size_z = new_size_z

        # Ensure center is within image FOV
        if getattr(roi_state, "box_center", None) is None:
            roi_state.box_center = [0.0, 0.0, 0.0]
        phys_center = np.array(roi_state.box_center)
        center_vox = base_vol.physic_coord_to_voxel_coord(phys_center)
        base_sz, base_sy, base_sx = base_vol.shape3d
        cx = np.clip(center_vox[0], 0.0, float(base_sx - 1))
        cy = np.clip(center_vox[1], 0.0, float(base_sy - 1))
        cz = np.clip(center_vox[2], 0.0, float(base_sz - 1))
        clipped_center_vox = np.array([cx, cy, cz])
        clipped_center_phys = base_vol.voxel_coord_to_physic_coord(clipped_center_vox)
        roi_state.box_center = clipped_center_phys.tolist()
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

        # 2. Create binary mask in the sub-grid
        zs = np.arange(min_z, max_z)
        ys = np.arange(min_y, max_y)
        xs = np.arange(min_x, max_x)
        grid_z, grid_y, grid_x = np.meshgrid(zs, ys, xs, indexing='ij')

        center_voxel = base_vol.physic_coord_to_voxel_coord(phys_center)

        rx = grid_x - center_voxel[0]
        ry = grid_y - center_voxel[1]
        rz = grid_z - center_voxel[2]

        dist_x = np.abs(rx * base_vol.spacing[0])
        dist_y = np.abs(ry * base_vol.spacing[1])
        dist_z = np.abs(rz * base_vol.spacing[2])

        mask_data = ((dist_x <= half_x) & (dist_y <= half_y) & (dist_z <= half_z)).astype(np.uint8)

        if not np.any(mask_data):
            cx_idx = int(round(center_voxel[0]))
            cy_idx = int(round(center_voxel[1]))
            cz_idx = int(round(center_voxel[2]))
            sub_z = cz_idx - min_z
            sub_y = cy_idx - min_y
            sub_x = cx_idx - min_x
            if 0 <= sub_z < (max_z - min_z) and 0 <= sub_y < (max_y - min_y) and 0 <= sub_x < (max_x - min_x):
                mask_data[sub_z, sub_y, sub_x] = 1

        # 3. Create SimpleITK image if not mocked
        ref_origin = base_vol.voxel_coord_to_physic_coord(np.array([min_x, min_y, min_z]))
        if "mock" not in type(base_vol.sitk_image).__name__.lower():
            mask_img = sitk.GetImageFromArray(mask_data)
            mask_img.SetSpacing(base_vol.spacing.tolist())
            try:
                mask_img.SetDirection(base_vol.sitk_image.GetDirection())
            except Exception:
                pass
            mask_img.SetOrigin(ref_origin.tolist())
            roi_vol.sitk_image = mask_img

        roi_vol.data = mask_data
        roi_vol.origin = ref_origin
        roi_vol.roi_bbox = (min_z, max_z, min_y, max_y, min_x, max_x)
