import os
import json
import numpy as np
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

        self.ui_needs_refresh = False

    def get_next_image_id(self, current_id):
        if not self.view_states:
            return None
        keys = list(self.view_states.keys())
        if current_id not in keys:
            return keys[0]
        next_idx = (keys.index(current_id) + 1) % len(keys)
        return keys[next_idx]

    def link_all(self):
        self.sync.link_all()

    def unlink_all(self):
        self.sync.unlink_all()

    def link_all_wl(self):
        self.sync.link_all_wl()

    def unlink_all_wl(self):
        self.sync.unlink_all_wl()

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
        fallback_center = self.get_volume_physical_center(vol).tolist()

        try:
            from vvv.math.transform_io import TransformIO

            new_transform = TransformIO.read_transform(filepath, fallback_center)

            vs.space.transform = new_transform
            vs.space.transform_file = os.path.basename(filepath)
            return True
        except Exception as e:
            print(f"Error loading transform: {e}")
            return False

    def save_transform(self, vs_id, filepath):
        vs = self.view_states.get(vs_id)
        if vs and vs.space.transform:
            try:
                from vvv.math.transform_io import TransformIO

                TransformIO.write_transform(vs.space.transform, filepath)
                vs.space.transform_file = os.path.basename(filepath)
            except Exception as e:
                print(f"Failed to save transform: {e}")

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
                if hasattr(r_vol, "roi_bbox"):
                    # The array is cropped! We must subtract the bounding box offsets
                    z0, z1, y0, y1, x0, x1 = r_vol.roi_bbox
                    if x0 <= ix < x1 and y0 <= iy < y1 and z0 <= iz < z1:
                        rt = min(time_idx, r_vol.num_timepoints - 1)
                        r_val = (
                            r_vol.data[rt, iz - z0, iy - y0, ix - x0]
                            if r_vol.num_timepoints > 1
                            else r_vol.data[iz - z0, iy - y0, ix - x0]
                        )
                        if r_val > 0:
                            roi_names.append(r_state.name)
                else:
                    # Fallback for uncropped arrays
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

    def set_sync_group(self, vs_id, group_id):
        """
        Programmatically sets the spatial sync group for an image and propagates
        the geometry from an existing group master to it.
        """
        vs = self.view_states.get(vs_id)
        if not vs:
            return

        vs.sync_group = group_id

        # Find the "Source of Truth" for this new group
        master_vs_id = None
        for other_id, other_vs in self.view_states.items():
            if other_id != vs_id and other_vs.sync_group == group_id:
                master_vs_id = other_id
                break

        # Find all viewers currently displaying any image in this group
        group_viewer_tags = [
            v.tag
            for v in self.viewers.values()
            if v.view_state and v.view_state.sync_group == group_id
        ]

        if not group_viewer_tags:
            return

        self.sync.propagate_ppm(group_viewer_tags)

        # Snap the newly synced viewers to the master's physical center
        if master_vs_id:
            master_viewer = next(
                (v for v in self.viewers.values() if v.image_id == master_vs_id),
                None,
            )
            if master_viewer:
                phys_center = master_viewer.get_center_physical_coord()
                if phys_center is not None:
                    for tag in group_viewer_tags:
                        self.viewers[tag].center_on_physical_coord(phys_center)
            self.sync.propagate_sync(master_vs_id)

        self.update_all_viewers_of_image(vs_id)
        self.ui_needs_refresh = True

    def update_all_viewers_of_image(self, vs_id, data_dirty=True):
        # 1. Flag the data as dirty so tick() handles the heavy blending
        if data_dirty:
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

            self.ui_needs_refresh = True

    def save_settings(self):
        return self.settings.save()

    def tick(self):
        for viewer in self.viewers.values():
            did_update = viewer.tick()
            if did_update and self.gui and viewer == self.gui.context_viewer:
                self.gui.update_sidebar_crosshair(viewer)

        # --- THE BRIDGE ---
        for vs_id, vs in self.view_states.items():
            # If the properties flipped the geometry flag, broadcast it!
            if getattr(vs, "is_geometry_dirty", False):
                for viewer in self.viewers.values():
                    if viewer.image_id == vs_id:
                        viewer.is_geometry_dirty = True

            vs.is_data_dirty = False
            vs.is_geometry_dirty = False

        # Check if files changed on disk, update UI if needed
        outdated_changed = False
        for vol in self.volumes.values():
            if hasattr(vol, "is_outdated"):
                was_outdated = vol._is_outdated
                is_out = vol.is_outdated()
                if is_out != was_outdated:
                    outdated_changed = True

        if outdated_changed:
            self.ui_needs_refresh = True
