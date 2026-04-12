import os
import json
import numpy as np
import SimpleITK as sitk
from vvv.config import ROI_COLORS
from vvv.math.image import VolumeData


class ROIState:
    def __init__(
        self, volume_id, name, color, source_mode="Ignore BG (val)", source_val=0.0
    ):
        self.volume_id = volume_id
        self.name = name
        self.color = color
        self.opacity = 0.5
        self.visible = True
        self.is_contour = False
        self.source_mode = source_mode
        self.source_val = source_val

    def to_dict(self):
        return {
            "volume_id": self.volume_id,
            "name": self.name,
            "color": self.color,
            "opacity": self.opacity,
            "visible": self.visible,
            "is_contour": self.is_contour,
            "source_mode": self.source_mode,
            "source_val": self.source_val,
        }

    def from_dict(self, d):
        self.name = d.get("name", self.name)
        self.color = d.get("color", self.color)
        self.opacity = d.get("opacity", self.opacity)
        self.visible = d.get("visible", self.visible)
        self.is_contour = d.get("is_contour", self.is_contour)
        self.source_mode = d.get("source_mode", "Ignore BG (val)")
        self.source_val = d.get("source_val", 0.0)


class ROIManager:
    """Manages the loading, processing, and mathematical statistics of Regions of Interest."""

    def __init__(self, controller):
        self.controller = controller

    # ==========================================
    # INTERNAL HELPERS
    # ==========================================

    def _clean_roi_name(self, filepath):
        """Strips common medical extensions to generate a clean display name."""
        name = os.path.basename(filepath)
        for ext in [
            ".nii.gz",
            ".nii",
            ".mhd",
            ".mha",
            ".nrrd",
            ".dcm",
            ".tif",
            ".png",
            ".jpg",
        ]:
            if name.lower().endswith(ext):
                return name[: -len(ext)]
        return name

    def _apply_binarization_rule(self, mask_vol, mode, target_val):
        """Applies the target value rules and safely updates the SimpleITK header."""
        if mode == "Target FG (val)":
            mask_vol.data = (mask_vol.data == target_val).astype(np.uint8)
        else:
            mask_vol.data = (mask_vol.data != target_val).astype(np.uint8)

        new_img = sitk.GetImageFromArray(mask_vol.data)
        new_img.SetSpacing(mask_vol.sitk_image.GetSpacing())
        new_img.SetOrigin(mask_vol.sitk_image.GetOrigin())
        new_img.SetDirection(mask_vol.sitk_image.GetDirection())
        mask_vol.sitk_image = new_img

    def process_binary_mask(self, base_vol, mask_vol):
        """Helper to resample and autocrop a binary mask."""
        if (
            mask_vol.shape3d != base_vol.shape3d
            or not np.allclose(mask_vol.spacing, base_vol.spacing, atol=1e-4)
            or not np.allclose(mask_vol.origin, base_vol.origin, atol=1e-4)
        ):
            resampler = sitk.ResampleImageFilter()
            resampler.SetReferenceImage(base_vol.sitk_image)
            resampler.SetInterpolator(sitk.sitkNearestNeighbor)
            resampler.SetDefaultPixelValue(0)

            mask_vol.sitk_image = resampler.Execute(mask_vol.sitk_image)
            mask_vol.data = sitk.GetArrayFromImage(mask_vol.sitk_image)
            mask_vol.shape3d = base_vol.shape3d
            mask_vol.spacing = base_vol.spacing
            mask_vol.origin = base_vol.origin

        # 3D Autocrop
        coords = np.argwhere(mask_vol.data > 0)
        if coords.size > 0:
            if mask_vol.data.ndim == 4:
                z0, y0, x0 = coords[:, 1:].min(axis=0)
                z1, y1, x1 = coords[:, 1:].max(axis=0) + 1
                mask_vol.data = mask_vol.data[:, z0:z1, y0:y1, x0:x1]
            else:
                z0, y0, x0 = coords.min(axis=0)
                z1, y1, x1 = coords.max(axis=0) + 1
                mask_vol.data = mask_vol.data[z0:z1, y0:y1, x0:x1]
            mask_vol.roi_bbox = (z0, z1, y0, y1, x0, x1)
        else:
            mask_vol.roi_bbox = (0, 0, 0, 0, 0, 0)
            if mask_vol.data.ndim == 4:
                mask_vol.data = np.zeros(
                    (mask_vol.data.shape[0], 0, 0, 0), dtype=mask_vol.data.dtype
                )
            else:
                mask_vol.data = np.zeros((0, 0, 0), dtype=mask_vol.data.dtype)

    # ==========================================
    # PUBLIC ROI API
    # ==========================================

    def load_label_map(self, base_id, filepath, start_color_idx):
        json_path = filepath.rsplit(".", 1)[0] + ".json"
        if filepath.endswith(".nii.gz"):
            json_path = filepath[:-7] + ".json"

        label_dict = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r") as f:
                    raw_dict = json.load(f)
                    label_dict = {int(k): str(v) for k, v in raw_dict.items()}
            except Exception as e:
                print(f"Failed to load JSON {json_path}: {e}")

        temp_img = sitk.ReadImage(filepath)
        temp_data = sitk.GetArrayViewFromImage(temp_img)
        unique_vals = np.unique(temp_data)

        loaded_count = 0
        base_name = self._clean_roi_name(filepath)

        for val in unique_vals:
            if val == 0:
                continue

            color = ROI_COLORS[(start_color_idx + loaded_count) % len(ROI_COLORS)]
            roi_name = label_dict.get(int(val), f"{base_name} - Lbl {val}")

            self.load_binary_mask(
                base_id,
                filepath,
                name=roi_name,
                color=color,
                mode="Target FG (val)",
                target_val=float(val),
            )
            loaded_count += 1

        return loaded_count

    def load_binary_mask(
        self,
        base_id,
        filepath,
        name=None,
        color=None,
        mode="Ignore BG (val)",
        target_val=0.0,
    ):
        if color is None:
            color = [255, 50, 50]

        base_vol = self.controller.volumes[base_id]

        # 1. THE FAST PATH: Instantiate and crop natively in C++ via SimpleITK
        mask_vol = VolumeData(
            filepath, is_roi=True, roi_mode=mode, roi_target_val=target_val
        )

        # 2. Apply the final binarization rule to ensure the remaining pixels are exactly 0 and 1
        self._apply_binarization_rule(mask_vol, mode, target_val)

        if mask_vol.data.size == 0:
            raise ValueError("Outside the base image FOV (or completely empty).")

        # 3. Calculate the exact bounding box using Physics instead of heavy array resampling
        # Map the ROI's new physical origin back to the Base Image's voxel grid
        start_vox = base_vol.physic_coord_to_voxel_coord(mask_vol.origin)
        x0, y0, z0 = [int(round(v)) for v in start_vox]

        # The size is just the shape of the newly cropped array!
        mz, my, mx = mask_vol.shape3d
        z1, y1, x1 = z0 + mz, y0 + my, x0 + mx

        mask_vol.roi_bbox = (z0, z1, y0, y1, x0, x1)

        # 4. Register the Volume and State
        mask_id = str(self.controller.next_image_id)
        self.controller.next_image_id += 1
        self.controller.volumes[mask_id] = mask_vol

        if name is None:
            name = self._clean_roi_name(filepath)

        roi_state = ROIState(
            mask_id, name, color, source_mode=mode, source_val=target_val
        )
        self.controller.view_states[base_id].rois[mask_id] = roi_state
        self.controller.view_states[base_id].is_data_dirty = True

        return mask_id

    def get_roi_stats(self, base_vs_id, roi_id, is_overlay=False):
        if (
            base_vs_id not in self.controller.view_states
            or roi_id not in self.controller.volumes
        ):
            return None

        vs = self.controller.view_states[base_vs_id]
        roi_vol = self.controller.volumes[roi_id]

        voxel_vol_mm3 = abs(np.prod(roi_vol.spacing))
        mask = roi_vol.data > 0
        voxel_count = np.count_nonzero(mask)
        vol_cc = (voxel_count * voxel_vol_mm3) / 1000.0

        if voxel_count == 0:
            return {
                "vol": 0.0,
                "mean": 0.0,
                "max": 0.0,
                "min": 0.0,
                "std": 0.0,
                "peak": 0.0,
                "mass": 0.0,
            }

        if is_overlay:
            if not vs.display.overlay_id or vs.display.overlay_data is None:
                return None
            target_data = vs.display.overlay_data
            ov_vol = self.controller.volumes[vs.display.overlay_id]
            if ov_vol.num_timepoints > 1:
                t = min(vs.camera.time_idx, ov_vol.num_timepoints - 1)
                target_data = target_data[t]
        else:
            base_vol = self.controller.volumes[base_vs_id]
            target_data = base_vol.data
            if base_vol.num_timepoints > 1:
                t = min(vs.camera.time_idx, base_vol.num_timepoints - 1)
                target_data = target_data[t]

        if hasattr(roi_vol, "roi_bbox"):
            z0, z1, y0, y1, x0, x1 = roi_vol.roi_bbox
            if z0 != z1:
                target_data = target_data[z0:z1, y0:y1, x0:x1]

        pixels = target_data[mask]
        mean_val = float(np.mean(pixels))
        peak_val = float(np.percentile(pixels, 95))

        density_g_cc = (mean_val / 1000.0) + 1.0
        mass_g = vol_cc * density_g_cc

        return {
            "vol": vol_cc,
            "mean": mean_val,
            "max": float(np.max(pixels)),
            "min": float(np.min(pixels)),
            "std": float(np.std(pixels)),
            "peak": peak_val,
            "mass": mass_g,
        }

    def center_on_roi(self, base_id, roi_id):
        if (
            base_id not in self.controller.view_states
            or roi_id not in self.controller.volumes
        ):
            return

        mask_vol = self.controller.volumes[roi_id]
        if not hasattr(mask_vol, "roi_bbox"):
            return

        z0, z1, y0, y1, x0, x1 = mask_vol.roi_bbox
        if z0 == z1:
            return

        cx = (x0 + x1 - 1) / 2.0
        cy = (y0 + y1 - 1) / 2.0
        cz = (z0 + z1 - 1) / 2.0

        vs = self.controller.view_states[base_id]
        vs.camera.crosshair_voxel = [cx, cy, cz, vs.camera.time_idx]
        vs.camera.crosshair_phys_coord = mask_vol.voxel_coord_to_physic_coord(
            np.array([cx, cy, cz])
        )

        self.controller.sync.propagate_sync(base_id)

        # State-Only: Write the target center to the synced ViewStates!
        target_ids = self.controller.sync.get_sync_group_vs_ids(
            base_id, active_only=True
        )
        for tid in target_ids:
            t_vs = self.controller.view_states[tid]
            t_vs.camera.target_center = vs.camera.crosshair_phys_coord

    def reload_roi(self, base_id, roi_id):
        if (
            base_id not in self.controller.view_states
            or roi_id not in self.controller.volumes
        ):
            return

        mask_vol = self.controller.volumes[roi_id]
        roi_state = self.controller.view_states[base_id].rois[roi_id]
        mask_vol.reload()

        mode = getattr(roi_state, "source_mode", "Ignore BG (val)")
        target_val = getattr(roi_state, "source_val", 0.0)

        # Apply rule BEFORE resampling
        self._apply_binarization_rule(mask_vol, mode, target_val)

        base_vol = self.controller.volumes[base_id]
        self.process_binary_mask(base_vol, mask_vol)

        self.controller.view_states[base_id].is_data_dirty = True
        self.controller.update_all_viewers_of_image(base_id)

        if self.controller.gui:
            self.controller.gui.show_status_message(f"Reloaded: {roi_state.name}")

    def close_roi(self, base_id, roi_id):
        if base_id in self.controller.view_states:
            vs = self.controller.view_states[base_id]
            if roi_id in vs.rois:
                del vs.rois[roi_id]
                vs.is_data_dirty = True

        if roi_id in self.controller.volumes:
            del self.controller.volumes[roi_id]

        self.controller.update_all_viewers_of_image(base_id)
