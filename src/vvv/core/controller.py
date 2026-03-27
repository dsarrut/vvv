import os
import json
import numpy as np
import SimpleITK as sitk
from vvv.utils import ViewMode
from vvv.core.roi_manager import ROIManager
from vvv.core.file_manager import FileManager
from vvv.core.sync_manager import SyncManager
from vvv.core.history_manager import HistoryManager
from vvv.core.settings_manager import SettingsManager


class Controller:
    """The central manager."""

    def __init__(self):
        self.gui = None
        self.volumes = {}
        self.view_states = {}
        self.viewers = {}
        self.file = FileManager(self)
        self.sync = SyncManager(self)
        self.roi = ROIManager(self)
        self.settings = SettingsManager()
        self.history = HistoryManager()

        self.use_history = True
        self.next_image_id = 0

    def get_next_image_id(self, current_id):
        if not self.view_states:
            return None
        keys = list(self.view_states.keys())
        if current_id not in keys:
            return keys[0]
        next_idx = (keys.index(current_id) + 1) % len(keys)
        return keys[next_idx]

    def link_all(self):
        if not self.view_states:
            return
        first_vs_id = next(iter(self.view_states))
        for vs in self.view_states.values():
            vs.sync_group = 1

        group_viewer_tags = [v.tag for v in self.viewers.values() if v.image_id]
        if group_viewer_tags:
            self.sync.propagate_ppm(group_viewer_tags)
            master_viewer = self.viewers[group_viewer_tags[0]]
            phys_center = master_viewer.get_center_physical_coord()
            if phys_center is not None:
                for tag in group_viewer_tags:
                    self.viewers[tag].center_on_physical_coord(phys_center)

        self.sync.propagate_sync(first_vs_id)
        if self.gui:
            self.gui.refresh_sync_ui()
            self.gui.refresh_image_list_ui()

    def unlink_all(self):
        for vs in self.view_states.values():
            vs.sync_group = 0
        if self.gui:
            self.gui.refresh_sync_ui()
            self.gui.refresh_image_list_ui()

    def default_viewers_orientation(self):
        n = len(self.view_states)
        if n == 1:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.SAGITTAL)
            self.viewers["V3"].set_orientation(ViewMode.CORONAL)
            self.viewers["V4"].set_orientation(ViewMode.AXIAL)
        elif n == 2:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.SAGITTAL)
            self.viewers["V3"].set_orientation(ViewMode.AXIAL)
            self.viewers["V4"].set_orientation(ViewMode.SAGITTAL)
        elif n == 3:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.AXIAL)
            self.viewers["V3"].set_orientation(ViewMode.AXIAL)
            self.viewers["V4"].set_orientation(ViewMode.SAGITTAL)
        elif n >= 4:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.AXIAL)
            self.viewers["V3"].set_orientation(ViewMode.AXIAL)
            self.viewers["V4"].set_orientation(ViewMode.AXIAL)

    def load_transform(self, vs_id, filepath):
        if vs_id not in self.view_states:
            return False

        vs = self.view_states[vs_id]
        vol = self.volumes[vs_id]
        new_transform = sitk.Euler3DTransform()

        try:
            # --- 1. Hand-parse simple text arrays (9 matrix numbers + optional 3 translation) ---
            if filepath.lower().endswith(".mat") or filepath.lower().endswith(".txt"):
                try:
                    arr = np.loadtxt(filepath).flatten()

                    if len(arr) >= 9:
                        # Extract the raw 3x3 matrix from the text file
                        R = np.array(arr[:9]).reshape(3, 3)

                        # THE FIX: Snap it back to perfect orthogonality using SVD!
                        # (This corrects any tiny rounding errors caused by saving to 6 decimal places)
                        U, _, Vt = np.linalg.svd(R)
                        R_ortho = U @ Vt

                        # Ensure it's a true rotation (determinant must be +1, not -1 reflection)
                        if np.linalg.det(R_ortho) < 0:
                            U[:, -1] *= -1
                            R_ortho = U @ Vt

                        rot_matrix = R_ortho.flatten().tolist()
                        trans_vec = (
                            arr[9:12].tolist() if len(arr) >= 12 else [0.0, 0.0, 0.0]
                        )

                        new_transform.SetMatrix(rot_matrix)
                        new_transform.SetTranslation(trans_vec)

                        new_transform.SetCenter(
                            self.get_volume_physical_center(vol).tolist()
                        )

                        vs.space.transform = new_transform
                        vs.space.transform_file = os.path.basename(filepath)
                        return True
                except Exception as e:
                    print(f"Failed to parse custom text matrix: {e}")
                    pass  # Fall through to standard Elastix/ITK parsers

            # --- 2. Try to parse as an Elastix Parameter File ---
            with open(filepath, "r") as f:
                content = f.read()

            if "TransformParameters" in content and "CenterOfRotationPoint" in content:
                import re

                params = (
                    re.search(r"\(TransformParameters(.*?)\)", content).group(1).split()
                )
                center = (
                    re.search(r"\(CenterOfRotationPoint(.*?)\)", content)
                    .group(1)
                    .split()
                )

                new_transform.SetRotation(
                    float(params[0]), float(params[1]), float(params[2])
                )
                new_transform.SetTranslation(
                    (float(params[3]), float(params[4]), float(params[5]))
                )
                new_transform.SetCenter(
                    (float(center[0]), float(center[1]), float(center[2]))
                )
            else:
                # --- 3. Fallback to standard ITK Transform Reader ---
                generic_transform = sitk.ReadTransform(filepath)
                if generic_transform.GetDimension() == 3:
                    new_transform.SetMatrix(generic_transform.GetMatrix())
                    new_transform.SetTranslation(generic_transform.GetTranslation())
                    if hasattr(generic_transform, "GetCenter"):
                        new_transform.SetCenter(generic_transform.GetCenter())

        except Exception as e:
            print(f"Error loading transform: {e}")
            return False

        # Failsafe: If Center of Rotation is exactly 0,0,0, fix it!
        if np.allclose(new_transform.GetCenter(), [0, 0, 0]):
            new_transform.SetCenter(self.get_volume_physical_center(vol).tolist())

        vs.space.transform = new_transform
        vs.space.transform_file = os.path.basename(filepath)
        return True

    def load_transform_OLD(self, vs_id, filepath):
        if vs_id not in self.view_states:
            return False

        vs = self.view_states[vs_id]
        vol = self.volumes[vs_id]
        new_transform = sitk.Euler3DTransform()

        try:
            # --- 1. Hand-parse simple text arrays (9 matrix numbers + optional 3 translation) ---
            if filepath.lower().endswith(".mat") or filepath.lower().endswith(".txt"):
                try:
                    # np.loadtxt ignores formatting and just grabs all the numbers in the file!
                    arr = np.loadtxt(filepath).flatten()

                    if len(arr) >= 9:
                        rot_matrix = arr[:9].tolist()
                        trans_vec = (
                            arr[9:12].tolist() if len(arr) >= 12 else [0.0, 0.0, 0.0]
                        )

                        new_transform.SetMatrix(rot_matrix)
                        new_transform.SetTranslation(trans_vec)

                        # Set CoR back to logical center if loading a raw matrix
                        new_transform.SetCenter(
                            self.get_volume_physical_center(vol).tolist()
                        )

                        vs.space.transform = new_transform
                        vs.space.transform_file = os.path.basename(filepath)
                        return True
                except Exception:
                    pass  # Fall through to standard Elastix/ITK parsers if np.loadtxt fails

            # --- 2. Try to parse as an Elastix Parameter File ---
            with open(filepath, "r") as f:
                content = f.read()

            if "TransformParameters" in content and "CenterOfRotationPoint" in content:
                import re

                params = (
                    re.search(r"\(TransformParameters(.*?)\)", content).group(1).split()
                )
                center = (
                    re.search(r"\(CenterOfRotationPoint(.*?)\)", content)
                    .group(1)
                    .split()
                )

                # Elastix Euler is [rx, ry, rz, tx, ty, tz] (angles in radians)
                new_transform.SetRotation(
                    float(params[0]), float(params[1]), float(params[2])
                )
                new_transform.SetTranslation(
                    (float(params[3]), float(params[4]), float(params[5]))
                )
                new_transform.SetCenter(
                    (float(center[0]), float(center[1]), float(center[2]))
                )
            else:
                # --- 3. Fallback to standard ITK Transform Reader ---
                generic_transform = sitk.ReadTransform(filepath)
                if generic_transform.GetDimension() == 3:
                    new_transform.SetMatrix(generic_transform.GetMatrix())
                    new_transform.SetTranslation(generic_transform.GetTranslation())
                    if hasattr(generic_transform, "GetCenter"):
                        new_transform.SetCenter(generic_transform.GetCenter())

        except Exception as e:
            print(f"Error loading transform: {e}")
            return False

        # Failsafe: If Center of Rotation is exactly 0,0,0, fix it!
        if np.allclose(new_transform.GetCenter(), [0, 0, 0]):
            new_transform.SetCenter(self.get_volume_physical_center(vol).tolist())

        vs.space.transform = new_transform
        vs.space.transform_file = os.path.basename(filepath)
        return True

    def save_transform(self, vs_id, filepath):
        vs = self.view_states.get(vs_id)
        if vs and vs.space.transform:
            try:
                # If the user specifically asks for a .mat or .txt file, write pure numbers
                if filepath.lower().endswith(".mat") or filepath.lower().endswith(
                    ".txt"
                ):
                    mat = vs.space.transform.GetMatrix()  # Tuple of 9
                    trans = vs.space.transform.GetTranslation()  # Tuple of 3

                    with open(filepath, "w") as f:
                        f.write(f"{mat[0]:.6f} {mat[1]:.6f} {mat[2]:.6f}\n")
                        f.write(f"{mat[3]:.6f} {mat[4]:.6f} {mat[5]:.6f}\n")
                        f.write(f"{mat[6]:.6f} {mat[7]:.6f} {mat[8]:.6f}\n")
                        f.write(f"{trans[0]:.6f} {trans[1]:.6f} {trans[2]:.6f}\n")
                else:
                    # Otherwise use standard SimpleITK .tfm format
                    sitk.WriteTransform(vs.space.transform, filepath)

                vs.space.transform_file = os.path.basename(filepath)
            except Exception as e:
                print(f"Failed to save transform: {e}")

    def load_transform_OLD(self, vs_id, filepath):
        if vs_id not in self.view_states:
            return False

        vs = self.view_states[vs_id]
        vol = self.volumes[vs_id]
        new_transform = sitk.Euler3DTransform()

        try:
            # 1. Try to parse as an Elastix Parameter File
            with open(filepath, "r") as f:
                content = f.read()

            if "TransformParameters" in content and "CenterOfRotationPoint" in content:
                import re

                params = (
                    re.search(r"\(TransformParameters(.*?)\)", content).group(1).split()
                )
                center = (
                    re.search(r"\(CenterOfRotationPoint(.*?)\)", content)
                    .group(1)
                    .split()
                )

                # Elastix Euler is [rx, ry, rz, tx, ty, tz] (angles in radians)
                new_transform.SetRotation(
                    float(params[0]), float(params[1]), float(params[2])
                )
                new_transform.SetTranslation(
                    (float(params[3]), float(params[4]), float(params[5]))
                )
                new_transform.SetCenter(
                    (float(center[0]), float(center[1]), float(center[2]))
                )
            else:
                # 2. Fallback to standard ITK Transform Reader
                generic_transform = sitk.ReadTransform(filepath)
                # Force it into an Euler3DTransform so our GUI sliders can interact with it
                if generic_transform.GetDimension() == 3:
                    new_transform.SetMatrix(generic_transform.GetMatrix())
                    new_transform.SetTranslation(generic_transform.GetTranslation())
                    if hasattr(generic_transform, "GetCenter"):
                        new_transform.SetCenter(generic_transform.GetCenter())

        except Exception as e:
            print(f"Error loading transform: {e}")
            return False

        # 3. Failsafe: If Center of Rotation is exactly 0,0,0, fix it!
        if np.allclose(new_transform.GetCenter(), [0, 0, 0]):
            new_transform.SetCenter(vs.space.cor.tolist())

        vs.space.transform = new_transform
        vs.space.transform_file = os.path.basename(filepath)
        return True

    def save_transform_OLD(self, vs_id, filepath):
        vs = self.view_states.get(vs_id)
        if vs and vs.space.transform:
            sitk.WriteTransform(vs.space.transform, filepath)
            vs.space.transform_file = os.path.basename(filepath)

    def add_recent_file(self, path):
        """Adds a path to the recent files list in settings and caps it at 10."""
        if "behavior" not in self.settings.data:
            self.settings.data["behavior"] = {}

        recent = self.settings.data["behavior"].get("recent_files", [])

        # Convert list (DICOM series) to JSON string to make it hashable and storable
        path_str = json.dumps(path) if isinstance(path, list) else path

        if path_str in recent:
            recent.remove(path_str)
        recent.insert(0, path_str)

        # Cap at 10
        self.settings.data["behavior"]["recent_files"] = recent[:10]

    def get_volume_physical_center(self, vol):
        """Calculates the exact physical center of an image volume for the CoR."""
        cx = (vol.shape3d[2] - 1) / 2.0
        cy = (vol.shape3d[1] - 1) / 2.0
        cz = (vol.shape3d[0] - 1) / 2.0
        return vol.voxel_coord_to_physic_coord(np.array([cx, cy, cz]))

    def save_image(self, vs_id, filepath):
        """Exports the active volume to disk as a NIfTI, MHD, etc."""
        if vs_id not in self.volumes:
            return
        import SimpleITK as sitk

        vol = self.volumes[vs_id]
        sitk.WriteImage(vol.sitk_image, filepath)

    def get_pixel_values_at_phys(self, vs_id, phys_coord, time_idx):
        """
        Calculates the Base value, Fused Target value, and intersecting ROIs.
        Uses pure Physical World Coordinates to map backwards through any active transforms,
        guaranteeing perfect accuracy even when the visual buffer is heavily resampled.
        """
        vs = self.view_states.get(vs_id)
        if not vs:
            return None

        vol = self.volumes[vs_id]

        # 1. Base Image Value (World -> Original Voxel Array)
        base_val = None
        # is_buffered=False forces it to ignore the resampled UI bounding box and use the raw array!
        base_vox = vs.space.world_to_display(phys_coord, is_buffered=False)
        ix, iy, iz = [int(np.floor(c + 0.5)) for c in base_vox[:3]]

        mz, my, mx = vol.shape3d
        if 0 <= ix < mx and 0 <= iy < my and 0 <= iz < mz:
            t = min(time_idx, vol.num_timepoints - 1) if vol.num_timepoints > 1 else 0
            base_val = (
                vol.data[t, iz, iy, ix]
                if vol.num_timepoints > 1
                else vol.data[iz, iy, ix]
            )

        # 2. Fused Target Overlay Value
        overlay_val = None
        if vs.display.overlay_id and vs.display.overlay_id in self.volumes:
            ov_vol = self.volumes[vs.display.overlay_id]
            ov_vs = self.view_states[vs.display.overlay_id]

            # Use the overlay's own spatial engine to map the world point into its original array
            ov_vox = ov_vs.space.world_to_display(phys_coord, is_buffered=False)
            ox, oy, oz = [int(np.floor(c + 0.5)) for c in ov_vox[:3]]
            omz, omy, omx = ov_vol.shape3d

            if 0 <= ox < omx and 0 <= oy < omy and 0 <= oz < omz:
                ot = min(time_idx, ov_vol.num_timepoints - 1)
                overlay_val = (
                    ov_vol.data[ot, oz, oy, ox]
                    if ov_vol.num_timepoints > 1
                    else ov_vol.data[oz, oy, ox]
                )

        # 3. Intersecting ROIs (ROIs share the Base Image's spatial grid)
        roi_names = []
        for r_id, r_state in vs.rois.items():
            r_vol = self.volumes.get(r_id)
            if r_vol:
                rmz, rmy, rmx = r_vol.shape3d
                if 0 <= ix < rmx and 0 <= iy < rmy and 0 <= iz < rmz:
                    rt = min(time_idx, r_vol.num_timepoints - 1)
                    r_val = (
                        r_vol.data[rt, iz, iy, ix]
                        if r_vol.num_timepoints > 1
                        else r_vol.data[iz, iy, ix]
                    )
                    if r_val > 0:
                        roi_names.append(r_state.name)

        return {"base_val": base_val, "overlay_val": overlay_val, "rois": roi_names}

    def get_pixel_values_at_voxel_OLD(self, vs_id, voxel_coord):
        """
        Calculates the Base value, Fused Target value, and intersecting ROIs for a specific voxel.
        Centralizes the math for both the floating mouse tracker and the sidebar crosshair!
        """
        vs = self.view_states.get(vs_id)
        if not vs:
            return None

        vol = self.volumes[vs_id]

        # 1. Extract and clamp integer base coordinates
        ix, iy, iz = [
            int(np.clip(np.floor(c + 0.5), 0, limit - 1))
            for c, limit in zip(
                voxel_coord[:3], [vol.shape3d[2], vol.shape3d[1], vol.shape3d[0]]
            )
        ]

        t_idx = int(voxel_coord[3]) if len(voxel_coord) > 3 else vs.camera.time_idx

        # 2. Base Image Value
        base_val = None
        mz, my, mx = vol.shape3d
        if 0 <= ix < mx and 0 <= iy < my and 0 <= iz < mz:
            t = min(t_idx, vol.num_timepoints - 1) if vol.num_timepoints > 1 else 0

            # Read from the display buffer if active
            display_data = getattr(vs, "base_display_data", None)
            if display_data is not None:
                base_val = (
                    display_data[t, iz, iy, ix]
                    if vol.num_timepoints > 1
                    else display_data[iz, iy, ix]
                )
            else:
                base_val = (
                    vol.data[t, iz, iy, ix]
                    if vol.num_timepoints > 1
                    else vol.data[iz, iy, ix]
                )

        if base_val is None:
            return None  # Mouse is completely outside the image bounds

        # 3. Fused Target Overlay Value (Calculated via physical coordinate mapping)
        overlay_val = None
        if vs.display.overlay_id and vs.display.overlay_id in self.volumes:
            ov_vol = self.volumes[vs.display.overlay_id]
            ov_vs = self.view_states[vs.display.overlay_id]

            is_buf = vs.base_display_data is not None
            world_phys = vs.space.display_to_world(
                np.array([ix, iy, iz]), is_buffered=is_buf
            )

            is_ov_buf = ov_vs.base_display_data is not None
            ov_vox = ov_vs.space.world_to_display(world_phys, is_buffered=is_ov_buf)

            ox, oy, oz = (
                int(np.floor(ov_vox[0] + 0.5)),
                int(np.floor(ov_vox[1] + 0.5)),
                int(np.floor(ov_vox[2] + 0.5)),
            )
            omz, omy, omx = ov_vol.shape3d

            if 0 <= ox < omx and 0 <= oy < omy and 0 <= oz < omz:
                ot = min(t_idx, ov_vol.num_timepoints - 1)
                overlay_val = (
                    ov_vol.data[ot, oz, oy, ox]
                    if ov_vol.num_timepoints > 1
                    else ov_vol.data[oz, oy, ox]
                )

        # 4. Intersecting ROIs (No visibility check! We want to see hidden ROIs)
        roi_names = []
        for r_id, r_state in vs.rois.items():
            r_vol = self.volumes.get(r_id)
            if r_vol:
                if hasattr(r_vol, "roi_bbox"):
                    rz0, rz1, ry0, ry1, rx0, rx1 = r_vol.roi_bbox
                    if rx0 <= ix < rx1 and ry0 <= iy < ry1 and rz0 <= iz < rz1:
                        rrx, rry, rrz = ix - rx0, iy - ry0, iz - rz0
                        rt = min(t_idx, r_vol.num_timepoints - 1)
                        r_val = (
                            r_vol.data[rt, rrz, rry, rrx]
                            if r_vol.num_timepoints > 1
                            else r_vol.data[rrz, rry, rrx]
                        )
                        if r_val > 0:
                            roi_names.append(r_state.name)
                else:
                    rmz, rmy, rmx = r_vol.shape3d
                    if 0 <= ix < rmx and 0 <= iy < rmy and 0 <= iz < rmz:
                        rt = min(t_idx, r_vol.num_timepoints - 1)
                        r_val = (
                            r_vol.data[rt, iz, iy, ix]
                            if r_vol.num_timepoints > 1
                            else r_vol.data[iz, iy, ix]
                        )
                        if r_val > 0:
                            roi_names.append(r_state.name)

        return {"base_val": base_val, "overlay_val": overlay_val, "rois": roi_names}

    def update_all_viewers_of_image(self, vs_id):
        # 1. Flag the data as dirty so tick() handles the heavy blending
        vs = self.view_states.get(vs_id)
        if vs:
            vs.is_data_dirty = True

        # 2. Flag the geometry as dirty so tick() handles the crosshair drawing
        for viewer in self.viewers.values():
            if viewer.image_id == vs_id:
                viewer.is_geometry_dirty = True

    def update_setting(self, keys, value):
        if not keys or keys[-1] is None:
            return

        d = self.settings.data
        for key in keys[:-1]:
            d = d[key]

        if keys[0] == "colors" and isinstance(value, (list, tuple)):
            if any(isinstance(x, float) for x in value):
                value = [int(x * 255) for x in value]
            else:
                value = [int(x) for x in value]

        d[keys[-1]] = value

        # ONLY SET FLAGS!
        for vs in self.view_states.values():
            vs.is_data_dirty = True
        for viewer in self.viewers.values():
            viewer.is_geometry_dirty = True

    def update_transform_manual(self, vs_id, tx, ty, tz, rx_deg, ry_deg, rz_deg):
        vs = self.view_states.get(vs_id)
        if not vs:
            return
        import math

        vs.space.set_manual_transform(
            tx, ty, tz, math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
        )

    def reset_settings(self):
        self.settings.reset()
        # ONLY SET FLAGS!
        for vs in self.view_states.values():
            vs.is_data_dirty = True
        for viewer in self.viewers.values():
            viewer.is_geometry_dirty = True

    def reset_image_view(self, vs_id, hard=False):
        """Resets the view and re-applies the boot-up synchronization logic."""
        if vs_id not in self.view_states:
            return

        vs = self.view_states[vs_id]

        if hard:
            vs.hard_reset()
        else:
            vs.reset_view()

        # Re-apply unifying math so it looks exactly like the initial load!
        same_viewers = [v.tag for v in self.viewers.values() if v.image_id == vs_id]
        if same_viewers:
            self.sync.propagate_ppm(same_viewers)

        # Force all linked viewers to perfectly re-center
        for tag in same_viewers:
            viewer = self.viewers[tag]
            if hasattr(viewer, "needs_recenter"):
                viewer.needs_recenter = True
            viewer.is_geometry_dirty = True

        if self.gui:
            self.gui.update_sidebar_info(self.gui.context_viewer)

    def reload_settings(self):
        self.settings.reset()
        self.settings.load()
        # ONLY SET FLAGS!
        for vs in self.view_states.values():
            vs.is_data_dirty = True
        for viewer in self.viewers.values():
            viewer.is_geometry_dirty = True

    def reload_image(self, vs_id):
        if vs_id in self.view_states:
            vs = self.view_states[vs_id]
            vol = vs.volume
            was_reset = vol.reload()

            if was_reset:
                for viewer in self.viewers.values():
                    if viewer.image_id == vs_id:
                        viewer.set_image(vs_id)
            else:
                ix, iy, iz = [
                    int(np.clip(np.floor(c + 0.5), 0, limit - 1))
                    for c, limit in zip(
                        vs.camera.crosshair_voxel[:3],
                        [vol.shape3d[2], vol.shape3d[1], vol.shape3d[0]],
                    )
                ]

                if vol.num_timepoints > 1:
                    vs.crosshair_value = vol.data[vs.camera.time_idx, iz, iy, ix]
                else:
                    vs.crosshair_value = vol.data[iz, iy, ix]

                vs.histogram_is_dirty = True
                vs.is_data_dirty = True
                self.update_all_viewers_of_image(vs_id)

            for other_id, other_vs in self.view_states.items():
                if other_vs.display.overlay_id == vs_id:
                    other_vs.set_overlay(vs_id, vol)
                    self.update_all_viewers_of_image(other_id)

            if self.gui.context_viewer and self.gui.context_viewer.image_id == vs_id:
                self.gui.update_sidebar_info(self.gui.context_viewer)
                self.gui.update_sidebar_crosshair(self.gui.context_viewer)

            if self.gui:
                self.gui.show_status_message(f"Reloaded: {vol.name}")
                self.gui.refresh_image_list_ui()
                self.gui.refresh_rois_ui()

    def save_settings(self):
        return self.settings.save()

    def tick(self):
        for viewer in self.viewers.values():
            did_update = viewer.tick()
            if did_update and self.gui and viewer == self.gui.context_viewer:
                self.gui.update_sidebar_crosshair(viewer)

        for vs in self.view_states.values():
            vs.is_data_dirty = False

        # Check if files changed on disk, update UI if needed
        outdated_changed = False
        for vol in self.volumes.values():
            if hasattr(vol, "is_outdated"):
                was_outdated = vol._is_outdated
                is_out = vol.is_outdated()
                if is_out != was_outdated:
                    outdated_changed = True

        if outdated_changed and self.gui:
            self.gui.refresh_image_list_ui()
            self.gui.refresh_rois_ui()
