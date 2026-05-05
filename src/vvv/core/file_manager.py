import os
import json
from vvv.maths.image import VolumeData
from vvv.core.view_state import ViewState
from vvv.utils import resolve_history_path_key


class FileManager:
    """Manages disk I/O: Loading images, parsing DICOMs, and saving Workspaces."""

    def __init__(self, controller):
        self.controller = controller

    def load_image(self, path, is_auto_overlay=False):

        img_id = str(self.controller.next_image_id)
        self.controller.next_image_id += 1
        vol = VolumeData(path)
        vs = ViewState(vol)

        # History
        history_entry = (
            self.controller.history.get_image_state(vol)
            if self.controller.use_history
            else None
        )

        if history_entry:
            vs.camera.from_dict(history_entry["camera"])
            vs.display.from_dict(history_entry["display"])

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

        self.controller.volumes[img_id] = vol
        self.controller.view_states[img_id] = vs

        # Auto-load overlay
        # Prevent infinite recursion with is_auto_overlay flag
        if history_entry and history_entry.get("overlay_path") and not is_auto_overlay:
            op_path = resolve_history_path_key(history_entry["overlay_path"])
            if os.path.exists(op_path):
                # Load the overlay quietly in the background
                op_id = self.load_image(op_path, is_auto_overlay=True)
                op_vol = self.controller.volumes[op_id]
                # Restore the link (opacity, mode, threshold are already restored in from_dict).
                vs.set_overlay(op_id, op_vol)

        if not is_auto_overlay:
            self.controller.add_recent_file(path)

        self.controller.ui_needs_refresh = True
        return img_id

    def scan_dicom_folder(self, folder_path, recursive=True):
        """Scans a folder for DICOM series and YIELDS progress updates."""
        import SimpleITK as sitk
        import pydicom
        import os

        if not os.path.exists(folder_path):
            yield (1.0, "Done", [])
            return

        _SCAN_TAGS = [
            (0x0008, 0x0008),  # Image Type
            (0x0008, 0x0020),  # Study Date
            (0x0008, 0x0030),  # Study Time
            (0x0008, 0x0060),  # Modality
            (0x0008, 0x0070),  # Manufacturer
            (0x0008, 0x1030),  # Study Description
            (0x0008, 0x103E),  # Series Description
            (0x0010, 0x0010),  # Patient Name
            (0x0010, 0x0020),  # Patient ID
            (0x0010, 0x0030),  # Patient Birth Date
            (0x0010, 0x0040),  # Patient Sex
            (0x0018, 0x0015),  # Body Part Examined
            (0x0018, 0x0031),  # Radiopharmaceutical
            (0x0018, 0x0050),  # Slice Thickness
            (0x0018, 0x1074),  # Radionuclide Total Dose
            (0x0020, 0x0011),  # Series Number
            (0x0028, 0x0008),  # Number of Frames
            (0x0028, 0x0010),  # Rows
            (0x0028, 0x0011),  # Columns
            (0x0028, 0x0030),  # Pixel Spacing
        ]

        def get_tag(ds, tag_tuple, default=""):
            elem = ds.get(tag_tuple)
            if elem is None:
                return default
            try:
                return str(elem.value).strip()
            except Exception:
                return default

        # Use a dictionary to group slices by Series UID across multiple folders!
        series_dict = {}
        search_dirs = (
            [x[0] for x in os.walk(folder_path, followlinks=True)]
            if recursive
            else [folder_path]
        )
        total_dirs = max(1, len(search_dirs))

        reader = sitk.ImageSeriesReader()

        for i, d in enumerate(search_dirs):
            # Yield progress to the UI Thread
            yield (i / total_dirs, os.path.basename(d))

            try:
                series_ids = reader.GetGDCMSeriesIDs(d)
                for sid in series_ids:
                    file_names = reader.GetGDCMSeriesFileNames(d, sid)
                    if not file_names:
                        continue

                    if sid in series_dict:
                        # Series is split across multiple folders -> just append the files.
                        series_dict[sid]["files"].extend(file_names)
                        continue

                    try:
                        ds = pydicom.dcmread(
                            file_names[0],
                            stop_before_pixels=True,
                            specific_tags=_SCAN_TAGS,
                        )
                    except Exception as e:
                        print(f"[vvv] DICOM metadata read failed for {file_names[0]}: {e}")
                        continue

                    # --- FORMAT DATE & TIME ---
                    d_str = get_tag(ds, (0x0008, 0x0020))
                    t_str = get_tag(ds, (0x0008, 0x0030))
                    fmt_date = d_str
                    if len(d_str) >= 8:
                        fmt_date = f"{d_str[0:4]}-{d_str[4:6]}-{d_str[6:8]}"
                        if len(t_str) >= 4:
                            fmt_date += f" {t_str[0:2]}:{t_str[2:4]}"

                    # --- DOSE ---
                    dose_str = ""
                    raw_dose = get_tag(ds, (0x0018, 0x1074))
                    if raw_dose:
                        try:
                            dose_str = f"{float(raw_dose) / 1e6:.2f} MBq"
                        except Exception:
                            dose_str = raw_dose

                    # --- PIXEL SPACING ---
                    spacing_str = "---"
                    ps_elem = ds.get((0x0028, 0x0030))
                    if ps_elem is not None:
                        try:
                            ps = ps_elem.value
                            spacing_str = f"{float(ps[0]):.2f} x {float(ps[1]):.2f}"
                        except Exception:
                            pass

                    rows = get_tag(ds, (0x0028, 0x0010), "0")
                    cols = get_tag(ds, (0x0028, 0x0011), "0")
                    try:
                        num_frames = int(get_tag(ds, (0x0028, 0x0008), "1"))
                    except Exception:
                        num_frames = 1

                    series_info = {
                        "id": sid,
                        "dir": d,
                        "files": list(file_names),
                        "patient_name": get_tag(ds, (0x0010, 0x0010), "Unknown"),
                        "study_desc": get_tag(ds, (0x0008, 0x1030), "Unknown"),
                        "series_desc": get_tag(ds, (0x0008, 0x103E), "Unknown"),
                        "modality": get_tag(ds, (0x0008, 0x0060), "Unknown"),
                        "date": fmt_date or "Unknown",
                        "spacing": spacing_str,
                        "tags": [],
                        "_base_rows": rows,
                        "_base_cols": cols,
                        "_base_frames": num_frames,
                    }

                    # --- CURATED MASTER TAG LIST ---
                    target_tags = [
                        ((0x0008, 0x0008), "Image Type"),
                        ((0x0008, 0x0020), "Study Date"),
                        ((0x0008, 0x0030), "Study Time"),
                        ((0x0008, 0x0060), "Modality"),
                        ((0x0008, 0x0070), "Manufacturer"),
                        ((0x0008, 0x1030), "Study Description"),
                        ((0x0008, 0x103E), "Series Description"),
                        ((0x0010, 0x0010), "Patient Name"),
                        ((0x0010, 0x0020), "Patient ID"),
                        ((0x0010, 0x0030), "Patient Birth Date"),
                        ((0x0010, 0x0040), "Patient Sex"),
                        ((0x0018, 0x0015), "Body Part Examined"),
                        ((0x0018, 0x0050), "Slice Thickness"),
                        ((0x0018, 0x1074), "Radionuclide Total Dose"),
                        ((0x0018, 0x0031), "Radiopharmaceutical"),
                        ((0x0020, 0x0011), "Series Number"),
                        ((0x0028, 0x0010), "Rows"),
                        ((0x0028, 0x0011), "Columns"),
                    ]

                    for tag_tuple, name in target_tags:
                        val = dose_str if tag_tuple == (0x0018, 0x1074) else get_tag(ds, tag_tuple)
                        if val:
                            if tag_tuple in ((0x0008, 0x0020), (0x0010, 0x0030)) and len(val) == 8:
                                val = f"{val[0:4]}-{val[4:6]}-{val[6:8]}"
                            elif tag_tuple == (0x0008, 0x0030) and len(val) >= 4:
                                val = (
                                    f"{val[0:2]}:{val[2:4]}:{val[4:6]}"
                                    if len(val) >= 6
                                    else f"{val[0:2]}:{val[2:4]}"
                                )
                            tag_str = f"{tag_tuple[0]:04x}|{tag_tuple[1]:04x}"
                            series_info["tags"].append((tag_str, name, val))

                    series_dict[sid] = series_info
            except Exception as e:
                print(f"[vvv] DICOM scan error in {d}: {e}")

        # Final post-processing to flatten the dictionary and fix the Z-Size
        found_series = []
        for sid, s in series_dict.items():
            rows = s.pop("_base_rows")
            cols = s.pop("_base_cols")
            z_header = s.pop("_base_frames")
            file_count = len(s["files"])

            # If there is only 1 file, trust the header frame count (Multi-frame DICOM).
            # Otherwise, use the total number of files found for this Series UID.
            z_dim = z_header if (z_header > 1 and file_count == 1) else file_count

            s["size"] = f"{cols} x {rows} x {z_dim}"
            found_series.append(s)

        yield (1.0, "Done", found_series)

    def save_workspace(self, filepath):
        workspace = {"version": 1.0, "viewers": {}, "images": {}}

        # for home as ~
        def portable_path(p):
            home = os.path.expanduser("~")
            abs_p = os.path.abspath(p)
            if abs_p.startswith(home):
                return abs_p.replace(home, "~", 1)
            return abs_p

        # Track all image IDs currently assigned to a viewer
        active_viewer_ids = set()

        # 1. Save Viewers
        for tag, viewer in self.controller.viewers.items():
            if viewer.image_id:
                active_viewer_ids.add(viewer.image_id)
                workspace["viewers"][tag] = {
                    "image_id": viewer.image_id,
                    "orientation": viewer.orientation.name,
                    "zoom": viewer.zoom,
                    "pan_offset": viewer.pan_offset,
                    "needs_recenter": getattr(viewer, "needs_recenter", False),
                }

        # 2. Save Images & ViewStates
        for vs_id, vs in list(self.controller.view_states.items()):
            # Never skip an image if it occupies a Viewer
            is_overlay = getattr(
                self.controller.volumes[vs_id], "is_overlay_only", False
            )
            if is_overlay and vs_id not in active_viewer_ids:
                continue

            vol = self.controller.volumes[vs_id]

            # Extract Overlay Info
            overlay_info = None
            if (
                vs.display.overlay_id
                and vs.display.overlay_id in self.controller.volumes
            ):
                ov_vol = self.controller.volumes[vs.display.overlay_id]
                overlay_info = {
                    "path": portable_path(ov_vol.file_paths[0]),
                    "mode": vs.display.overlay_mode,
                    "opacity": vs.display.overlay_opacity,
                    "colormap": self.controller.view_states[
                        vs.display.overlay_id
                    ].display.colormap,
                }

            # Extract ROIs Info
            rois_list = []
            for roi_id, roi_state in vs.rois.items():
                if roi_id in self.controller.volumes:
                    r_vol = self.controller.volumes[roi_id]
                    if r_vol.file_paths:
                        rois_list.append(
                            {
                                "path": portable_path(r_vol.file_paths[0]),
                                "state": roi_state.to_dict(),
                            }
                        )

            roi_filter = ""
            roi_sort_order = 0
            if self.controller.gui and hasattr(self.controller.gui, "roi_ui"):
                roi_filter = self.controller.gui.roi_ui.roi_filters.get(vs_id, "")
                roi_sort_order = self.controller.gui.roi_ui.roi_sort_orders.get(vs_id, 0)

            workspace["images"][vs_id] = {
                "path": portable_path(vol.file_paths[0]),
                "sync_group": vs.sync_group,
                "display": vs.display.to_dict(),
                "camera": vs.camera.to_dict(),
                "extraction": vs.extraction.to_dict(),
                "dvf": vs.dvf.to_dict(),
                "overlay": overlay_info,
                "rois": rois_list,
                "roi_filter": roi_filter,
                "roi_sort_order": roi_sort_order,
            }

        with open(filepath, "w") as f:
            json.dump(workspace, f, indent=4)

        if self.controller.gui:
            self.controller.gui.show_status_message(
                f"Saved Workspace: {os.path.basename(filepath)}"
            )

    def close_image(self, vs_id):
        if vs_id in self.controller.view_states:

            # History
            self.controller.history.save_image_state(self.controller, vs_id)

            # State-Only: Wipe from layout dict
            for tag, current_id in self.controller.layout.items():
                if current_id == vs_id:
                    self.controller.layout[tag] = None

            for other_id, other_vs in list(self.controller.view_states.items()):
                if other_vs.display.overlay_id == vs_id:
                    other_vs.set_overlay(None, None)
                    self.controller.update_all_viewers_of_image(other_id)

            name = self.controller.view_states[vs_id].volume.name

            # Delete ROIs from memory before deleting the view state ---
            for roi_id in list(self.controller.view_states[vs_id].rois.keys()):
                if roi_id in self.controller.volumes:
                    del self.controller.volumes[roi_id]

            del self.controller.view_states[vs_id]
            del self.controller.volumes[vs_id]

            # State-Only Fallback: Give empty viewers the next available image
            if self.controller.view_states:
                first_vs_id = next(iter(self.controller.view_states))
                for tag, current_id in self.controller.layout.items():
                    if current_id is None:
                        self.controller.layout[tag] = first_vs_id

            self.controller.ui_needs_refresh = True

            if self.controller.gui:
                self.controller.gui.show_status_message(f"Closed: {name}")
