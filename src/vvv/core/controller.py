import os
import json
import math
import shlex
import threading
import numpy as np
import collections
import concurrent.futures
from typing import Any
from vvv.utils import ViewMode, write_json_atomic
from vvv.maths.image import VolumeData
from vvv.maths.geometry import SpatialEngine
from vvv.core.roi_manager import ROIManager
from vvv.core.file_manager import FileManager
from vvv.core.sync_manager import SyncManager
from vvv.core.contour_manager import ContourManager
from vvv.core.history_manager import HistoryManager
from vvv.core.settings_manager import SettingsManager
from vvv.core.profile_manager import ProfileManager
from vvv.core.overlay_resampler import resample_base, resample_overlay
from vvv.core.background_job import JobRunner
import logging

logger = logging.getLogger(__name__)


def _active_transform_copy(vs):
    """Copy of an image's active transform (same type), for a background job."""
    t = vs.space.transform if vs.space.is_active else None
    return None if t is None else type(t)(t)


class Controller:
    """
    The Central Manager and State-Only Bridge for VVV.

    ARCHITECTURE MANDATES (State-Only / Reactive):
    1. THE CONTROLLER AS A BRIDGE: This class is a "dumb" coordinator. It must NOT
       micromanage Viewers or the GUI. Its primary job is to sync data flags between
       the central 'ViewState' (Data) and the 'SliceViewer' (View).

    2. TICK LOOP PRIORITY: Inside the tick() loop, the Bridge broadcasts each
       ViewState's 'is_geometry_dirty' / 'is_data_dirty' to the Viewers displaying it
       (then resets the source flags) BEFORE the Viewers tick, so a change is
       rendered exactly once, in the same frame. Viewers only read their own flags.

    3. NO IMPERATIVE UI CALLS: Never call 'gui.refresh_rois_ui()' or 'dpg.set_value()'
       from this class or any of its Managers (FileManager, SyncManager, etc.).
       Instead, set 'self.ui_needs_refresh = True' and let the MainGUI handle it
       reactively in the next frame.

    4. THREAD SAFETY: Only the main thread touches DPG and the state viewers
       read (view states, volumes, display data). Background work computes from
       inputs captured on the main thread and hands its result to
       call_on_main(): the commit runs at the start of the next tick().

    5. GEOMETRY UPDATES: To force a viewer re-center, DO NOT set 'viewer.needs_recenter'.
       Instead, set 'vs.camera.target_center = world_pos'. The Viewers watch this
       central data and re-calibrate themselves autonomously.
    """

    def __init__(self):
        self.gui: Any = None
        self.volumes = {}
        self.view_states = {}
        self.viewers = {}
        self._state_lock = threading.RLock()

        self.layout: dict[str, str | None] = {
            "V1": None,
            "V2": None,
            "V3": None,
            "V4": None,
        }

        self.file = FileManager(self)
        self.sync = SyncManager(self)
        self.roi = ROIManager(self)
        self.contours = ContourManager(self)
        self.settings = SettingsManager()
        self.history = HistoryManager()
        self.profiles = ProfileManager(self)

        self.use_history = True
        self.next_image_id = 1

        # Background-job results to apply on the main thread (call_on_main)
        self._main_commits = collections.deque()

        # ITK images whose numpy views may still be in use by the main thread
        # (see _retire); released at the start of the next tick().
        self._retired = []
        self._retired_lock = threading.Lock()

        # One JobRunner per image, lazily created. resample_image() and
        # bake_transform_to_volume() share the same runner for a given vs_id so
        # they can never race each other on that image's data.
        self._job_runners: dict[str, JobRunner] = {}

        self.ui_needs_refresh = False
        self.ui_needs_layout_rebuild = False
        self.debug_mode = False
        self.status_message: str | None = None

    def get_plugin(self, plugin_id: str) -> Any | None:
        """Safely retrieve a plugin by its ID from the GUI."""
        if self.gui:
            return self.gui.get_plugin(plugin_id)
        return None

    def allocate_image_id(self) -> str:
        """Return a new unique image id. Thread-safe: images load in parallel."""
        with self._state_lock:
            img_id = str(self.next_image_id)
            self.next_image_id += 1
            return img_id

    def get_next_image_id(self, current_id):
        with self._state_lock:
            if not self.view_states:
                return None
            keys = list(self.view_states.keys())
        if current_id not in keys:
            return keys[0]
        next_idx = (keys.index(current_id) + 1) % len(keys)
        return keys[next_idx]

    def default_viewers_orientation(self):
        # Count the displayed images: one only fused as overlay of another
        # (e.g. CT + PET fusion) does not need its own viewers.
        overlays = {vs.display.overlay.image_id for vs in self.view_states.values()}
        n = len([i for i in self.view_states if i not in overlays]) or len(self.view_states)
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
                    logger.exception(f"Failed to load {path}. Error: {exc}")

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
            logger.exception(f"Error loading transform: {e}")
            return False

    def save_transform(self, vs_id, filepath):
        vs = self.view_states.get(vs_id)
        if vs and vs.space.transform:
            try:
                from vvv.maths.transform_io import TransformIO

                if not os.path.splitext(filepath)[1]:
                    filepath = filepath + ".tfm"

                TransformIO.write_transform(vs.space.transform, filepath)
                vs.space.transform_file = os.path.basename(filepath)
                vs.space.full_transform_path = os.path.abspath(filepath)
                return True
            except Exception as e:
                logger.exception(f"Failed to save transform: {e}")
                return False
        return False

    def add_recent_file(self, path):
        """Adds a path to the recent files list in settings and caps it at 10."""
        if isinstance(path, list):
            path = [os.path.abspath(p) for p in path]
        elif isinstance(path, str):
            if path.startswith("4D:"):
                try:
                    path_for_shlex = (
                        path[3:].replace("\\", "\\\\") if os.name == "nt" else path[3:]
                    )
                    tokens = shlex.split(path_for_shlex)
                    abs_tokens = [os.path.abspath(t) for t in tokens]
                    path = "4D:" + " ".join(f'"{t}"' for t in abs_tokens)
                except Exception:
                    pass
            else:
                path = os.path.abspath(path)

        behavior: Any = self.settings.data.setdefault("behavior", {})
        if not isinstance(behavior, dict):
            behavior = {}
            self.settings.data["behavior"] = behavior

        recent: Any = behavior.setdefault("recent_files", [])
        if not isinstance(recent, list):
            recent = []
            behavior["recent_files"] = recent

        # Convert list (DICOM series) to JSON string to make it hashable and storable
        path_str = json.dumps(path) if isinstance(path, list) else path

        if path_str in recent:
            recent.remove(path_str)
        recent.insert(0, path_str)

        # Cap at 20
        behavior["recent_files"] = recent[:20]
        self.save_settings()

    def resolve_recent_path(self, path):
        """Resolves a path from the recent files. If not found, searches for a ~ equivalent path."""
        if isinstance(path, list):
            return [self.resolve_recent_path(p) for p in path]
        elif isinstance(path, str):
            if path.startswith("4D:"):
                try:
                    path_for_shlex = (
                        path[3:].replace("\\", "\\\\") if os.name == "nt" else path[3:]
                    )
                    tokens = shlex.split(path_for_shlex)
                    resolved_tokens = [self._resolve_single_path(t) for t in tokens]
                    return "4D:" + " ".join(f'"{t}"' for t in resolved_tokens)
                except Exception:
                    return path
            else:
                return self._resolve_single_path(path)
        return path

    def _resolve_single_path(self, p):
        if os.path.exists(p):
            return p

        expanded = os.path.expanduser(p)
        if os.path.exists(expanded):
            return expanded

        normalized = p.replace("\\", "/")
        if normalized.startswith("/home/") or normalized.startswith("/Users/"):
            parts = normalized.split("/")
            if len(parts) >= 4:
                rest_parts = parts[3:]
                home = os.path.expanduser("~")
                alt_path = os.path.join(home, *rest_parts)
                if os.path.exists(alt_path):
                    return alt_path
        return p

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
        base_name = vol.name

        # Clean any existing leading (number) prefix for dynamic index display
        import re

        clean_name = re.sub(r"^\(\d+\)\s*", "", base_name)

        name_str = f"({idx}) {clean_name}"
        if is_outdated:
            name_str += " *"
        return name_str, is_outdated

    def save_image(self, vs_id, filepath):
        """Exports the volume to disk as a NIfTI, MHD, etc. (synchronous)."""
        vol = self._volume_to_save(vs_id)
        if vol is None:
            return
        state = self._write_image_files(vol.sitk_image, getattr(vol, "unit", None), filepath)
        self._apply_saved_state(vol, filepath, state)

    def save_image_async(self, vs_id, filepath):
        """Same as save_image(), writing the files in a background thread.

        The image is captured now (main thread); the volume's path/name are
        updated, or the error reported, on the main thread when it is done.
        """
        vol = self._volume_to_save(vs_id)
        if vol is None:
            return
        img, unit = vol.sitk_image, getattr(vol, "unit", None)
        name = os.path.basename(filepath)

        def _save():
            try:
                state = self._write_image_files(img, unit, filepath)
            except Exception as e:
                msg = f"Save failed ({name}): {e}"
                self.call_on_main(lambda: self._set_status(msg))
                return

            def _commit():
                self._apply_saved_state(vol, filepath, state)
                self._set_status(f"Saved: {name}")

            self.call_on_main(_commit)

        threading.Thread(target=_save, daemon=True).start()

    def _volume_to_save(self, vs_id):
        vol = self.volumes.get(vs_id)
        if vol is None:  # Guard against invalid vs_id
            logger.error(f"Volume {vs_id} not found for saving.")
            return None
        if vol.data is None:  # Guard against unloaded data
            logger.error(f"Volume {vs_id} has no data loaded.")
            return None
        return vol

    @staticmethod
    def _write_image_files(img, unit_val, filepath):
        """Write the image and its unit sidecar JSON. Touches no app state."""
        import SimpleITK as sitk

        sitk.WriteImage(img, filepath)

        # Update or create sidecar JSON if unit is set or sidecar exists
        if filepath.endswith(".nii.gz"):
            json_path = filepath[:-7] + ".json"
        else:
            json_path = os.path.splitext(filepath)[0] + ".json"

        state = {}
        if unit_val is not None or os.path.isfile(json_path):
            try:
                jdata = {}
                if os.path.isfile(json_path):
                    with open(json_path, "r", encoding="utf-8") as f:
                        jdata = json.load(f)
                    if not isinstance(jdata, dict):
                        jdata = {}
                if unit_val:
                    jdata["unit"] = unit_val
                elif "unit" in jdata:
                    del jdata["unit"]
                if jdata:
                    write_json_atomic(json_path, jdata)
                    state["sidecar_json_path"] = json_path
                    if unit_val:
                        state["unit_source"] = os.path.basename(json_path)
            except Exception as e:
                logger.warning(f"Failed to write sidecar JSON {json_path}: {e}")
        return state

    @staticmethod
    def _apply_saved_state(vol, filepath, state):
        """Main thread: the volume now refers to the file it was saved to."""
        for key, value in state.items():
            setattr(vol, key, value)
        vol.path = filepath
        vol.file_paths = [filepath]
        vol.name = os.path.basename(filepath)
        vol.update_mtime_tracker()
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
        val = (
            vol.data[t, iz, iy, ix] if vol.num_timepoints > 1 else vol.data[iz, iy, ix]
        )
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
            if (
                vs.display.overlay.image_id
                and vs.display.overlay.image_id in self.volumes
            ):
                ov_vol = self.volumes[vs.display.overlay.image_id]
                ov_vs = self.view_states[vs.display.overlay.image_id]
                overlay_val, _, _, _ = self._get_voxel_value(
                    ov_vol, ov_vs, phys_coord, time_idx
                )

            # 3. Intersecting ROIs (ROIs share the Base Image's spatial grid)
            roi_names = []
            for r_id, r_state in list(vs.rois.items()):
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

    def set_sync_wl_group(self, vs_id, group_id):
        """
        Programmatically sets the W/L sync group for an image and broadcasts
        the W/L and colormap from an existing group master to it.
        """
        vs = self.view_states.get(vs_id)
        if not vs:
            return

        if vs.sync_wl_group == group_id:
            return

        vs.sync_wl_group = group_id

        if group_id == 0:
            self.update_all_viewers_of_image(vs_id)
            self.ui_needs_refresh = True
            return

        # Find the source of truth for this group
        master_vs_id = None
        active_viewer = self.gui.context_viewer if self.gui else None
        if active_viewer and active_viewer.image_id in self.view_states:
            if self.view_states[active_viewer.image_id].sync_wl_group == group_id:
                master_vs_id = active_viewer.image_id

        if not master_vs_id:
            for other_id, other_vs in list(self.view_states.items()):
                if other_id != vs_id and other_vs.sync_wl_group == group_id:
                    master_vs_id = other_id
                    break

        if master_vs_id:
            self.sync.propagate_window_level(master_vs_id)
            self.sync.propagate_colormap(master_vs_id)
            self.sync.propagate_overlay_opacity(master_vs_id)

        self.ui_needs_refresh = True

    def update_all_viewers_of_image(self, vs_id, data_dirty=True):
        if vs_id in self.view_states and data_dirty:
            self.view_states[vs_id].is_data_dirty = True
            # Flag the viewers now rather than at the next tick's broadcast
            self._flag_viewers_for_image(vs_id, data_dirty=True)
        else:
            self._flag_viewers_for_image(vs_id, geometry_dirty=True)

    def _flag_viewers_for_image(self, vs_id, data_dirty=False, geometry_dirty=False):
        """Set dirty flags on all viewers that display vs_id as base image or overlay."""
        for v in self.viewers.values():
            if v.image_id == vs_id or (
                v.view_state and v.view_state.display.overlay.image_id == vs_id
            ):
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

        if isinstance(keys, str):
            keys = [keys]

        d: Any = self.settings.data
        for key in keys[:-1]:
            if not isinstance(d, dict):
                return
            if key in d and not isinstance(d[key], dict):
                return
            if key not in d:
                d[key] = {}
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

    def _retire(self, *objs):
        """Keep ITK images alive until the main thread's next tick().

        Display arrays are numpy *views* of ITK images (GetArrayViewFromImage)
        and do not keep them alive: if a background thread drops an image while
        the main thread is still reading a view of it, that read hits freed
        memory. Anything a worker replaces is retired here instead; tick() on
        the main thread releases it, when no view from the previous frame is
        still in use (no main-thread code keeps such views across frames).
        """
        objs = [o for o in objs if o is not None]
        if objs:
            with self._retired_lock:
                self._retired.extend(objs)

    def _get_job_runner(self, vs_id) -> JobRunner:
        """Return this image's background JobRunner, creating it on first use.

        Shared by resample_image() and bake_transform_to_volume() so the two
        can never run concurrently on the same image's data.
        """
        runner = self._job_runners.get(vs_id)
        if runner is None:
            runner = JobRunner()
            self._job_runners[vs_id] = runner
        return runner

    def update_transform_manual(self, vs_id, tx, ty, tz, rx_deg, ry_deg, rz_deg):
        vs = self.view_states.get(vs_id)
        if not vs:
            return
        vs.space.set_manual_transform(
            tx, ty, tz, math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
        )
        # Mark any in-flight resample/bake for this image as stale.
        self._get_job_runner(vs_id).invalidate()

    def resample_image(self, image_id, include_dependents=True):
        """Resample image_id's rotated base and overlays on its background JobRunner.

        Inputs are captured now (main thread), the worker only computes, and the
        results are committed on the main thread (_commit_resample, run by
        tick()): no other thread ever writes display data. A job superseded by a
        newer submit, or by update_transform_manual() (invalidate()), is
        discarded at commit. Recomputes the base rotation (if any), this image's
        overlay and, with include_dependents, the overlays of images that
        display this one as overlay. Each job is a full recompute because a
        JobRunner keeps only the latest queued job.
        """
        vs = self.view_states.get(image_id)
        if not vs:
            return

        self.ui_needs_refresh = True  # update UI debug indicator immediately

        rot = (
            vs.space.get_rotation_only_transform()
            if vs.space.is_active and vs.space.has_rotation()
            else None
        )
        pairs = []  # (target view state, overlay id): target displays overlay id
        if vs.display.overlay.image_id in self.view_states:
            pairs.append((vs, vs.display.overlay.image_id))
        if include_dependents:
            pairs += [
                (other_vs, image_id)
                for other_vs in self.view_states.values()
                if other_vs.display.overlay.image_id == image_id
            ]
        inputs = [
            (
                target,
                ov_id,
                target.volume,
                self.view_states[ov_id].volume,
                _active_transform_copy(target),
                _active_transform_copy(self.view_states[ov_id]),
            )
            for target, ov_id in pairs
        ]
        base_vol = vs.volume

        def _do(job):
            base = resample_base(base_vol, rot) if rot is not None else (None, None)
            overlays = []
            for target, ov_id, t_vol, ov_vol, t_tr, ov_tr in inputs:
                if not job.is_current():
                    return  # superseded: the newer job will commit
                overlays.append((target, ov_id, resample_overlay(t_vol, ov_vol, t_tr, ov_tr)))
            self.call_on_main(lambda: self._commit_resample(job, image_id, base, overlays))

        self._get_job_runner(image_id).submit(_do)

    def _commit_resample(self, job, image_id, base, overlays):
        """Main thread: swap in the results of a resample_image() job."""
        vs = self.view_states.get(image_id)
        if not vs:
            return
        if not job.is_current():
            self._discard_resample()
            return

        vs.reset_preview_rotation()
        self._retire(vs._sitk_base_cache)  # views of it may be in use this frame
        vs._sitk_base_cache, vs.base_display_data = base

        for target, ov_id, (cache, data, baked) in overlays:
            if target.display.overlay.image_id != ov_id:
                continue  # overlay changed or removed meanwhile
            self._retire(target.display._sitk_overlay_cache)
            target.display._sitk_overlay_cache = cache
            target.display.overlay_data = data
            target.display.baked_overlay_translation = baked
            target.is_data_dirty = True

        if vs.base_display_data is not None and vs.camera.crosshair_phys_coord is not None:
            vs.update_crosshair_from_phys(vs.camera.crosshair_phys_coord)

        vs.needs_resample = False
        self.update_all_viewers_of_image(image_id)
        self.status_message = "Resampling complete"
        self.ui_needs_refresh = True

    def _discard_resample(self):
        self.status_message = "Resample discarded (superseded)"
        self.ui_needs_refresh = True

    def _apply_overlay_resample(self, base_vs, ovs, job=None):
        """Resample ovs onto base_vs's grid and apply it now, synchronously.

        Main thread only (setup code, tests): background resampling goes through
        resample_image(). The replaced ITK cache is retired, not freed, since
        views of it may still be in use this frame. If a `Job` is given, keeps
        the previous overlay when that job has been superseded.
        """
        _old_cache = base_vs.display._sitk_overlay_cache
        base_vs.display._sitk_overlay_cache = None

        new_cache, new_data, baked = resample_overlay(
            base_vs.volume,
            ovs.volume,
            base_vs.space.transform if base_vs.space.is_active else None,
            ovs.space.transform if ovs.space.is_active else None,
        )

        if job is not None and not job.is_current():
            base_vs.display._sitk_overlay_cache = _old_cache
            return

        base_vs.display._sitk_overlay_cache = new_cache
        base_vs.display.overlay_data = new_data
        base_vs.display.baked_overlay_translation = baked
        # The main thread may still be reading the old overlay_data view
        self._retire(_old_cache)
        base_vs.is_data_dirty = True

    def bake_transform_to_volume(self, vs_id):
        """Permanently apply the registration transform by resampling the volume.

        The worker resamples from inputs captured now (main thread); the swap is
        committed on the main thread (_commit_bake, run by tick()). After baking,
        the transform is reset to identity and the image is indistinguishable
        from one loaded without any transform. Shares the image's JobRunner with
        resample_image(), so a newer resample/bake or a transform change
        supersedes it.
        """
        import SimpleITK as sitk

        vs: Any = self.view_states.get(vs_id)
        vol: Any = self.volumes.get(vs_id)
        if not vs or not vol or not vs.space.transform or not vs.space.is_active:
            return

        anchor_world = (
            vs.camera.crosshair_phys_coord.copy()
            if vs.camera.crosshair_phys_coord is not None
            else None
        )
        src = vol.sitk_image  # this reference keeps the source alive in the worker
        inverse = vs.space.transform.GetInverse()
        size = [int(vol.shape3d[2]), int(vol.shape3d[1]), int(vol.shape3d[0])]
        spacing, origin = vol.spacing.tolist(), vol.origin.tolist()
        direction = vol.matrix.flatten().tolist()

        def _do_bake(job):
            try:
                # Reference grid: same size/spacing/origin/direction as the original
                ref = sitk.Image(*size, sitk.sitkFloat32)
                ref.SetSpacing(spacing)
                ref.SetOrigin(origin)
                ref.SetDirection(direction)

                resampler = sitk.ResampleImageFilter()
                resampler.SetReferenceImage(ref)
                resampler.SetInterpolator(sitk.sitkLinear)
                resampler.SetDefaultPixelValue(
                    float(np.min(sitk.GetArrayViewFromImage(src)))
                )
                resampler.SetTransform(inverse)
                new_sitk = resampler.Execute(sitk.Cast(src, sitk.sitkFloat32))
                new_sitk = sitk.Cast(new_sitk, src.GetPixelID())
            except Exception as e:
                msg = f"Bake failed: {e}"
                self.call_on_main(lambda: self._set_status(msg))
                return
            self.call_on_main(lambda: self._commit_bake(job, vs_id, new_sitk, anchor_world))

        self._get_job_runner(vs_id).submit(_do_bake)

    def _set_status(self, message, level=None):
        """Status bar message, shown by the GUI at its next frame.

        level: None, or a ui_cfg color name ("working", "warning").
        """
        self.status_message = message if level is None else (message, level)
        self.ui_needs_refresh = True

    def _commit_bake(self, job, vs_id, new_sitk, anchor_world):
        """Main thread: swap the baked volume in, reset the transform, re-link overlays."""
        import SimpleITK as sitk

        vs, vol = self.view_states.get(vs_id), self.volumes.get(vs_id)
        if not vs or not vol:
            return
        if not job.is_current():
            self._set_status("Bake discarded (superseded)")
            return

        old_state = self._capture_pre_reload_state(vs, vol)
        data_snapshot = self._capture_volume_data_snapshot(vs_id, vs, vol)
        try:
            self._drop_display_data(vs_id, vs, vol)
            vol.sitk_image = new_sitk
            vol.data = sitk.GetArrayViewFromImage(new_sitk)
            vol._is_outdated = True

            # Transform is now identity: rebuild the spatial engine
            vs.space.transform = None
            vs.space.is_active = False
            vs.space = SpatialEngine(vol, view_state=vs)
            if anchor_world is not None:
                vs.update_crosshair_from_phys(anchor_world)
        except Exception as e:
            self._restore_volume_data_snapshot(vs_id, vs, vol, data_snapshot)
            self._set_status(f"Bake failed: {e}")
            return

        self._retire(data_snapshot)  # old images: views may still be in use
        self._rebuild_dependent_overlays(vs_id, vs, vol, old_state)
        self.update_all_viewers_of_image(vs_id)
        self.sync.propagate_sync(vs_id)
        self._set_status("Transform baked into image")

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

        # 0. Signal plugins to safely abort any background threads accessing this image
        if self.gui:
            self.gui.notify_plugins_image_reloading(vs_id)

        # 1. Snapshot the world and memory before the reload
        old_state = self._capture_pre_reload_state(vs, vol)
        data_snapshot = self._capture_volume_data_snapshot(vs_id, vs, vol)

        try:
            # 2. Safely destroy C++ bindings to prevent Segfaults
            self._drop_display_data(vs_id, vs, vol)

            # 3. Read the disk
            was_reset = vol.reload()
            if not was_reset and vol.data is None:
                raise RuntimeError("Reload failed or was aborted.")
        except Exception as e:
            # Restore previous state on failure
            self._restore_volume_data_snapshot(vs_id, vs, vol, data_snapshot)
            self.status_message = f"Reload failed: {e}"
            self.ui_needs_refresh = True
            return

        # 4. Resolve the new spatial reality
        self._resolve_reloaded_geometry(vs_id, vs, vol, old_state, was_reset)

        # 5. Re-link Fusions/Overlays
        self._rebuild_dependent_overlays(vs_id, vs, vol, old_state)

        # 6. Notify plugins that reload has finished so they can refresh caches
        if self.gui:
            self.gui.notify_plugins_image_reloaded(vs_id)

        # 7. Flag UI
        self._set_status(f"Reloaded: {vol.name}")

    # --- RELOAD HELPER METHODS ---

    def _capture_pre_reload_state(self, vs, vol):
        """Snapshots geometry and UX preferences before they are wiped out."""
        return {
            "shape": getattr(vol, "shape3d", None),
            "spacing": getattr(vol, "spacing", None),
            "ww": vs.display.ww,
            "wl": vs.display.wl,
            "cmap": vs.display.colormap,
            "overlay_id": vs.display.overlay.image_id,
            "overlay_mode": vs.display.overlay.mode,
            "overlay_opacity": vs.display.overlay.opacity,
        }

    def _drop_display_data(self, vs_id, vs, vol):
        """Drop everything displayed from this image's data before it is replaced
        (main thread): its own buffers, the overlays other images derive from it,
        and the viewers' slice caches. The old ITK images stay alive in the
        caller's snapshot (restored on failure, else retired)."""
        vs.base_display_data = None
        vs._sitk_base_cache = None
        vs.display.overlay_data = None
        vs.display._sitk_overlay_cache = None
        vol.data = None
        vol.data_4d = None

        for other_vs in self.view_states.values():
            if other_vs.display.overlay.image_id == vs_id:
                other_vs.display.overlay_data = (
                    None  # Sever the other viewstate's overlay if it points to us
                )
                other_vs.display._sitk_overlay_cache = None  # Also sever the cache

        # Instantly blind the viewers and flush temporary slice preview caches
        for v in self.viewers.values():
            if v.image_id == vs_id:
                v.is_viewer_data_dirty = True
                v.is_geometry_dirty = True
                if hasattr(v, "_preview_slices"):
                    v._preview_slices.clear()
                if hasattr(v, "_overlay_preview_slices"):
                    v._overlay_preview_slices.clear()

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

        vs.mark_both_dirty()
        self.update_all_viewers_of_image(vs_id)

        return shape_changed

    def _capture_volume_data_snapshot(self, vs_id, vs, vol):
        snapshot = {
            "vol_sitk_image": vol.sitk_image,
            "vol_data": vol.data,
            "vs_base_display_data": vs.base_display_data,
            "vs_sitk_base_cache": vs._sitk_base_cache,
            "vs_overlay_data": vs.display.overlay_data,
            "vs_sitk_overlay_cache": vs.display._sitk_overlay_cache,
            "dependent_overlays": {},
        }
        for other_id, other_vs in self.view_states.items():
            if other_vs.display.overlay.image_id == vs_id:
                snapshot["dependent_overlays"][other_id] = {
                    "overlay_data": other_vs.display.overlay_data,
                    "sitk_overlay_cache": other_vs.display._sitk_overlay_cache,
                }
        return snapshot

    def _restore_volume_data_snapshot(self, vs_id, vs, vol, snapshot):
        vol.sitk_image = snapshot["vol_sitk_image"]
        vol.data = snapshot["vol_data"]
        vs.base_display_data = snapshot["vs_base_display_data"]
        vs._sitk_base_cache = snapshot["vs_sitk_base_cache"]
        vs.display.overlay_data = snapshot["vs_overlay_data"]
        vs.display._sitk_overlay_cache = snapshot["vs_sitk_overlay_cache"]

        for other_id, other_snapshot in snapshot["dependent_overlays"].items():
            other_vs = self.view_states.get(other_id)
            if other_vs:
                other_vs.display.overlay_data = other_snapshot["overlay_data"]
                other_vs.display._sitk_overlay_cache = other_snapshot[
                    "sitk_overlay_cache"
                ]

        self.update_all_viewers_of_image(vs_id)

    def _rebuild_dependent_overlays(self, vs_id, vs, vol, old_state):
        """Restore the fusions attached to this image, or that this image was attached to.

        Main thread. The links (mode, opacity) are restored now; the overlay data
        is recomputed by background resample jobs. Submitting them also
        supersedes any job still computing from the old data.
        """
        # 1. Images that display us as overlay
        dependents = []
        for other_id, other_vs in list(self.view_states.items()):
            if other_vs.display.overlay.image_id == vs_id:
                old_m = other_vs.display.overlay.mode
                old_o = other_vs.display.overlay.opacity
                other_vs.set_overlay(vs_id, vol)
                other_vs.display.overlay.mode = old_m
                other_vs.display.overlay.opacity = old_o
                dependents.append(other_id)

        # 2. Our own overlay
        if old_state["overlay_id"] and old_state["overlay_id"] in self.volumes:
            vs.set_overlay(old_state["overlay_id"], self.volumes[old_state["overlay_id"]])
            vs.display.overlay.mode = old_state["overlay_mode"]
            vs.display.overlay.opacity = old_state["overlay_opacity"]

        self.resample_image(vs_id, include_dependents=False)
        for other_id in dependents:
            self.resample_image(other_id)

    def save_settings(self):
        try:
            return self.settings.save()
        except Exception as e:
            logger.warning(f"Could not save settings: {e}")
            return None

    def call_on_main(self, fn):
        """Queue fn to run on the main thread, at the start of the next tick()."""
        self._main_commits.append(fn)

    def run_main_thread_commits(self):
        """Run the queued background-job commits (main thread; tick() calls it)."""
        while self._main_commits:
            fn = self._main_commits.popleft()
            try:
                fn()
            except Exception as e:
                import traceback

                traceback.print_exc()
                self._set_status(f"Background job commit failed: {e}")

    def wait_for_jobs(self, timeout=60.0):
        """Main thread, without a running GUI loop (scripts, screenshots, tests):
        wait for every background job and run its commit. False on timeout."""
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            self.run_main_thread_commits()
            if not self._main_commits and all(
                r.is_idle() for r in list(self._job_runners.values())
            ):
                return True
            time.sleep(0.005)
        return False

    def tick(self):
        # Previous frame is over: retired ITK images can be freed now
        with self._retired_lock:
            self._retired.clear()
        self.run_main_thread_commits()

        with self._state_lock:
            vs_items = list(self.view_states.items())
            vol_items = list(self.volumes.values())

        # Broadcast flags from each central ViewState to the Viewers displaying it,
        # then let the Viewers render. Read and reset are kept adjacent so a flag
        # set by another thread is not lost in between.
        for vs_id, vs in vs_items:
            is_geom, vs.is_geometry_dirty = vs.is_geometry_dirty, False
            is_data, vs.is_data_dirty = vs.is_data_dirty, False
            if is_geom or is_data:
                self._flag_viewers_for_image(
                    vs_id, data_dirty=is_data, geometry_dirty=is_geom
                )

        for viewer in self.viewers.values():
            viewer.tick()

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
