import os
import json
import numpy as np
import SimpleITK as sitk
from vvv.image import VolumeData
from vvv.config import ROI_COLORS


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

        # We save the rules so history loads perfectly!
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

    def load_label_map(self, base_id, filepath, start_color_idx):
        # 1. Attempt to find a JSON sidecar dictionary
        json_path = filepath.rsplit(".", 1)[0] + ".json"
        if filepath.endswith(".nii.gz"):
            json_path = filepath[:-7] + ".json"

        label_dict = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r") as f:
                    raw_dict = json.load(f)
                    # Force integer keys in case JSON parsed them as strings
                    label_dict = {int(k): str(v) for k, v in raw_dict.items()}
            except Exception as e:
                print(f"Failed to load JSON {json_path}: {e}")

        # 2. Read the image quickly just to get the unique integer values
        temp_img = sitk.ReadImage(filepath)
        temp_data = sitk.GetArrayViewFromImage(temp_img)
        unique_vals = np.unique(temp_data)

        loaded_count = 0
        base_name = os.path.basename(filepath)
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
            if base_name.lower().endswith(ext):
                base_name = base_name[: -len(ext)]
                break

        # 3. Process every non-zero label as a distinct ROI
        for val in unique_vals:
            if val == 0:
                continue  # 0 is strictly background in label maps

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
        color=[255, 50, 50],
        mode="Ignore BG (val)",
        target_val=0.0,
    ):
        base_vol = self.controller.volumes[base_id]
        mask_vol = VolumeData(filepath)

        # Apply rule to raw data BEFORE any resampling or cropping!
        if mode == "Target FG (val)":
            mask_vol.data = (mask_vol.data == target_val).astype(np.uint8)
        else:
            mask_vol.data = (mask_vol.data != target_val).astype(np.uint8)

        # Update SITK image to ensure Resampler behaves correctly with the new binary data
        new_img = sitk.GetImageFromArray(mask_vol.data)
        new_img.SetSpacing(mask_vol.sitk_image.GetSpacing())
        new_img.SetOrigin(mask_vol.sitk_image.GetOrigin())
        new_img.SetDirection(mask_vol.sitk_image.GetDirection())
        mask_vol.sitk_image = new_img

        self.process_binary_mask(base_vol, mask_vol)

        # Safeguard warning
        if mask_vol.data.size == 0:
            raise ValueError("Outside the base image FOV (or completely empty).")

        # FIX: Point to the controller's ID tracker
        mask_id = str(self.controller._next_image_id)
        self.controller._next_image_id += 1
        self.controller.volumes[mask_id] = mask_vol

        if name is None:
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
                    name = name[: -len(ext)]
                    break

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

        # 1. Calculate physical volume per voxel in cubic centimeters (cc)
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

        # 2. Extract the target data (Base vs Resampled Overlay)
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

        # 3. Crop the target image to match the ROI's bounding box
        if hasattr(roi_vol, "roi_bbox"):
            z0, z1, y0, y1, x0, x1 = roi_vol.roi_bbox
            if z0 != z1:
                target_data = target_data[z0:z1, y0:y1, x0:x1]

        pixels = target_data[mask]

        # 4. Compute advanced statistics
        mean_val = float(np.mean(pixels))
        peak_val = float(np.percentile(pixels, 95))  # Robust P95 Peak

        # Mass assumes CT Hounsfield Units (Water = 0 = 1g/cc, Air = -1000 = 0g/cc)
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
        if z0 == z1:  # Empty mask
            return

        cx = (x0 + x1 - 1) / 2.0
        cy = (y0 + y1 - 1) / 2.0
        cz = (z0 + z1 - 1) / 2.0

        vs = self.controller.view_states[base_id]

        vs.camera.crosshair_voxel = [cx, cy, cz, vs.camera.time_idx]
        vs.camera.crosshair_phys_coord = mask_vol.voxel_coord_to_physic_coord(
            np.array([cx, cy, cz])
        )

        # FIX: Point to the controller's sync manager
        self.controller.sync.propagate_sync(base_id)

        target_group = vs.sync_group
        # FIX: Point to the controller's viewers
        for viewer in self.controller.viewers.values():
            if viewer.image_id and viewer.view_state:
                if viewer.image_id == base_id or (
                    target_group != 0 and viewer.view_state.sync_group == target_group
                ):
                    viewer.needs_recenter = True
                    viewer.is_geometry_dirty = True

    def reload_roi(self, base_id, roi_id):
        if (
            base_id not in self.controller.view_states
            or roi_id not in self.controller.volumes
        ):
            return

        mask_vol = self.controller.volumes[roi_id]
        roi_state = self.controller.view_states[base_id].rois[roi_id]
        was_reset = mask_vol.reload()

        # Re-apply binarization rule after reloading from disk!
        mode = getattr(roi_state, "source_mode", "Ignore BG (val)")
        target_val = getattr(roi_state, "source_val", 0.0)

        if mode == "Target FG (val)":
            mask_vol.data = (mask_vol.data == target_val).astype(np.uint8)
        else:
            mask_vol.data = (mask_vol.data != target_val).astype(np.uint8)

        new_img = sitk.GetImageFromArray(mask_vol.data)
        new_img.SetSpacing(mask_vol.sitk_image.GetSpacing())
        new_img.SetOrigin(mask_vol.sitk_image.GetOrigin())
        new_img.SetDirection(mask_vol.sitk_image.GetDirection())
        mask_vol.sitk_image = new_img

        base_vol = self.controller.volumes[base_id]
        self.process_binary_mask(base_vol, mask_vol)

        self.controller.view_states[base_id].is_data_dirty = True
        # FIX: Point to the controller's viewer update function
        self.controller.update_all_viewers_of_image(base_id)

        if self.controller.gui:
            self.controller.gui.refresh_rois_ui()
            self.controller.gui.show_status_message(f"Reloaded: {roi_state.name}")

    def close_roi(self, base_id, roi_id):
        """Safely removes an ROI from the view state and frees the volume memory."""
        if base_id in self.controller.view_states:
            vs = self.controller.view_states[base_id]
            if roi_id in vs.rois:
                del vs.rois[roi_id]
                vs.is_data_dirty = True

        if roi_id in self.controller.volumes:
            del self.controller.volumes[roi_id]

        # FIX: Point to the controller's viewer update function
        self.controller.update_all_viewers_of_image(base_id)
