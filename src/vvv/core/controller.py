import os
import json
import threading
import numpy as np
import concurrent.futures
from typing import Any
from vvv.utils import ViewMode
from vvv.maths.image import VolumeData
from vvv.core.roi_manager import ROIManager
from vvv.core.file_manager import FileManager
from vvv.core.sync_manager import SyncManager
from vvv.core.contour_manager import ContourManager
from vvv.core.history_manager import HistoryManager
from vvv.core.settings_manager import SettingsManager
from vvv.core.extraction_manager import ExtractionManager
from vvv.core.profile_manager import ProfileManager


class Controller:
    """
    The Central Manager and State-Only Bridge for VVV.

    ARCHITECTURE MANDATES (State-Only / Reactive):
    1. THE CONTROLLER AS A BRIDGE: This class is a "dumb" coordinator. It must NOT
       micromanage Viewers or the GUI. Its primary job is to sync data flags between
       the central 'ViewState' (Data) and the 'SliceViewer' (View).

    2. TICK LOOP PRIORITY: Inside the tick() loop, the Viewers (View) must always
       execute BEFORE the Bridge (Sync). The Bridge must broadcast 'is_geometry_dirty'
       and 'is_data_dirty' to all relevant Viewers BEFORE resetting the source flags.

    3. NO IMPERATIVE UI CALLS: Never call 'gui.refresh_rois_ui()' or 'dpg.set_value()'
       from this class or any of its Managers (FileManager, SyncManager, etc.).
       Instead, set 'self.ui_needs_refresh = True' and let the MainGUI handle it
       reactively in the next frame.

    4. THREAD SAFETY: Background threads (threading.Thread) must NEVER call UI functions.
       To report a status update from a thread, set 'self.status_message = "..."'
       and 'self.ui_needs_refresh = True'.

    5. GEOMETRY UPDATES: To force a viewer re-center, DO NOT set 'viewer.needs_recenter'.
       Instead, set 'vs.camera.target_center = world_pos'. The Viewers watch this
       central data and re-calibrate themselves autonomously.
    """

    def __init__(self):
        self.gui: Any = None
        self.volumes = {}
        self.view_states = {}
        self.viewers = {}

        self.layout: dict[str, str | None] = {"V1": None, "V2": None, "V3": None, "V4": None}

        self.file = FileManager(self)
        self.sync = SyncManager(self)
        self.roi = ROIManager(self)
        self.contours = ContourManager(self)
        self.settings = SettingsManager()
        self.history = HistoryManager()
        self.extraction = ExtractionManager(self)
        self.profiles = ProfileManager(self)

        self.use_history = True
        self.next_image_id = 0

        self.ui_needs_refresh = False
        self.ui_needs_layout_rebuild = False
        self.debug_mode = False
        self.status_message: str | None = None

    def get_next_image_id(self, current_id):
        if not self.view_states:
            return None
        keys = list(self.view_states.keys())
        if current_id not in keys:
            return keys[0]
        next_idx = (keys.index(current_id) + 1) % len(keys)
        return keys[next_idx]

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

    def load_volumes_parallel(self, file_paths):
        """
        [ASYNC_BOUNDARY]: Uses a ThreadPoolExecutor.
        Multiple background threads are hitting the disk and SimpleITK simultaneously.

        Loads multiple VolumeData objects simultaneously using a thread pool.
        Returns a dictionary mapping the original file path to the loaded VolumeData object.
        """
        loaded_volumes = {}

        # Determine optimal thread count (default is usually fine, but you can cap it to prevent I/O choking)
        max_workers = min(len(file_paths), 8)

        # Spin up the thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all paths to the executor simultaneously
            future_to_path = {
                executor.submit(VolumeData, path): path for path in file_paths
            }

            # Collect them as soon as they individually finish
            for future in concurrent.futures.as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    vol = future.result()
                    loaded_volumes[path] = vol
                    # If you have a logger, this is a great place to log: f"Successfully loaded {vol.name}"
                except Exception as exc:
                    print(f"CRITICAL: Failed to load {path}. Error: {exc}")

        return loaded_volumes

    def load_transform(self, vs_id, filepath):
        if vs_id not in self.view_states:
            return False

        vs = self.view_states[vs_id]
        vol = self.volumes[vs_id]
        fallback_center = self.get_volume_physical_center(vol).tolist()

        try:
            from vvv.maths.transform_io import TransformIO

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
                from vvv.maths.transform_io import TransformIO

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

        # Cap at 20
        self.settings.data["behavior"]["recent_files"] = recent[:20]

    def get_volume_physical_center(self, vol):
        """Calculates the exact physical center of an image volume for the CoR."""
        cx = (vol.shape3d[2] - 1) / 2.0
        cy = (vol.shape3d[1] - 1) / 2.0
        cz = (vol.shape3d[0] - 1) / 2.0
        return vol.voxel_coord_to_physic_coord(np.array([cx, cy, cz]))

    def get_image_display_name(self, vs_id):
        """Returns a formatted display name (e.g., '(1) name.mhd') and an is_outdated boolean."""
        try:
            idx = list(self.view_states.keys()).index(vs_id) + 1
        except ValueError:
            idx = "?"

        vol = self.volumes.get(vs_id)
        if not vol:
            return f"({idx}) Unknown", False

        is_outdated = getattr(vol, "_is_outdated", False)
        base_name = f"({idx}) {vol.name}"
        name_str = f"{base_name} *" if is_outdated else base_name
        return name_str, is_outdated

    def save_image(self, vs_id, filepath):
        """Exports the active volume to disk as a NIfTI, MHD, etc."""
        if vs_id not in self.volumes:  # Guard against invalid vs_id
            print(f"Error: Volume {vs_id} not found for saving.")
            return
        import SimpleITK as sitk

        vol = self.volumes[vs_id]
        if vol.data is None:  # Guard against tombstoned or unloaded data
            print(f"Error: Volume {vs_id} has no data loaded.")
            return
        sitk.WriteImage(vol.sitk_image, filepath)

        # Update internal state so the UI reflects the new filename and path
        vol.path = filepath
        vol.file_paths = [filepath]
        vol.name = os.path.basename(filepath)
        vol.last_mtime = vol._get_latest_mtime()
        vol._is_outdated = False

    def _get_voxel_value(self, vol, vs, phys_coord, time_idx):
        """Map a physical world coordinate to a voxel value in vol's native array."""
        vox = vs.world_to_display(phys_coord, is_buffered=False)
        ix, iy, iz = (int(np.floor(c + 0.5)) for c in vox[:3])
        mz, my, mx = vol.shape3d
        if not (0 <= ix < mx and 0 <= iy < my and 0 <= iz < mz):
            return None, ix, iy, iz
        if getattr(vol, "is_dvf", False):
            return vol.data[:, iz, iy, ix], ix, iy, iz
        t = min(time_idx, vol.num_timepoints - 1)
        val = vol.data[t, iz, iy, ix] if vol.num_timepoints > 1 else vol.data[iz, iy, ix]
        return val, ix, iy, iz

    def get_pixel_values_at_phys(self, vs_id, phys_coord, time_idx):
        """
        Calculates the Base value, Fused Target value, and intersecting ROIs.
        Uses pure Physical World Coordinates to map backwards through any active transforms,
        guaranteeing perfect accuracy even when the visual buffer is heavily resampled.
        """
        vs = self.view_states.get(vs_id)
        if (
            not vs
            or phys_coord is None
            or np.isscalar(phys_coord)
            or len(phys_coord) < 3
        ):
            return None

        vol = self.volumes[vs_id]

        try:
            # 1. Base Image Value (World -> Original Voxel Array)
            # is_buffered=False forces it to ignore the resampled UI bounding box and use the raw array.
            base_val, ix, iy, iz = self._get_voxel_value(vol, vs, phys_coord, time_idx)

            # 2. Fused Target Overlay Value
            overlay_val = None
            if vs.display.overlay_id and vs.display.overlay_id in self.volumes:
                ov_vol = self.volumes[vs.display.overlay_id]
                ov_vs = self.view_states[vs.display.overlay_id]
                overlay_val, _, _, _ = self._get_voxel_value(ov_vol, ov_vs, phys_coord, time_idx)

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
        except Exception:
            return None

    def set_sync_group(self, vs_id, group_id):
        """
        Programmatically sets the spatial sync group for an image and propagates
        the geometry from an existing group master to it.
        """
        vs = self.view_states.get(vs_id)
        if not vs:
            return

        if vs.sync_group == group_id:
            return

        vs.sync_group = group_id

        if group_id == 0:
            self.update_all_viewers_of_image(vs_id)
            self.ui_needs_refresh = True
            return

        # Find the "Source of Truth" for this new group
        master_vs_id = None
        active_viewer = self.gui.context_viewer if self.gui else None
        
        # If the active viewer is in the same sync group, use it as master
        if active_viewer and active_viewer.image_id in self.view_states:
            active_vs = self.view_states[active_viewer.image_id]
            if active_vs.sync_group == group_id:
                master_vs_id = active_viewer.image_id

        if not master_vs_id:
            for other_id, other_vs in list(self.view_states.items()):
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

        # Snap the newly synced viewers to the master's physical center
        if master_vs_id:
            master_viewer = next(
                (v for v in self.viewers.values() if v.image_id == master_vs_id),
                None,
            )
            if master_viewer:
                self.sync.propagate_camera(master_viewer)
            self.sync.propagate_sync(master_vs_id)

        self.update_all_viewers_of_image(vs_id)
        self.ui_needs_refresh = True

    def update_all_viewers_of_image(self, vs_id, data_dirty=True):
        if vs_id in self.view_states and data_dirty:
            self.view_states[vs_id].is_data_dirty = True
            # GUARDRAIL 3: Push the data flag to viewers to prevent them
            # from rendering tombstoned C++ memory during the 1-frame Bridge gap.
            self._flag_viewers_for_image(vs_id, data_dirty=True)
        else:
            self._flag_viewers_for_image(vs_id, geometry_dirty=True)

    def _flag_viewers_for_image(self, vs_id, data_dirty=False, geometry_dirty=False):
        """Set dirty flags on all viewers that display vs_id as base image or overlay."""
        for v in self.viewers.values():
            if v.image_id == vs_id or (v.view_state and v.view_state.display.overlay_id == vs_id):
                if data_dirty:
                    v.is_viewer_data_dirty = True
                if geometry_dirty:
                    v.is_geometry_dirty = True

    def _flag_all_viewers_dirty(self):
        """Helper to reactively refresh all viewers when global settings change."""
        for viewer in self.viewers.values():
            if viewer.view_state:
                viewer.view_state.is_data_dirty = True
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

        if keys[0] == "layout":
            self.ui_needs_layout_rebuild = True

        self.ui_needs_refresh = True
        self._flag_all_viewers_dirty()

    def update_transform_manual(self, vs_id, tx, ty, tz, rx_deg, ry_deg, rz_deg):
        vs = self.view_states.get(vs_id)
        if not vs:
            return
        import math

        vs.space.set_manual_transform(
            tx, ty, tz, math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
        )
        vs._active_resample_job = 0  # mark any in-flight resample as inproductive

    def resample_image(self, image_id):
        """Spawn a background thread that resamples image_id and all dependent overlays.

        Each call gets a unique job ID.  If the transform changes mid-resample
        (update_transform_manual sets _active_resample_job = 0), the thread detects
        it is inproductive at the end and discards the result without touching viewers.
        """
        vs = self.view_states.get(image_id)
        if not vs:
            return

        vs._resample_job_counter += 1
        my_job_id = vs._resample_job_counter
        vs._active_resample_job = my_job_id
        self.ui_needs_refresh = True  # update UI debug indicator immediately

        def _do():
            vs = self.view_states.get(image_id)
            if not vs:
                return

            vs.reset_preview_rotation()
            vs.update_base_display_data()

            # --- Early exit: check before touching any overlay data ---
            # If the transform changed during base resampling, overlay_data was never
            # modified so the old (pre-resample) overlay is still valid — no ghost.
            if vs._active_resample_job != my_job_id:
                self._discard_resample(my_job_id)
                return

            if vs.display.overlay_id:
                vs.update_overlay_display_data(self)

            for other_vs in self.view_states.values():
                if other_vs.display.overlay_id == image_id:
                    other_vs.update_overlay_display_data(self)

            # --- Late exit: check after overlay resampling ---
            # If the transform changed during overlay resampling, the overlays now hold
            # wrong-transform data (late-tombstone kept old valid during Execute, but
            # assigned new wrong result afterwards). Clear them so viewers show "no
            # overlay" briefly rather than a ghost at the wrong rotation angle.
            if vs._active_resample_job != my_job_id:
                self._clear_overlay_data(image_id)
                self._discard_resample(my_job_id)
                return

            # Sync crosshair AFTER all overlay resampling (avoids tombstone flash).
            if vs.base_display_data is not None and vs.camera.crosshair_phys_coord is not None:
                vs.update_crosshair_from_phys(vs.camera.crosshair_phys_coord)

            vs._active_resample_job = 0
            vs.needs_resample = False
            self.update_all_viewers_of_image(image_id)
            self.status_message = "Resampling complete"
            self.ui_needs_refresh = True

        threading.Thread(target=_do, daemon=True).start()

    def _discard_resample(self, job_id):
        self.status_message = f"Resample #{job_id} discarded (transform changed)"
        self.ui_needs_refresh = True

    def _clear_overlay_data(self, image_id):
        """Clear overlay data that was written with a wrong transform during a discarded resample.

        Called when a resample is discarded AFTER overlay resampling has already run.
        Sets overlay_data to None so viewers show no overlay rather than a ghost at
        the wrong rotation. The next valid resample will restore correct overlay data.
        """
        vs = self.view_states.get(image_id)
        if vs and vs.display.overlay_id:
            vs.display.overlay_data = None
            vs.display._sitk_overlay_cache = None
        for other_vs in self.view_states.values():
            if other_vs.display.overlay_id == image_id:
                other_vs.display.overlay_data = None
                other_vs.display._sitk_overlay_cache = None

    def bake_transform_to_volume(self, vs_id):
        """Permanently apply the registration transform by resampling the volume in-place.

        Runs in a background thread.  Uses the same tombstone pattern as reload_image
        to safely sever old C++ memory before swapping in the new resampled data.
        After baking, the transform is reset to identity and the image is indistinguishable
        from one loaded without any transform.
        """
        import SimpleITK as sitk

        vs = self.view_states.get(vs_id)
        vol = self.volumes.get(vs_id)
        if not vs or not vol or not vs.space.transform or not vs.space.is_active:
            return

        anchor_world = (
            vs.camera.crosshair_phys_coord.copy()
            if vs.camera.crosshair_phys_coord is not None
            else None
        )

        def _do_bake():
            with vs.loading_shield():
                try:
                    # Build reference grid (same size/spacing/origin/direction as original)
                    ref = sitk.Image(
                        int(vol.shape3d[2]), int(vol.shape3d[1]), int(vol.shape3d[0]),
                        sitk.sitkFloat32,
                    )
                    ref.SetSpacing(vol.spacing.tolist())
                    ref.SetOrigin(vol.origin.tolist())
                    ref.SetDirection(vol.matrix.flatten().tolist())

                    resampler = sitk.ResampleImageFilter()
                    resampler.SetReferenceImage(ref)
                    resampler.SetInterpolator(sitk.sitkLinear)
                    resampler.SetDefaultPixelValue(float(np.min(vol.data) if vol.data is not None else 0))
                    resampler.SetTransform(vs.space.transform)

                    src_img = sitk.Cast(vol.sitk_image, sitk.sitkFloat32)
                    new_sitk = resampler.Execute(src_img)

                    # Capture pre-bake state for overlay rebuild
                    old_state = self._capture_pre_reload_state(vs, vol)

                    # Sever old C++ bindings (tombstone pattern)
                    self._tombstone_image_memory(vs_id, vs, vol)

                    # Swap in the resampled data
                    vol.sitk_image = sitk.Cast(new_sitk, vol.sitk_image.GetPixelID()
                                                if vol.sitk_image else sitk.sitkFloat32)
                    vol.data = sitk.GetArrayViewFromImage(vol.sitk_image)

                    # Reset transform to identity
                    vs.space.transform = None
                    vs.space.is_active = False
                    vs.base_display_data = None
                    vs._sitk_base_cache = None

                    # Rebuild spatial engine (origin/spacing/matrix unchanged, no transform)
                    from vvv.maths.geometry import SpatialEngine
                    vs.space = SpatialEngine(vol, view_state=vs)

                    # Remap crosshair to new native voxel (transform is now identity)
                    if anchor_world is not None:
                        vs.update_crosshair_from_phys(anchor_world)

                    # Rebuild overlays that depended on this image
                    self._rebuild_dependent_overlays(vs_id, vs, vol, old_state)

                    self.update_all_viewers_of_image(vs_id)
                    self.sync.propagate_sync(vs_id)
                    self.status_message = "Transform baked into image"
                    self.ui_needs_refresh = True

                except Exception as e:
                    self.status_message = f"Bake failed: {e}"
                    self.ui_needs_refresh = True

        threading.Thread(target=_do_bake, daemon=True).start()

    def reset_settings(self):
        self.settings.reset()
        self._flag_all_viewers_dirty()

    def reset_image_view(self, vs_id, hard=False):
        """Resets the view and re-applies the boot-up synchronization logic."""
        if vs_id not in self.view_states:
            return

        vs = self.view_states[vs_id]

        if hard:
            vs.hard_reset()
        else:
            vs.reset_view()

        # Re-apply unifying math so it looks exactly like the initial load.
        same_viewers = [v.tag for v in self.viewers.values() if v.image_id == vs_id]
        if same_viewers:
            self.sync.propagate_ppm(same_viewers)

        # Force all linked viewers to perfectly re-center
        vs.camera.target_center = vs.camera.crosshair_phys_coord
        vs.is_geometry_dirty = True
        self.ui_needs_refresh = True

    def reload_settings(self):
        self.settings.reset()
        self.settings.load()

        self._flag_all_viewers_dirty()

    def reload_image(self, vs_id):
        if vs_id not in self.view_states:
            return

        vs = self.view_states[vs_id]
        vol = vs.volume

        self.status_message = f"Reloading {vol.name} ..."
        self.ui_needs_refresh = True

        with vs.loading_shield():
            # 1. Snapshot the world before the reload
            old_state = self._capture_pre_reload_state(vs, vol)

            # 2. Safely destroy C++ bindings to prevent Segfaults
            self._tombstone_image_memory(vs_id, vs, vol)

            # 3. Read the disk
            was_reset = vol.reload()

            # 4. Resolve the new spatial reality
            shape_changed = self._resolve_reloaded_geometry(
                vs_id, vs, vol, old_state, was_reset
            )

            # 5. Re-link Fusions/Overlays
            self._rebuild_dependent_overlays(vs_id, vs, vol, old_state)

            # 6. Flag UI
            self.status_message = f"Reloaded: {vol.name}"
            if shape_changed and self.gui and hasattr(self.gui, "rois_need_refresh"):
                self.gui.rois_need_refresh = True

        self.ui_needs_refresh = True

    # --- RELOAD HELPER METHODS ---

    def _capture_pre_reload_state(self, vs, vol):
        """Snapshots geometry and UX preferences before they are wiped out."""
        return {
            "shape": getattr(vol, "shape3d", None),
            "spacing": getattr(vol, "spacing", None),
            "ww": vs.display.ww,
            "wl": vs.display.wl,
            "cmap": vs.display.colormap,
            "overlay_id": vs.display.overlay_id,
            "overlay_mode": getattr(vs.display, "overlay_mode", "Alpha"),
            "overlay_opacity": getattr(vs.display, "overlay_opacity", 0.5),
        }

    def _tombstone_image_memory(self, vs_id, vs, vol):
        """Severs all Numpy views pointing to ITK C++ memory to prevent segfaults."""
        vs.base_display_data = None
        vs._sitk_base_cache = None
        vs.display.overlay_data = None
        vs.display._sitk_overlay_cache = None
        vol.data = None

        for other_vs in self.view_states.values():
            if getattr(other_vs.display, "overlay_id", None) == vs_id:
                other_vs.display.overlay_data = (
                    None  # Sever the other viewstate's overlay if it points to us
                )
                other_vs.display._sitk_overlay_cache = None  # Also sever the cache

        # Instantly blind the viewers so DPG doesn't read dead memory
        for v in self.viewers.values():
            v.is_viewer_data_dirty = True

    def _resolve_reloaded_geometry(self, vs_id, vs, vol, old_state, was_reset):
        """Checks if the image dimensions changed and re-aligns the UI accordingly."""
        shape_changed = old_state["shape"] is not None and old_state[
            "shape"
        ] != getattr(vol, "shape3d", None)
        spacing_changed = old_state["spacing"] is not None and not np.allclose(
            old_state["spacing"], getattr(vol, "spacing", [0, 0, 0])
        )

        if shape_changed or spacing_changed:
            vs.hard_reset()

            # Restore UX
            vs.display.ww = old_state["ww"]
            vs.display.wl = old_state["wl"]
            vs.display.colormap = old_state["cmap"]

            # Drop invalid ROIs
            for r_id in list(vs.rois.keys()):
                if self.volumes.get(r_id) and self.volumes[r_id].shape3d != vol.shape3d:
                    del vs.rois[r_id]

            # Rebuild GPU Textures
            for v in self.viewers.values():
                if v.image_id == vs_id:
                    v.drop_image()
                    v.last_drawn_image_id = None
                    v.set_image(vs_id)

            self.sync.propagate_window_level(vs_id)
            self.sync.propagate_colormap(vs_id)
            self.sync.propagate_sync(vs_id)

        else:
            if was_reset:
                vs.camera.target_center = vs.camera.crosshair_phys_coord
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
        vs.mark_both_dirty()
        self.update_all_viewers_of_image(vs_id)

        return shape_changed

    def _rebuild_dependent_overlays(self, vs_id, vs, vol, old_state):
        """Restores fusions that were attached to this image, or that this image was attached to."""
        # 1. Fix images that rely on us
        for other_id, other_vs in list(self.view_states.items()):
            if getattr(other_vs.display, "overlay_id", None) == vs_id:
                old_m = getattr(other_vs.display, "overlay_mode", "Alpha")
                old_o = getattr(other_vs.display, "overlay_opacity", 0.5)
                other_vs.set_overlay(vs_id, vol, self)
                other_vs.display.overlay_mode = old_m
                other_vs.display.overlay_opacity = old_o
                if hasattr(other_vs, "update_overlay_display_data"):
                    other_vs.update_overlay_display_data(self)
                self.update_all_viewers_of_image(other_id)

        # 2. Fix our own overlays
        if old_state["overlay_id"] and old_state["overlay_id"] in self.volumes:
            ov_vol = self.volumes[old_state["overlay_id"]]
            vs.set_overlay(old_state["overlay_id"], ov_vol, self)
            vs.display.overlay_mode = old_state["overlay_mode"]
            vs.display.overlay_opacity = old_state["overlay_opacity"]
            if hasattr(vs, "update_overlay_display_data"):
                vs.update_overlay_display_data(self)
            self.update_all_viewers_of_image(vs_id)

    def save_settings(self):
        return self.settings.save()

    def tick(self):
        for viewer in self.viewers.values():
            viewer.tick()

        # --- THE REACTIVE BRIDGE ---
        try:
            # Copy to list to avoid RuntimeError if background threads mutate dictionaries
            vs_items = list(self.view_states.items())
            vol_items = list(self.volumes.values())
        except RuntimeError:
            return  # Skip this frame's bridge updates if a background thread is mutating data

        # Optimized: Consolidate geometry and data checks into a single loop
        for vs_id, vs in vs_items:
            # Broadcast flags from central ViewState to all Viewers displaying it
            is_geom = getattr(vs, "is_geometry_dirty", False)
            is_data = getattr(vs, "is_data_dirty", False)

            if is_geom or is_data:
                self._flag_viewers_for_image(vs_id, data_dirty=is_data, geometry_dirty=is_geom)

            # Safe Reset (ONLY after all viewers in the loop have been flagged)
            vs.is_data_dirty = False
            vs.is_geometry_dirty = False

        # Check if files changed on disk, update UI if needed
        outdated_changed = False
        for vol in vol_items:
            if hasattr(vol, "is_outdated"):
                was_outdated = vol._is_outdated
                is_out = vol.is_outdated()
                if is_out != was_outdated:
                    outdated_changed = True

        if outdated_changed:
            self.ui_needs_refresh = True
