import os
import json
from vvv.math.image import VolumeData
from vvv.state.view_state import ViewState
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
                # Restore the link! (opacity, mode, threshold are already restored in from_dict)
                vs.set_overlay(op_id, op_vol)

        if not is_auto_overlay:
            self.controller.add_recent_file(path)

        if self.controller.gui:
            self.controller.gui.refresh_image_list_ui()

        return img_id

    def scan_dicom_folder(self, folder_path, recursive=True):
        """Scans a folder for DICOM series and YIELDS progress updates."""
        import SimpleITK as sitk
        import os

        if not os.path.exists(folder_path):
            yield (1.0, "Done", [])
            return

        # Use a dictionary to group slices by Series UID across multiple folders!
        series_dict = {}
        search_dirs = (
            [x[0] for x in os.walk(folder_path, followlinks=True)]
            if recursive
            else [folder_path]
        )
        total_dirs = max(1, len(search_dirs))

        reader = sitk.ImageSeriesReader()
        file_reader = sitk.ImageFileReader()

        # Silence the C++ GDCM Warnings
        sitk.ProcessObject.SetGlobalWarningDisplay(False)

        try:
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
                            # Series is split across multiple folders -> just append the files!
                            series_dict[sid]["files"].extend(file_names)
                        else:
                            file_reader.SetFileName(file_names[0])
                            file_reader.ReadImageInformation()

                            def get_tag(tag, default=""):
                                return (
                                    file_reader.GetMetaData(tag).strip()
                                    if file_reader.HasMetaDataKey(tag)
                                    else default
                                )

                            # --- FORMAT DATE & TIME ---
                            d_str = get_tag("0008|0020")
                            t_str = get_tag("0008|0030")
                            fmt_date = d_str
                            if len(d_str) >= 8:
                                fmt_date = f"{d_str[0:4]}-{d_str[4:6]}-{d_str[6:8]}"
                                if len(t_str) >= 4:
                                    fmt_date += f" {t_str[0:2]}:{t_str[2:4]}"

                            # --- FUZZY SEARCH FOR INJECTED DOSE (Nested Sequences) ---
                            dose_str = ""
                            for k in file_reader.GetMetaDataKeys():
                                if "0018|1074" in k:  # Radionuclide Total Dose
                                    raw_dose = file_reader.GetMetaData(k).strip()
                                    try:
                                        dose_str = f"{float(raw_dose) / 1e6:.2f} MBq"
                                    except:
                                        dose_str = raw_dose
                                    break

                            size_tup = file_reader.GetSize()
                            x, y = size_tup[0], size_tup[1]
                            z = size_tup[2] if len(size_tup) > 2 else 1

                            series_info = {
                                "id": sid,
                                "dir": d,
                                "files": list(file_names),
                                "patient_name": get_tag("0010|0010", "Unknown"),
                                "study_desc": get_tag("0008|1030", "Unknown"),
                                "series_desc": get_tag("0008|103e", "Unknown"),
                                "modality": get_tag("0008|0060", "Unknown"),
                                "date": fmt_date if fmt_date else "Unknown",
                                "spacing": f"{file_reader.GetSpacing()[0]:.2f} x {file_reader.GetSpacing()[1]:.2f}",
                                "tags": [],
                                "_base_z": z,
                                "_base_x": x,
                                "_base_y": y,
                            }

                            # --- CURATED MASTER TAG LIST ---
                            target_tags = {
                                "0008|0008": "Image Type",
                                "0008|0020": "Study Date",
                                "0008|0030": "Study Time",
                                "0008|0060": "Modality",
                                "0008|0070": "Manufacturer",
                                "0008|1030": "Study Description",
                                "0008|103E": "Series Description",
                                "0010|0010": "Patient Name",
                                "0010|0020": "Patient ID",
                                "0010|0030": "Patient Birth Date",
                                "0010|0040": "Patient Sex",
                                "0018|0015": "Body Part Examined",
                                "0018|0050": "Slice Thickness",
                                "0018|1074": "Radionuclide Total Dose",
                                "0018|0031": "Radiopharmaceutical",
                                "0020|0011": "Series Number",
                                "0028|0010": "Rows",
                                "0028|0011": "Columns",
                            }

                            # Only append tags that actually contain data
                            for tag, name in target_tags.items():
                                val = dose_str if tag == "0018|1074" else get_tag(tag)

                                if val:
                                    # Format standalone dates/times cleanly
                                    if (
                                        tag in ("0008|0020", "0010|0030")
                                        and len(val) == 8
                                    ):
                                        val = f"{val[0:4]}-{val[4:6]}-{val[6:8]}"
                                    elif tag == "0008|0030" and len(val) >= 4:
                                        val = (
                                            f"{val[0:2]}:{val[2:4]}:{val[4:6]}"
                                            if len(val) >= 6
                                            else f"{val[0:2]}:{val[2:4]}"
                                        )

                                    series_info["tags"].append((tag, name, val))

                            series_dict[sid] = series_info
                except Exception as e:
                    pass
        finally:
            sitk.ProcessObject.SetGlobalWarningDisplay(True)

        # Final post-processing to flatten the dictionary and fix the Z-Size
        found_series = []
        for sid, s in series_dict.items():
            x, y, z_header = s.pop("_base_x"), s.pop("_base_y"), s.pop("_base_z")
            file_count = len(s["files"])

            # If there is only 1 file, trust the header Z size (Multi-frame DICOM).
            # Otherwise, use the total number of files found for this Series UID.
            z_dim = z_header if (z_header > 1 and file_count == 1) else file_count

            s["size"] = f"{x} x {y} x {z_dim}"
            found_series.append(s)

        yield (1.0, "Done", found_series)

    def save_workspace(self, filepath):
        workspace = {"viewers": {}, "images": {}}

        # for home as ~
        def portable_path(p):
            home = os.path.expanduser("~")
            abs_p = os.path.abspath(p)
            if abs_p.startswith(home):
                return abs_p.replace(home, "~", 1)
            return abs_p

        # 1. Save Viewers
        for tag, viewer in self.controller.viewers.items():
            if viewer.image_id:
                workspace["viewers"][tag] = {
                    "image_id": viewer.image_id,
                    "orientation": viewer.orientation.name,
                    "zoom": viewer.zoom,
                    "pan_offset": viewer.pan_offset,
                    "needs_recenter": getattr(viewer, "needs_recenter", False),
                }

        # 2. Save Images & ViewStates
        for vs_id, vs in self.controller.view_states.items():
            if getattr(self.controller.volumes[vs_id], "is_overlay_only", False):
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
                    "path": portable_path(ov_vol.file_paths[0]),  # <--- UPDATED
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
                                "path": portable_path(
                                    r_vol.file_paths[0]
                                ),  # <--- UPDATED
                                "state": roi_state.to_dict(),
                            }
                        )

            workspace["images"][vs_id] = {
                "path": portable_path(vol.file_paths[0]),  # <--- UPDATED
                "sync_group": vs.sync_group,
                "display": vs.display.to_dict(),
                "camera": vs.camera.to_dict(),
                "overlay": overlay_info,
                "rois": rois_list,
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

            for viewer in self.controller.viewers.values():
                if viewer.image_id == vs_id:
                    viewer.drop_image()

            for other_id, other_vs in self.controller.view_states.items():
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

            if self.controller.view_states:
                first_vs_id = next(iter(self.controller.view_states))
                for viewer in self.controller.viewers.values():
                    if viewer.image_id is None:
                        viewer.set_image(first_vs_id)

            if self.controller.gui:
                self.controller.gui.refresh_image_list_ui()
                self.controller.gui.refresh_rois_ui()
                if self.controller.gui.context_viewer:
                    self.controller.gui.update_sidebar_info(
                        self.controller.gui.context_viewer
                    )
                self.controller.gui.show_status_message(f"Closed: {name}")
