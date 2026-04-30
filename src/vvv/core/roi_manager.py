import os
import json
import numpy as np
import SimpleITK as sitk
from vvv.utils import ViewMode
from vvv.config import ROI_COLORS
from vvv.maths.image import VolumeData


class ROIState:
    def __init__(
        self,
        volume_id,
        name,
        color,
        source_mode="Ignore BG (val)",
        source_val=0.0,
        rtstruct_info=None,
    ):
        self.volume_id = volume_id
        self.name = name
        self.color = color
        self.opacity = 0.5
        self.visible = True
        self.is_contour = False
        self.source_mode = source_mode
        self.source_val = source_val
        self.thickness = 1.0
        self.rtstruct_info = rtstruct_info
        self.polygons = {
            ViewMode.AXIAL: {},
            ViewMode.SAGITTAL: {},
            ViewMode.CORONAL: {},
        }

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
            "thickness": self.thickness,
            "rtstruct_info": getattr(self, "rtstruct_info", None),
        }

    def from_dict(self, d):
        self.name = d.get("name", self.name)
        self.color = d.get("color", self.color)
        self.opacity = d.get("opacity", self.opacity)
        self.visible = d.get("visible", self.visible)
        self.is_contour = d.get("is_contour", self.is_contour)
        self.source_mode = d.get("source_mode", "Ignore BG (val)")
        self.source_val = d.get("source_val", 0.0)
        self.thickness = d.get("thickness", self.thickness)
        self.rtstruct_info = d.get("rtstruct_info", None)


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
        """Helper to natively crop, align, and resample a binary mask."""

        # --- 1. NATIVE CROP FIRST ---
        print("Processing binary mask: Applying native cropping and alignment...")
        # Strip away millions of empty background voxels before doing any heavy math
        coords = np.argwhere(mask_vol.data > 0)
        if coords.size == 0:
            mask_vol.roi_bbox = (0, 0, 0, 0, 0, 0)
            return

        z_max, y_max, x_max = mask_vol.data.shape[-3:]

        if mask_vol.data.ndim == 4:
            z0, y0, x0 = np.maximum(coords[:, 1:].min(axis=0) - 1, 0)
            z1, y1, x1 = np.minimum(
                coords[:, 1:].max(axis=0) + 2, [z_max, y_max, x_max]
            )
            mask_vol.data = np.ascontiguousarray(mask_vol.data[:, z0:z1, y0:y1, x0:x1])
        else:
            z0, y0, x0 = np.maximum(coords.min(axis=0) - 1, 0)
            z1, y1, x1 = np.minimum(coords.max(axis=0) + 2, [z_max, y_max, x_max])
            mask_vol.data = np.ascontiguousarray(mask_vol.data[z0:z1, y0:y1, x0:x1])

        # Update the SimpleITK image to reflect this small, dense block of data
        new_origin = mask_vol.sitk_image.TransformIndexToPhysicalPoint(
            (int(x0), int(y0), int(z0))
        )

        cropped_sitk = sitk.GetImageFromArray(mask_vol.data)
        cropped_sitk.SetSpacing(mask_vol.sitk_image.GetSpacing())
        cropped_sitk.SetDirection(mask_vol.sitk_image.GetDirection())
        cropped_sitk.SetOrigin(new_origin)
        mask_vol.sitk_image = cropped_sitk

        # --- 2. CHECK FOR PERFECT ALIGNMENT ---
        spacing_match = np.allclose(mask_vol.spacing, base_vol.spacing, atol=1e-4)
        dir_match = np.allclose(
            mask_vol.sitk_image.GetDirection(),
            base_vol.sitk_image.GetDirection(),
            atol=1e-4,
        )

        if spacing_match and dir_match:
            base_idx = base_vol.sitk_image.TransformPhysicalPointToContinuousIndex(
                new_origin
            )
            if np.allclose(base_idx, np.round(base_idx), atol=1e-3):
                # FAST PATH: It perfectly aligns. Just calculate the offset.
                bx, by, bz = [int(round(v)) for v in base_idx]
                sz, sy, sx = mask_vol.data.shape[-3:]
                mask_vol.roi_bbox = (bz, bz + sz, by, by + sy, bx, bx + sx)
                return

        # --- 3. TARGETED SUB-GRID RESAMPLING ---
        # Find the physical corners of our tiny cropped ROI
        sz, sy, sx = mask_vol.data.shape[-3:]
        corners = [
            (0, 0, 0),
            (sx, 0, 0),
            (0, sy, 0),
            (sx, sy, 0),
            (0, 0, sz),
            (sx, 0, sz),
            (0, sy, sz),
            (sx, sy, sz),
        ]

        base_indices = []
        for c in corners:
            phys_pt = mask_vol.sitk_image.TransformIndexToPhysicalPoint(c)
            base_indices.append(
                base_vol.sitk_image.TransformPhysicalPointToContinuousIndex(phys_pt)
            )

        base_indices = np.array(base_indices)

        # Calculate the bounding box IN THE BASE IMAGE that covers the ROI
        # Pad by 1 voxel to ensure interpolation doesn't clip the edges
        min_idx = np.floor(base_indices.min(axis=0)).astype(int) - 1
        max_idx = np.ceil(base_indices.max(axis=0)).astype(int) + 2

        base_sz, base_sy, base_sx = base_vol.shape3d
        min_x, max_x = max(0, min_idx[0]), min(base_sx, max_idx[0])
        min_y, max_y = max(0, min_idx[1]), min(base_sy, max_idx[1])
        min_z, max_z = max(0, min_idx[2]), min(base_sz, max_idx[2])

        if min_x >= max_x or min_y >= max_y or min_z >= max_z:
            mask_vol.roi_bbox = (0, 0, 0, 0, 0, 0)
            return

        # Build a pure 3D reference grid to prevent SimpleITK dimension mismatches
        ref_image = sitk.Image(
            int(max_x - min_x),
            int(max_y - min_y),
            int(max_z - min_z),
            sitk.sitkUInt8,
        )
        ref_origin = base_vol.voxel_coord_to_physic_coord(
            np.array([min_x, min_y, min_z])
        )
        ref_image.SetSpacing(base_vol.spacing.tolist())
        ref_image.SetOrigin(ref_origin.tolist())
        ref_image.SetDirection(base_vol.matrix.flatten().tolist())

        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(ref_image)
        resampler.SetInterpolator(sitk.sitkNearestNeighbor)
        resampler.SetDefaultPixelValue(0)

        # Execute resampling ONLY on the tiny grid
        mask_vol.sitk_image = resampler.Execute(mask_vol.sitk_image)
        mask_vol.data = sitk.GetArrayFromImage(mask_vol.sitk_image)

        # --- 4. FINAL TIGHT CROP ---
        # Resampling might have introduced a border of 0s. Clean it up.
        coords2 = np.argwhere(mask_vol.data > 0)
        if coords2.size > 0:
            z_max2, y_max2, x_max2 = mask_vol.data.shape[-3:]
            if mask_vol.data.ndim == 4:
                z0, y0, x0 = np.maximum(coords2[:, 1:].min(axis=0) - 1, 0)
                z1, y1, x1 = np.minimum(
                    coords2[:, 1:].max(axis=0) + 2, [z_max2, y_max2, x_max2]
                )
                mask_vol.data = np.ascontiguousarray(
                    mask_vol.data[:, z0:z1, y0:y1, x0:x1]
                )
            else:
                z0, y0, x0 = np.maximum(coords2.min(axis=0) - 1, 0)
                z1, y1, x1 = np.minimum(
                    coords2.max(axis=0) + 2, [z_max2, y_max2, x_max2]
                )
                mask_vol.data = np.ascontiguousarray(mask_vol.data[z0:z1, y0:y1, x0:x1])

            # The final bounding box is the base slice offset + the final crop offset
            mask_vol.roi_bbox = (
                min_z + z0,
                min_z + z1,
                min_y + y0,
                min_y + y1,
                min_x + x0,
                min_x + x1,
            )
        else:
            mask_vol.roi_bbox = (0, 0, 0, 0, 0, 0)

        # Sync metadata properties
        mask_vol.shape3d = base_vol.shape3d
        mask_vol.spacing = base_vol.spacing
        mask_vol.origin = base_vol.origin

    # ==========================================
    # PUBLIC ROI API
    # ==========================================

    def load_binary_mask(
        self,
        base_id,
        filepath,
        name=None,
        color=None,
        mode="Ignore BG (val)",
        target_val=0.0,
        preloaded_sitk=None,
    ):
        if color is None:
            color = [255, 50, 50]

        base_vol = self.controller.volumes[base_id]
        vs = self.controller.view_states[base_id]

        # [ASYNC_BOUNDARY]: Shield the viewer during C++ binarization and cropping
        with vs.loading_shield():
            # 1. Instantiate the raw ROI data
            mask_vol = VolumeData(
                filepath,
                is_roi=True,
                roi_mode=mode,
                roi_target_val=target_val,
                preloaded_sitk=preloaded_sitk,
            )

            # 2. Apply binarization rule BEFORE resampling to avoid interpolation artifacts
            self._apply_binarization_rule(mask_vol, mode, target_val)

            if mask_vol.data.size == 0:
                raise ValueError("Completely empty ROI.")

            # 3. SAFELY RESAMPLE AND AUTOCROP
            # This handles mismatched spacing, differing origins, and differing orientations,
            # and automatically calculates mask_vol.roi_bbox.
            self.process_binary_mask(base_vol, mask_vol)

            # Check if resampling pushed the ROI completely out of bounds
            if mask_vol.data.size == 0:
                raise ValueError("ROI is completely outside the base image FOV.")

        # 4. Register the Volume and State
        mask_id = str(self.controller.next_image_id)
        self.controller.next_image_id += 1
        self.controller.volumes[mask_id] = mask_vol

        if name is None:
            name = self._clean_roi_name(filepath)

        roi_state = ROIState(
            mask_id, name, color, source_mode=mode, source_val=target_val
        )
        vs.rois[mask_id] = roi_state
        vs.is_data_dirty = True

        return mask_id

    def parse_rtstruct(self, filepath):
        """
        Parses an RT-Struct DICOM file and returns a list of dictionaries
        containing information about the available ROIs.
        """
        try:
            import pydicom
        except ImportError:
            raise ImportError(
                "pydicom is required to read RT-Struct files. (pip install pydicom)"
            )

        try:
            ds = pydicom.dcmread(filepath, force=True)
        except Exception as e:
            raise ValueError(f"Could not read DICOM file: {e}")

        if getattr(ds, "Modality", None) != "RTSTRUCT":
            raise ValueError(
                f"File is not an RT-Struct (Modality: {getattr(ds, 'Modality', 'Unknown')})"
            )

        rois_info = []

        roi_names = {}
        seq_rois = getattr(ds, "StructureSetROISequence", None) or []
        for item in seq_rois:
            roi_num = getattr(item, "ROINumber", None)
            if roi_num is not None:
                try:
                    roi_names[int(roi_num)] = str(
                        getattr(item, "ROIName", f"ROI {roi_num}")
                    )
                except (ValueError, TypeError):
                    pass

        roi_colors = {}
        seq_contours = getattr(ds, "ROIContourSequence", None) or []
        for item in seq_contours:
            ref_num = getattr(item, "ReferencedROINumber", None)
            color_val = getattr(item, "ROIDisplayColor", None)
            if ref_num is not None and color_val is not None:
                try:
                    roi_colors[int(ref_num)] = [int(c) for c in color_val]
                except (ValueError, TypeError):
                    pass

        # Gather the final list
        for roi_num, name in roi_names.items():
            clean_name = str(name) if name else f"ROI {roi_num}"
            rois_info.append(
                {
                    "id": roi_num,
                    "name": clean_name,
                    "color": roi_colors.get(roi_num, [255, 0, 0]),
                }
            )

        return rois_info

    def load_rtstruct_roi(self, base_id, filepath, roi_info, ds=None):
        """Registers the RT-Struct ROI and maps its DICOM polygons to 2D slices."""
        vs = self.controller.view_states[base_id]
        base_vol = self.controller.volumes[base_id]

        if ds is None:
            try:
                import pydicom
            except ImportError:
                raise ImportError("pydicom is required to read RT-Struct files.")
            ds = pydicom.dcmread(filepath, force=True)

        try:
            from skimage.draw import polygon
        except ImportError:
            raise ImportError("scikit-image is required to rasterize RT-Structs.")

        target_roi_num = roi_info.get("id")

        # 1. Create a full-size blank mask
        mz, my, mx = base_vol.shape3d
        mask_data = np.zeros((mz, my, mx), dtype=np.uint8)

        seq_contours = getattr(ds, "ROIContourSequence", None) or []
        for roi_contour in seq_contours:
            if getattr(roi_contour, "ReferencedROINumber", -1) == target_roi_num:
                seq = getattr(roi_contour, "ContourSequence", None) or []
                for contour in seq:
                    if hasattr(contour, "ContourData"):
                        pts_flat = contour.ContourData
                        if len(pts_flat) % 3 != 0:
                            continue

                        mapped_pts = []
                        for i in range(0, len(pts_flat), 3):
                            pt_phys = [
                                float(pts_flat[i]),
                                float(pts_flat[i + 1]),
                                float(pts_flat[i + 2]),
                            ]
                            # Map directly to Base Image Voxel space
                            vox = base_vol.physic_coord_to_voxel_coord(
                                np.array(pt_phys)
                            )
                            mapped_pts.append(vox)

                        if not mapped_pts:
                            continue

                        mapped_pts = np.array(mapped_pts)

                        # Z is depth (axial slice index)
                        z_idx = int(round(np.mean(mapped_pts[:, 2])))

                        if 0 <= z_idx < mz:
                            # skimage.draw.polygon takes (r, c) which maps to (Y, X)
                            r = mapped_pts[:, 1]
                            c = mapped_pts[:, 0]
                            rr, cc = polygon(r, c, shape=(my, mx))

                            # XOR assignment handles internal holes natively!
                            mask_data[z_idx, rr, cc] ^= 1
                break

        if not np.any(mask_data):
            raise ValueError(
                "RT-Struct ROI did not map to any valid voxels on the base image."
            )

        # 2. Package as a VolumeData and crop it using the highly optimized pipeline!
        roi_id = str(self.controller.next_image_id)
        self.controller.next_image_id += 1

        mask_vol = VolumeData.__new__(VolumeData)
        mask_vol.path = filepath
        mask_vol.file_paths = [filepath]
        mask_vol.name = roi_info.get("name", "RT ROI")

        mask_img = sitk.GetImageFromArray(mask_data)
        mask_img.SetSpacing(base_vol.spacing.tolist())
        mask_img.SetOrigin(base_vol.origin.tolist())
        mask_img.SetDirection(base_vol.matrix.flatten().tolist())
        mask_vol.sitk_image = mask_img
        mask_vol.data = mask_data
        mask_vol.matrix_display_str = base_vol.matrix_display_str
        mask_vol.matrix_tooltip_str = base_vol.matrix_tooltip_str
        mask_vol.read_image_metadata()
        mask_vol.last_mtime = mask_vol._get_latest_mtime()
        mask_vol._last_check_time = 0
        mask_vol._is_outdated = False

        self.process_binary_mask(base_vol, mask_vol)
        self.controller.volumes[roi_id] = mask_vol

        roi_state = ROIState(
            roi_id,
            name=mask_vol.name,
            color=roi_info.get("color", [255, 0, 0]),
            source_mode="Ignore BG (val)",
            source_val=0.0,
            rtstruct_info=roi_info,
        )
        roi_state.is_contour = True

        vs.rois[roi_id] = roi_state
        vs.is_geometry_dirty = True
        vs.is_data_dirty = True

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

        # State-Only: Write the target center to the synced ViewStates.
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

        if getattr(roi_state, "rtstruct_info", None) is not None:
            if self.controller.gui:
                self.controller.gui.show_status_message(
                    "RT-Struct ROIs cannot be hot-reloaded.", color=[255, 100, 100]
                )
            return

        if self.controller.gui:
            self.controller.gui.show_status_message(
                f"Reloading: {roi_state.name} ...",
                color=self.controller.gui.ui_cfg["colors"]["working"],
            )

        vs = self.controller.view_states[base_id]
        with vs.loading_shield():
            mask_vol.reload()

            for ori in roi_state.polygons:
                roi_state.polygons[ori].clear()

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

    def update_roi_contours(self, viewer):
        """Extracts 2D marching squares for all contour ROIs on the current slice."""
        vs = viewer.view_state
        if not vs:
            return

        ori = viewer.orientation
        s_idx = viewer.slice_idx

        needs_update = False
        for roi_state in vs.rois.values():
            if roi_state.visible and roi_state.is_contour:
                if s_idx not in roi_state.polygons[ori]:
                    needs_update = True
                    break

        if not needs_update:
            return

        sw, sh = viewer.volume.get_physical_aspect_ratio(ori)
        base_z, base_y, base_x = viewer.volume.shape3d
        from vvv.maths.contours import extract_2d_contours_from_slice

        extracted_any = False
        for roi_id, roi_state in vs.rois.items():
            if not roi_state.visible or not roi_state.is_contour:
                continue

            if s_idx in roi_state.polygons[ori]:
                continue

            roi_vol = self.controller.volumes.get(roi_id)
            if not roi_vol or not hasattr(roi_vol, "roi_bbox"):
                roi_state.polygons[ori][s_idx] = []
                continue

            z0, z1, y0, y1, x0, x1 = roi_vol.roi_bbox
            if z0 == z1:
                roi_state.polygons[ori][s_idx] = []
                continue

            t_idx = min(vs.camera.time_idx, roi_vol.num_timepoints - 1)
            roi_slice = None
            offset_x, offset_y = 0, 0

            # Isolate the exact 2D slice for this orientation
            if ori == ViewMode.AXIAL:
                if z0 <= s_idx < z1:
                    if roi_vol.data.ndim == 4:
                        roi_slice = roi_vol.data[t_idx, s_idx - z0, :, :]
                    else:
                        roi_slice = roi_vol.data[s_idx - z0, :, :]
                    offset_x, offset_y = x0, y0
            elif ori == ViewMode.CORONAL:
                if y0 <= s_idx < y1:
                    if roi_vol.data.ndim == 4:
                        roi_slice = np.flipud(roi_vol.data[t_idx, :, s_idx - y0, :])
                    else:
                        roi_slice = np.flipud(roi_vol.data[:, s_idx - y0, :])
                    offset_x = x0
                    offset_y = base_z - z1
            elif ori == ViewMode.SAGITTAL:
                if x0 <= s_idx < x1:
                    if roi_vol.data.ndim == 4:
                        roi_slice = np.flipud(
                            np.fliplr(roi_vol.data[t_idx, :, :, s_idx - x0])
                        )
                    else:
                        roi_slice = np.flipud(np.fliplr(roi_vol.data[:, :, s_idx - x0]))
                    offset_x = base_y - y1
                    offset_y = base_z - z1

            if roi_slice is not None and roi_slice.size > 0:
                mask_2d = (roi_slice > 0).astype(np.uint8)
                polys = extract_2d_contours_from_slice(mask_2d, 0.5, sw, sh)

                # Shift the polygons to accurately overlay on the base image coordinates
                shifted_polys = []
                for poly in polys:
                    shifted_poly = []
                    for pt in poly:
                        shifted_poly.append(
                            [pt[0] + offset_x * sw, pt[1] + offset_y * sh]
                        )
                    shifted_polys.append(shifted_poly)
                roi_state.polygons[ori][s_idx] = shifted_polys
            else:
                roi_state.polygons[ori][s_idx] = []

            extracted_any = True

        if extracted_any:
            self.controller.ui_needs_refresh = True
