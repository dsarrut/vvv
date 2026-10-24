import os
import json
from vvv.maths.image import VolumeData
from vvv.core.view_state import ViewState
from vvv.utils import resolve_history_path_key, write_json_atomic


class FileManager:
    """Manages disk I/O: Loading images, parsing DICOMs, and saving Workspaces."""

    def __init__(self, controller):
        self.controller = controller

    def load_image(self, path, is_auto_overlay=False, ignore_history=False):
        """Read and register an image (main thread). Returns its id."""
        return self.register_image(self.read_image(path, is_auto_overlay, ignore_history))

    def read_image(self, path, is_auto_overlay=False, ignore_history=False):
        """Read an image from disk, without registering it. Safe in a worker thread.

        Builds the VolumeData + ViewState (restoring its history) and also reads
        the overlay remembered in its history, so that no disk read is left for
        register_image(), which runs on the main thread.
        """
        vol = VolumeData(path)
        vs = ViewState(vol)

        # History
        history_entry = (
            self.controller.history.get_image_state(vol)
            if self.controller.use_history and not ignore_history
            else None
        )

        if history_entry:
            vs.camera.from_dict(history_entry["camera"])
            vs.display.from_dict(history_entry["display"])
            if "dvf" in history_entry and getattr(vol, "is_dvf", False):
                vs.dvf.from_dict(history_entry["dvf"])

            # Re-derive the crosshair_value based on restored voxel
            if vs.camera.crosshair_voxel is not None:
                ix, iy, iz = [int(v) for v in vs.camera.crosshair_voxel[:3]]
                max_z, max_y, max_x = vol.shape3d

                # Only apply the saved crosshair if it strictly fits inside the new volume
                if 0 <= iz < max_z and 0 <= iy < max_y and 0 <= ix < max_x:
                    if vol.num_timepoints > 1:
                        vs.crosshair_value = vol.data[vs.camera.time_idx, iz, iy, ix]
                    else:
                        vs.crosshair_value = vol.data[iz, iy, ix]
                else:
                    # Ignore the out-of-bounds history!
                    vs.camera.crosshair_voxel = None

            vs.is_data_dirty = True

        # Auto-load overlay
        # Prevent infinite recursion with is_auto_overlay flag
        overlay = None
        if history_entry and history_entry.get("overlay_path") and not is_auto_overlay:
            op_path = resolve_history_path_key(history_entry["overlay_path"])
            if os.path.exists(op_path):
                overlay = self.read_image(op_path, is_auto_overlay=True)

        return {
            "path": path,
            "vol": vol,
            "vs": vs,
            "history": history_entry,
            "is_auto_overlay": is_auto_overlay,
            "overlay": overlay,
        }

    def register_image(self, loaded):
        """Register an image returned by read_image() and notify plugins.

        Main thread only: plugins may build UI, and settings are saved.
        """
        vol, vs, history_entry = loaded["vol"], loaded["vs"], loaded["history"]
        is_auto_overlay = loaded["is_auto_overlay"]

        img_id = self.controller.allocate_image_id()
        with self.controller._state_lock:
            self.controller.volumes[img_id] = vol
            self.controller.view_states[img_id] = vs

        # Before the plugins hear of it: they see the image as displayed
        self.controller.apply_transform_sidecar(img_id)

        if self.controller.gui and not is_auto_overlay:
            self.controller.gui.notify_plugins_image_loaded(img_id)
            if history_entry and "plugins" in history_entry:
                for plugin in self.controller.gui.plugins:
                    plugin_data = history_entry["plugins"].get(plugin.plugin_id, {})
                    if plugin_data:
                        plugin.restore_image_state(
                            img_id, plugin_data, context="history"
                        )

        if loaded["overlay"] is not None:
            op_id = self.register_image(loaded["overlay"])
            # Restore the link (opacity, mode, threshold are already restored in from_dict).
            vs.set_overlay(op_id, self.controller.volumes[op_id])

        if not is_auto_overlay:
            self.controller.add_recent_file(loaded["path"])
        if getattr(vol, "sidecar_error", None):
            self.controller._set_status(
                f"Side-car not read: {vol.sidecar_error}", level="warning"
            )

        self.controller.ui_needs_refresh = True
        return img_id

    def scan_dicom_folder(self, folder_path, recursive=True, use_cache=True):
        """Scans a folder for DICOM series and YIELDS progress updates:
        (fraction, folder name) per folder, then (1.0, "Done", series, errors).

        Each folder whose files are unchanged since the last scan of this root
        is read from the scan cache (core.dicom_scan); use_cache=False scans
        everything again and rebuilds the cache. self.last_dicom_scan holds
        how many folders came from the cache."""
        import SimpleITK as sitk
        from vvv.core.dicom_scan import (
            DicomScanCache,
            dir_signature,
            finalize_series,
            merge_dir_entries,
            scan_dicom_dir,
        )

        self.last_dicom_scan = {"dirs": 0, "cached": 0, "use_cache": use_cache}
        if not os.path.exists(folder_path):
            yield (1.0, "Done", [], [])
            return

        series_dict = {}
        scan_errors = []
        search_dirs = (
            [x[0] for x in os.walk(folder_path, followlinks=True)]
            if recursive
            else [folder_path]
        )
        total_dirs = max(1, len(search_dirs))
        cache = DicomScanCache(folder_path)

        reader = sitk.ImageSeriesReader()
        file_reader = sitk.ImageFileReader()
        sitk.ProcessObject.SetGlobalWarningDisplay(False)  # silence GDCM warnings
        try:
            for i, d in enumerate(search_dirs):
                yield (i / total_dirs, os.path.basename(d))
                sig = dir_signature(d)
                entries = cache.get(d, sig) if use_cache else None
                if entries is None:
                    cache.seen.add(d)
                    try:
                        entries = scan_dicom_dir(d, reader, file_reader)
                    except Exception as e:
                        scan_errors.append(f"{d}: {e}")
                        continue  # not cached: scanned again next time
                    cache.put(d, sig, entries)
                merge_dir_entries(series_dict, entries)
        finally:
            sitk.ProcessObject.SetGlobalWarningDisplay(True)

        cache.save()
        self.last_dicom_scan = {"dirs": len(search_dirs), "cached": cache.hits, "use_cache": use_cache}
        yield (1.0, "Done", finalize_series(series_dict), scan_errors)

    def save_workspace(self, filepath, view=None):
        """Write the workspace file.

        view: the GUI viewport layout, {"layout": "1"|"2"|"4", "active_viewer":
        tag, "visible_viewers": [tags]}; any missing key gets a default.
        """
        view = view or {}
        active_layout = str(view.get("layout") or "4")
        active_viewer_tag = view.get("active_viewer") or "V1"
        visible_viewers = view.get("visible_viewers")
        if visible_viewers:
            visible_viewers = [str(x) for x in visible_viewers]
        elif active_layout == "2":
            visible_viewers = ["V1", "V2"]
        elif active_layout == "1":
            visible_viewers = [active_viewer_tag]
        else:
            visible_viewers = ["V1", "V2", "V3", "V4"]

        workspace = {
            "version": 1.0,
            "workspace_path": os.path.abspath(filepath),
            "layout_mode": str(active_layout),
            "active_viewer": active_viewer_tag,
            "visible_viewers": visible_viewers,
            "viewers": {},
            "images": {},
        }

        # for home as ~
        def portable_path(p):
            if not p:
                return ""
            if isinstance(p, list):
                return [portable_path(x) for x in p]
            if isinstance(p, str) and p.startswith("4D:"):
                return p
            home = os.path.expanduser("~")
            abs_p = os.path.abspath(p)
            if abs_p.startswith(home):
                return abs_p.replace(home, "~", 1)
            return abs_p

        # Track all image IDs currently assigned to a viewer
        active_viewer_ids = set()

        # 1. Save Viewers
        for tag, viewer in self.controller.viewers.items():
            if getattr(viewer, "image_id", None):
                active_viewer_ids.add(viewer.image_id)
                nr = getattr(viewer, "needs_recenter", False)
                workspace["viewers"][tag] = {
                    "image_id": str(viewer.image_id),
                    "orientation": (
                        viewer.orientation.name
                        if hasattr(viewer.orientation, "name")
                        else str(viewer.orientation)
                    ),
                    "zoom": (
                        float(viewer.zoom)
                        if isinstance(getattr(viewer, "zoom", None), (int, float))
                        else 1.0
                    ),
                    "pan_offset": (
                        list(viewer.pan_offset)
                        if isinstance(
                            getattr(viewer, "pan_offset", None), (list, tuple)
                        )
                        else [0.0, 0.0]
                    ),
                    "needs_recenter": bool(nr) if isinstance(nr, bool) else False,
                }

        # 2. Save Images & ViewStates
        for vs_id, vs in self.controller.view_states.items():
            is_overlay = getattr(
                self.controller.volumes[vs_id], "is_overlay_only", False
            )
            if is_overlay and vs_id in active_viewer_ids:
                is_overlay = False

            vol = self.controller.volumes[vs_id]

            # Extract Overlay Info
            overlay_info = None
            if (
                vs.display.overlay.image_id
                and vs.display.overlay.image_id in self.controller.volumes
            ):
                ov_vol = self.controller.volumes[vs.display.overlay.image_id]
                ov_path = ""
                if getattr(ov_vol, "file_paths", None) and len(ov_vol.file_paths) > 0:
                    ov_path = portable_path(ov_vol.file_paths[0])
                elif getattr(ov_vol, "path", None):
                    ov_path = portable_path(ov_vol.path)
                overlay_info = {
                    "id": vs.display.overlay.image_id,
                    "path": ov_path,
                    "mode": vs.display.overlay.mode,
                    "opacity": vs.display.overlay.opacity,
                    "colormap": self.controller.view_states[
                        vs.display.overlay.image_id
                    ].display.colormap,
                }

            # Extract ROIs Info: separate multi-label maps from independent ROIs
            rois_list = []
            label_maps_dict = {}
            for roi_id, roi_state in list(vs.rois.items()):
                if roi_id in self.controller.volumes:
                    r_vol = self.controller.volumes[roi_id]
                    if not r_vol.file_paths:
                        continue
                    is_spheroid = getattr(roi_state, "is_spheroid", False)
                    is_box = getattr(roi_state, "is_box", False)
                    is_rtstruct = getattr(roi_state, "rtstruct_info", None) is not None
                    stype = getattr(roi_state, "source_type", None)
                    smode = getattr(roi_state, "source_mode", None)
                    is_label_map = stype == "Label Map" or (
                        smode == "Target FG (val)"
                        and not is_spheroid
                        and not is_box
                        and not is_rtstruct
                    )

                    if is_label_map:
                        primary_path = r_vol.file_paths[0]
                        if primary_path not in label_maps_dict:
                            label_maps_dict[primary_path] = {
                                "path": portable_path(primary_path),
                                "labels": {},
                            }
                        lbl_val = (
                            int(roi_state.source_val)
                            if isinstance(roi_state.source_val, (int, float))
                            and float(roi_state.source_val).is_integer()
                            else roi_state.source_val
                        )
                        label_maps_dict[primary_path]["labels"][str(lbl_val)] = {
                            "name": roi_state.name,
                            "color": roi_state.color,
                            "opacity": roi_state.opacity,
                            "visible": roi_state.visible,
                            "is_contour": roi_state.is_contour,
                            "thickness": roi_state.thickness,
                        }
                    else:
                        rois_list.append(
                            {
                                "path": (
                                    portable_path(r_vol.file_paths)
                                    if len(r_vol.file_paths) > 1
                                    else portable_path(r_vol.file_paths[0])
                                ),
                                "state": roi_state.to_dict(),
                            }
                        )

            label_maps_list = list(label_maps_dict.values())

            # Extract Profiles Info
            profiles_list = [p.to_dict() for p in vs.profiles.values()]

            if getattr(vol, "file_paths", None):
                if len(vol.file_paths) > 1:
                    img_path = portable_path(vol.file_paths)
                elif len(vol.file_paths) == 1:
                    img_path = portable_path(vol.file_paths[0])
                else:
                    img_path = ""
            elif getattr(vol, "path", None):
                img_path = portable_path(vol.path)
            else:
                img_path = ""

            image_entry = {
                "path": img_path,
                "unit": getattr(vol, "unit", None),
                "unit_source": getattr(vol, "unit_source", None),
                "is_overlay_only": is_overlay,
                "sync_group": vs.sync_group,
                "sync_wl_group": getattr(vs, "sync_wl_group", 0),
                "display": vs.display.to_dict(),
                "camera": vs.camera.to_dict(),
                "extraction": vs.extraction.to_dict(),
                "dvf": vs.dvf.to_dict(),
                "overlay": overlay_info,
                "rois": rois_list,
                "label_maps": label_maps_list,
                "profiles": profiles_list,
            }

            if self.controller.gui:
                plugins_data = {}
                for plugin in self.controller.gui.plugins:
                    data = plugin.serialize_image_state(vs_id, context="workspace")
                    if data:
                        plugins_data[plugin.plugin_id] = data
                if plugins_data:
                    image_entry["plugins"] = plugins_data

            workspace["images"][vs_id] = image_entry

        write_json_atomic(filepath, workspace)

    def close_image(self, vs_id):
        with self.controller._state_lock:
            if vs_id in self.controller.view_states:

                # History
                self.controller.history.save_image_state(self.controller, vs_id)

                # State-Only: Wipe from layout dict
                for tag, current_id in self.controller.layout.items():
                    if current_id == vs_id:
                        self.controller.layout[tag] = None

                for other_id, other_vs in self.controller.view_states.items():
                    if other_vs.display.overlay.image_id == vs_id:
                        other_vs.set_overlay(None, None)
                        self.controller.update_all_viewers_of_image(other_id)

                name = self.controller.view_states[vs_id].volume.name

                # Delete ROIs from memory before deleting the view state ---
                for roi_id in list(self.controller.view_states[vs_id].rois.keys()):
                    if roi_id in self.controller.volumes:
                        del self.controller.volumes[roi_id]

                del self.controller.view_states[vs_id]
                del self.controller.volumes[vs_id]
                self.controller.profiles.clear_cache(vs_id)

                if self.controller.gui:
                    self.controller.gui.notify_plugins_image_removed(vs_id)

                # State-Only Fallback: Give empty viewers the next available image
                if self.controller.view_states:
                    first_vs_id = next(iter(self.controller.view_states))
                    for tag, current_id in self.controller.layout.items():
                        if current_id is None:
                            self.controller.layout[tag] = first_vs_id

                self.controller.ui_needs_refresh = True

                self.controller._set_status(f"Closed: {name}")
