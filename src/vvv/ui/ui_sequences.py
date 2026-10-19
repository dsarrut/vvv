import os
import dearpygui.dearpygui as dpg
import numpy as np
from vvv.config import ROI_COLORS
from vvv.ui.ui_notifications import show_loading_modal, hide_loading_modal
import logging

logger = logging.getLogger(__name__)


def _apply_default_layout(gui, controller, img_id):
    target_tag = gui.context_viewer.tag if gui.context_viewer else "V1"
    controller.layout[target_tag] = img_id

    target_viewer = controller.viewers[target_tag]
    target_viewer.set_orientation(
        controller.view_states[img_id].camera.last_orientation
    )

    if None in controller.layout.values():
        controller.default_viewers_orientation()
        for tag, current_id in controller.layout.items():
            if current_id is None:
                controller.layout[tag] = img_id

    same_image_viewers = [
        v.tag for v in controller.viewers.values() if v.image_id == img_id
    ]
    if same_image_viewers:
        controller.sync.propagate_ppm(same_image_viewers)

    gui.set_context_viewer(target_viewer)
    controller.ui_needs_refresh = True


def _show_message_and_wait(gui, title, message):
    """[generator] Show the message modal and yield until the user closes it."""
    gui.show_message(title, message)
    while dpg.does_item_exist("generic_message_modal"):
        yield


def _handle_warnings_and_cleanup(gui, warnings, title, message):
    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")
    yield
    if warnings:
        yield from _show_message_and_wait(
            gui, title, f"{message}\n\n" + "\n".join(warnings)
        )


def _warn_rois_outside_fov(gui, controller, rois):
    """[generator] Warn (modal) about the ROIs ({roi_id: ROIState}) lying
    partially or fully outside their image field of view."""
    outside = [
        state.name
        for r_id, state in rois.items()
        if getattr(controller.volumes.get(r_id), "is_outside", False)
    ]
    if not outside:
        return
    yield
    if len(outside) == 1:
        msg = f"Warning: The loaded ROI '{outside[0]}' lies partially or fully outside the image field of view (FOV)."
    else:
        names_str = ", ".join(f"'{n}'" for n in outside)
        msg = f"Warning: The loaded ROIs {names_str} lie partially or fully outside the image field of view (FOV)."
    yield from _show_message_and_wait(gui, "ROI Warning", msg)


def _run_parallel(jobs, work, on_done, max_workers=4, poll_s=0.01):
    """[generator, main thread] Run work(job) for each job on a thread pool.

    on_done(job, future) runs on the main thread as each job finishes, in
    submission order within a frame; future.result() re-raises the worker's
    exception. Yields once per frame while jobs are running, so DearPyGui
    keeps rendering; waits at most poll_s per frame.
    """
    import concurrent.futures

    if not jobs:
        return
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(len(jobs), max_workers)
    ) as executor:
        running = {executor.submit(work, job): job for job in jobs}
        while running:
            done, _ = concurrent.futures.wait(
                running, timeout=poll_s, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in [f for f in running if f in done]:
                on_done(running.pop(future), future)
            if running:
                yield


def _compute_label_bboxes(img, labels=None):
    import SimpleITK as sitk

    bboxes = {}
    try:
        stats = sitk.LabelShapeStatisticsImageFilter()
        cast_img = sitk.Cast(img, sitk.sitkUInt32)
        stats.Execute(cast_img)
        target_labels = labels if labels is not None else stats.GetLabels()
        for val in target_labels:
            val_int = int(val)
            if stats.HasLabel(val_int):
                bboxes[val_int] = stats.GetBoundingBox(val_int)
    except Exception:
        pass
    return bboxes


def load_single_image_sequence(gui, controller, file_path):

    is_4d = file_path.startswith("4D:")
    display_name = "4D Sequence" if is_4d else os.path.basename(file_path)

    # Start the progress bar at 20% to show it is active
    show_loading_modal("Loading image...", display_name, progress=0.2)

    for _ in range(3):
        yield

    # Non-blocking: DearPyGui keeps rendering while SimpleITK reads the file
    result = {}

    def on_done(path, future):
        try:
            result["img_id"] = controller.file.register_image(future.result())
        except Exception as e:
            result["error"] = e

    yield from _run_parallel([file_path], controller.file.read_image, on_done)
    img_id, load_error = result.get("img_id"), result.get("error")

    if load_error:
        if dpg.does_item_exist("loading_modal"):
            dpg.delete_item("loading_modal")
        yield
        yield from _show_message_and_wait(
            gui,
            "File Load Error",
            f"Failed to load image:\n{display_name}\n\n{load_error}",
        )
        hide_loading_modal()
        return

    show_loading_modal(
        "Loading image...", "Applying synchronization and layouts...", progress=1.0
    )
    yield

    _apply_default_layout(gui, controller, img_id)
    yield from _handle_warnings_and_cleanup(gui, [], "", "")


def load_batch_images_sequence(gui, controller, file_paths):
    import pydicom
    from collections import defaultdict

    # Group individual DICOM files by Series Instance UID
    dicom_groups = defaultdict(list)
    non_dicom_paths = []

    for path in file_paths:
        if isinstance(path, (list, tuple)):
            # Already a group (e.g. from DICOM Browser or 4D sequence)
            non_dicom_paths.append(list(path))
            continue

        is_dicom = False
        try:
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    f.seek(128)
                    if f.read(4) == b"DICM":
                        is_dicom = True
        except Exception:
            pass

        if is_dicom:
            try:
                ds = pydicom.dcmread(path, stop_before_pixels=True)
                series_uid = getattr(ds, "SeriesInstanceUID", None)
                if series_uid:
                    dicom_groups[series_uid].append(path)
                else:
                    non_dicom_paths.append(path)
            except Exception:
                non_dicom_paths.append(path)
        else:
            non_dicom_paths.append(path)

    # Helper function to sort DICOM files geometrically
    def sort_dicom_files(files):
        file_sort_keys = []
        for f in files:
            try:
                ds = pydicom.dcmread(f, stop_before_pixels=True)
                ipp = getattr(ds, "ImagePositionPatient", None)
                if ipp is not None and len(ipp) == 3:
                    iop = getattr(ds, "ImageOrientationPatient", None)
                    if iop is not None and len(iop) == 6:
                        normal = [
                            iop[1] * iop[5] - iop[2] * iop[4],
                            iop[2] * iop[3] - iop[0] * iop[5],
                            iop[0] * iop[4] - iop[1] * iop[3],
                        ]
                        dist = sum(n * p for n, p in zip(normal, ipp))
                        file_sort_keys.append((dist, f))
                    else:
                        file_sort_keys.append((ipp[2], f))
                else:
                    inst = getattr(ds, "InstanceNumber", 0)
                    file_sort_keys.append((inst, f))
            except Exception:
                file_sort_keys.append((0, f))
        file_sort_keys.sort(key=lambda x: (x[0], x[1]))
        return [x[1] for x in file_sort_keys]

    # Process and sort each DICOM group
    clean_paths = []
    for series_uid, files in dicom_groups.items():
        if len(files) > 1:
            clean_paths.append(sort_dicom_files(files))
        else:
            clean_paths.extend(files)
    clean_paths.extend(non_dicom_paths)

    total_files = len(clean_paths)
    warnings = []

    display_name = f"Loading {total_files} images..."
    show_loading_modal("Loading image...", display_name)
    # Yield multiple times to guarantee the OS paints the window
    for _ in range(3):
        yield

    loaded_ids = []

    # --- THE PARALLEL LOADER & REAL PROGRESS BAR ---
    done_count = [0]

    def on_done(path, future):
        try:
            loaded_ids.append(controller.file.register_image(future.result()))
        except Exception as e:
            warnings.append(f"- Failed: {e}")
        done_count[0] += 1
        show_loading_modal(
            "Loading image...",
            f"Loaded ({done_count[0]}/{total_files})",
            progress=(done_count[0] / total_files),
        )

    yield from _run_parallel(clean_paths, controller.file.read_image, on_done)

    show_loading_modal("Loading image...", "Applying layouts...", progress=1.0)
    yield

    if loaded_ids:
        _apply_default_layout(gui, controller, loaded_ids[0])

    yield from _handle_warnings_and_cleanup(
        gui, warnings, "Image Load Warning", "Some images failed to load:"
    )


def load_batch_rois_sequence(
    gui,
    controller,
    base_image_id,
    file_paths,
    roi_type="Binary Mask",
    mode="Ignore BG (val)",
    val=0.0,
):
    import os

    # 1. Filter valid paths BEFORE initializing the UI so the total count is accurate
    valid_paths = [p for p in file_paths if os.path.exists(p)]
    total_files = len(valid_paths)

    if total_files == 0:
        gui.show_status_message("No valid ROI files found.")
        return

    warnings = []
    show_loading_modal("Loading ROIs...", f"Preparing {total_files} file(s)...")

    # Yield multiple times to guarantee the OS paints the window
    for _ in range(3):
        yield

    vs = controller.view_states[base_image_id]
    color_idx = len(vs.rois)
    initial_roi_ids = set(vs.rois.keys())

    # 2. Unified Loading Loop
    for i, path in enumerate(valid_paths, 1):
        filename = os.path.basename(path)
        prefix = "Label Map" if roi_type == "Label Map" else "ROI"

        # Update UI Frame
        show_loading_modal(
            "Loading ROIs...",
            f"Loading {prefix} ({i}/{total_files}):\n{filename}",
            progress=(i / total_files),
        )
        yield  # Flush UI to screen

        # Execute Math
        try:
            if roi_type == "Binary Mask":
                color = ROI_COLORS[color_idx % len(ROI_COLORS)]
                controller.roi.load_binary_mask(
                    base_image_id,
                    path,
                    name=None,
                    color=color,
                    mode=mode,
                    target_val=val,
                )
                color_idx += 1
            elif roi_type == "Label Map":
                pass  # This is now handled by load_label_map_sequence
        except Exception as e:
            warnings.append(f"- {filename}: {e}")

    # 3. Finalize & Cleanup
    show_loading_modal("Loading ROIs...", "Applying changes...", progress=1.0)
    yield

    if vs.rois:
        gui.active_roi_id = list(vs.rois.keys())[-1]

    controller.ui_needs_refresh = True
    controller.update_all_viewers_of_image(base_image_id)

    yield from _handle_warnings_and_cleanup(
        gui, warnings, "ROI Import Warning", "Some ROIs were skipped:"
    )

    # Check for out-of-bounds ROIs
    new_roi_ids = set(vs.rois.keys()) - initial_roi_ids
    yield from _warn_rois_outside_fov(
        gui, controller, {r: vs.rois[r] for r in new_roi_ids}
    )


def _parse_label_map_json(raw_dict):
    """Parses a label-map sidecar JSON into (label_dict, color_dict).

    Supports the legacy flat format {"<id>": "<name>"} and an extended
    per-label format {"<id>": {"name": "...", "color": [r, g, b]}}; the two
    may be mixed within the same file. Malformed entries are skipped so one
    bad entry doesn't discard the whole file.
    Supports:
    - Flat dict: {"1": "name", ...}
    - Nested struct dict: {"1": {"name": "...", "color": [r, g, b]}, ...}
    - Separate dicts: {"labels": {"1": "name"}, "colors": {"1": [r, g, b]}}
    - List of dicts: [{"label": 1, "name": "...", "color": ...}, ...]
    - Colors as [0-255], float [0.0-1.0], RGBA, or hex string "#RRGGBB".
    Malformed entries are skipped gracefully.
    """
    label_dict = {}
    color_dict = {}

    if not isinstance(raw_dict, (dict, list)):
        return label_dict, color_dict

    def _parse_color(c):
        if isinstance(c, str):
            c_str = c.strip().lstrip("#")
            if len(c_str) in (6, 8):
                try:
                    r = int(c_str[0:2], 16)
                    g = int(c_str[2:4], 16)
                    b = int(c_str[4:6], 16)
                    return [r, g, b]
                except ValueError:
                    pass
        elif isinstance(c, (list, tuple)) and len(c) >= 3:
            try:
                from vvv.ui.ui_components import normalize_rgba_to_int

                norm = normalize_rgba_to_int(c)
                return norm[:3]
            except Exception:
                pass
        return None

    # Handle separate "colors" / "colormap" / "palette" dict if present
    if isinstance(raw_dict, dict):
        colors_section = (
            raw_dict.get("colors")
            or raw_dict.get("colormap")
            or raw_dict.get("palette")
        )
        if isinstance(colors_section, dict):
            for ck, cv in colors_section.items():
                parsed_c = _parse_color(cv)
                if parsed_c is not None:
                    try:
                        color_dict[int(ck)] = parsed_c
                    except (TypeError, ValueError):
                        pass

        # If there is a sub-dictionary for labels / names / structures / rois
        for key in ("labels", "names", "structures", "rois"):
            if key in raw_dict and isinstance(raw_dict[key], (dict, list)):
                raw_dict = raw_dict[key]
                break

    if isinstance(raw_dict, list):
        dict_from_list = {}
        for item in raw_dict:
            if isinstance(item, dict):
                lbl = (
                    item.get("label")
                    if item.get("label") is not None
                    else (
                        item.get("id")
                        if item.get("id") is not None
                        else (
                            item.get("value")
                            if item.get("value") is not None
                            else item.get("val")
                        )
                    )
                )
                if lbl is not None:
                    dict_from_list[str(lbl)] = item
        raw_dict = dict_from_list

    if not isinstance(raw_dict, dict):
        return label_dict, color_dict

    for k, v in raw_dict.items():
        try:
            val_int = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict):
            if "name" in v:
                label_dict[val_int] = str(v["name"])
            elif "label" in v and isinstance(v["label"], str):
                label_dict[val_int] = str(v["label"])
            color = v.get("color")
            if isinstance(color, (list, tuple)) and len(color) >= 3:
                try:
                    color_dict[val_int] = [int(c) for c in color[:3]]
                except (TypeError, ValueError):
                    pass
            if color is None:
                color = v.get("rgb")
            if color is None:
                color = v.get("rgba")
            parsed_c = _parse_color(color)
            if parsed_c is not None:
                color_dict[val_int] = parsed_c
        else:
            label_dict[val_int] = str(v)
    return label_dict, color_dict


def _rasterize_and_load_labels(
    gui,
    controller,
    base_image_id,
    filepath,
    unique_labels,
    label_dict,
    saved_preferences=None,
    color_dict=None,
):
    """[generator] Extract each label of a label map as an ROI, in parallel,
    then register them all (main thread). Updates the loading modal."""
    import SimpleITK as sitk

    vs = controller.view_states[base_image_id]
    total_lbls = len(unique_labels)
    base_name = controller.roi._clean_roi_name(filepath)
    color_dict = color_dict or {}

    # --- Read the full image ONCE ---
    img = sitk.ReadImage(filepath)
    data = sitk.GetArrayViewFromImage(img)

    # --- PRE-EXTRACT BOUNDING BOXES FOR THREAD SAFETY ---
    bboxes = _compute_label_bboxes(img, unique_labels)

    jobs = []
    for i, val in enumerate(unique_labels):
        val_int = int(val)
        custom_name = label_dict.get(val_int, f"{base_name} - Lbl {val_int}")
        color = color_dict.get(val_int) or ROI_COLORS[(val_int - 1) % len(ROI_COLORS)]
        jobs.append((i, val_int, custom_name, color, bboxes.get(val_int)))

    def extract(job):
        # worker: compute only, registered below on the main thread
        _, val_int, custom_name, color, bbox = job
        return controller.roi.extract_label_from_image(
            base_image_id, filepath, img, data, val_int, custom_name, color, bbox,
            defer=True,
        )

    # Register all ROIs at the end: each registration re-renders the
    # viewers with every ROI so far (150 labels = 150 ever slower frames).
    pending = [None] * total_lbls
    done_count = [0]

    def on_done(job, future):
        pending[job[0]] = future.result()
        done_count[0] += 1
        show_loading_modal(
            "Loading Label Map...",
            f"Rasterizing Labels ({done_count[0]}/{total_lbls})...",
            progress=(done_count[0] / total_lbls),
        )

    yield from _run_parallel(jobs, extract, on_done)

    for p in pending:
        res = controller.roi.register_roi(p)
        if res and saved_preferences and res in vs.rois:
            rstate = vs.rois[res]
            lbl_val = int(rstate.source_val)
            if lbl_val in saved_preferences:
                prefs = saved_preferences[lbl_val]
                for k, v in prefs.items():
                    if k == "color" and lbl_val in color_dict:
                        # Prefer the color read from the newly reloaded JSON file
                        continue
                    setattr(rstate, k, v)


def load_label_map_sequence(
    gui, controller, base_image_id, filepath, saved_preferences=None
):
    import os
    import json
    import time
    import numpy as np
    import SimpleITK as sitk
    from vvv.maths.image import VolumeData
    from vvv.core.roi_manager import ROIState
    from vvv.config import ROI_COLORS

    if isinstance(filepath, (list, tuple)):
        filepath = filepath[0]

    if not isinstance(filepath, str) or not os.path.exists(filepath):
        gui.show_status_message("Invalid label map file.", color=[255, 100, 100])
        return

    # Give DearPyGui 3 frames to clear any previous modals
    for _ in range(3):
        yield

    show_loading_modal(
        "Loading Label Map...", f"Reading file:\n{os.path.basename(filepath)}"
    )
    # Yield multiple times to guarantee the OS paints the window
    # before the main thread gets blocked by sitk.ReadImage!
    for _ in range(3):
        yield

    time.sleep(0.3)  # Artificial delay so the user actually sees the modal!

    # 1. Get unique labels
    try:
        img = sitk.ReadImage(filepath)
        data = sitk.GetArrayViewFromImage(img)
        unique_labels = np.unique(data)
        unique_labels = unique_labels[unique_labels != 0]
    except Exception as e:
        hide_loading_modal()
        yield
        gui.show_message("Error", f"Failed to read label map:\n{e}")
        return

    if len(unique_labels) == 0:
        hide_loading_modal()
        yield
        gui.show_message(
            "No Labels Found", "The selected image contains no non-zero labels."
        )
        return

    # 2. Confirmation dialog
    if len(unique_labels) > 200:
        hide_loading_modal()
        yield

        modal_tag = "label_map_confirm_modal"
        confirmed = [False]  # Use a list to be mutable inside closures

        def on_confirm(s, a, u):
            u[0] = True
            dpg.delete_item(modal_tag)

        def on_cancel(s, a, u):
            dpg.delete_item(modal_tag)

        with dpg.window(
            tag=modal_tag,
            modal=True,
            show=True,
            label="Large Number of Labels",
            no_collapse=True,
            width=450,
        ):
            dpg.add_text(f"This image contains {len(unique_labels)} unique labels.")
            dpg.add_text(
                "Loading them all may take some time. Do you want to continue?"
            )
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=100)
                dpg.add_button(
                    label="Continue",
                    width=100,
                    callback=on_confirm,
                    user_data=confirmed,
                )
                dpg.add_button(label="Cancel", width=100, callback=on_cancel)

        # Wait for user input
        while dpg.does_item_exist(modal_tag):
            yield

        if not confirmed[0]:
            return

        # Let DPG completely destroy the confirm modal before spawning the loading modal!
        for _ in range(3):
            yield

    # 3. Load each label as a separate ROI
    vs = controller.view_states[base_image_id]
    total_lbls = len(unique_labels)
    initial_roi_ids = set(vs.rois.keys())

    # Re-initialize the loading modal safely
    show_loading_modal("Loading Label Map...", f"Processing {total_lbls} labels...")
    for _ in range(3):
        yield

    # Attempt to load sidecar JSON for label names
    if filepath.lower().endswith(".nii.gz"):
        json_path = filepath[:-7] + ".json"
    else:
        json_path = os.path.splitext(filepath)[0] + ".json"

    label_dict = {}
    color_dict = {}
    if os.path.exists(json_path):
        try:
            import json

            with open(json_path, "r") as f:
                raw_dict = json.load(f)
                label_dict, color_dict = _parse_label_map_json(raw_dict)
        except Exception as e:
            logger.warning(f"Failed to parse {json_path}: {e}")

    yield from _rasterize_and_load_labels(
        gui,
        controller,
        base_image_id,
        filepath,
        unique_labels,
        label_dict,
        saved_preferences,
        color_dict,
    )
    yield

    # Finalize
    yield from _handle_warnings_and_cleanup(gui, [], "", "")

    if vs.rois:
        gui.active_roi_id = list(vs.rois.keys())[-1]

    vs.is_data_dirty = True
    vs.is_geometry_dirty = True

    controller.ui_needs_refresh = True
    controller.update_all_viewers_of_image(base_image_id)

    # Check for out-of-bounds ROIs
    new_roi_ids = set(vs.rois.keys()) - initial_roi_ids
    yield from _warn_rois_outside_fov(
        gui, controller, {r: vs.rois[r] for r in new_roi_ids}
    )


def load_rtstruct_sequence(
    gui, controller, base_image_id, filepath, selected_rois, ds=None
):
    import os

    # Give DearPyGui 3 frames to completely destroy the selection modal
    # before we attempt to open the loading modal. Otherwise, DPG swallows it!
    for _ in range(3):
        yield

    total_rois = len(selected_rois)
    show_loading_modal("Loading RT-Struct...", f"Preparing {total_rois} ROI(s)...")

    yield

    warnings = []
    vs = controller.view_states[base_image_id]
    initial_roi_ids = set(vs.rois.keys())

    if ds is None:
        try:
            import pydicom

            ds = pydicom.dcmread(filepath, force=True)
        except Exception as e:
            hide_loading_modal()
            yield
            gui.show_message("Error", f"Failed to read DICOM:\n{e}")
            return

    for i, r_info in enumerate(selected_rois, 1):
        name = r_info.get("name", "Unknown")
        show_loading_modal(
            "Loading RT-Struct...",
            f"Rasterizing ROI ({i}/{total_rois}):\n{name}",
            progress=((i - 1) / total_rois),
        )
        yield  # Flush UI to screen

        try:
            controller.roi.load_rtstruct_roi(base_image_id, filepath, r_info, ds=ds)
        except Exception as e:
            warnings.append(f"- {name}: {e}")

    show_loading_modal("Loading RT-Struct...", "Applying changes...", progress=1.0)
    yield

    if vs.rois:
        gui.active_roi_id = list(vs.rois.keys())[-1]

    controller.ui_needs_refresh = True
    controller.update_all_viewers_of_image(base_image_id)

    yield from _handle_warnings_and_cleanup(
        gui, warnings, "RT-Struct Import Warning", "Some ROIs failed to load:"
    )

    # Check for out-of-bounds ROIs
    new_roi_ids = set(vs.rois.keys()) - initial_roi_ids
    yield from _warn_rois_outside_fov(
        gui, controller, {r: vs.rois[r] for r in new_roi_ids}
    )


def load_series_and_rtstruct_sequence(
    gui, controller, series_files, rtstruct_filepath
):
    import time

    show_loading_modal("Loading reference image...", "Reading DICOM files...")
    for _ in range(3):
        yield

    loaded_id = None
    try:
        loaded_id = controller.file.load_image(series_files)
    except Exception as e:
        hide_loading_modal()
        yield
        gui.show_message("Error", f"Failed to load reference image:\n{e}")
        return

    show_loading_modal(
        "Loading reference image...", "Applying layouts...", progress=1.0
    )
    yield

    if loaded_id:
        _apply_default_layout(gui, controller, loaded_id)

    yield from _handle_warnings_and_cleanup(gui, [], "", "")

    # Now show the RT-Struct selection modal targeting the loaded image
    roi_plugin = next(
        (
            p
            for p in getattr(gui, "plugins", [])
            if getattr(p, "plugin_id", "") == "roi_plugin"
        ),
        None,
    )
    if roi_plugin and hasattr(roi_plugin, "_ui"):
        try:
            res = controller.roi.parse_rtstruct(
                rtstruct_filepath, return_ds=True
            )
            if isinstance(res, tuple) and len(res) == 2:
                rois_info, ds = res
            else:
                rois_info, ds = res, None
            roi_plugin._ui.show_rtstruct_selection_modal(
                rtstruct_filepath, rois_info, target_image_id=loaded_id, ds=ds
            )
        except Exception as e:
            gui.show_message("Error", f"Failed to parse RT-Struct:\n{e}")


def _gather_workspace_rois(controller, ws, id_map, warnings, resolve_workspace_path):
    """List the ROIs of a workspace to load: [{"new_id", "path", "state"}].

    Label maps give one entry per label present in the file on disk (the
    workspace only supplies the user preferences). Missing files are added
    to warnings.
    """
    import json

    # 1. Gather all valid ROIs first to calculate total progress
    valid_rois_to_load = []
    for old_id, img_data in ws.get("images", {}).items():
        if old_id in id_map:
            new_id = id_map[old_id]
            for roi_data in img_data.get("rois", []):
                raw_r_path = roi_data.get("path", "")
                if raw_r_path:
                    if isinstance(raw_r_path, list):
                        resolved_list = resolve_workspace_path(raw_r_path)
                        p0 = resolved_list[0]
                        if os.path.exists(p0):
                            valid_rois_to_load.append(
                                {
                                    "new_id": new_id,
                                    "path": tuple(resolved_list),
                                    "state": roi_data.get("state", {}),
                                }
                            )
                        else:
                            warnings.append(
                                f"Missing ROI DICOM: {os.path.basename(raw_r_path[0])}"
                            )
                    elif isinstance(raw_r_path, str) and raw_r_path.startswith("4D:"):
                        warnings.append("4D ROIs are not supported.")
                    else:
                        r_path = resolve_workspace_path(raw_r_path)
                        if os.path.exists(r_path):
                            valid_rois_to_load.append(
                                {
                                    "new_id": new_id,
                                    "path": r_path,
                                    "state": roi_data.get("state", {}),
                                }
                            )
            for lm_data in img_data.get("label_maps", []):
                raw_lm_path = lm_data.get("path", "")
                labels_dict = lm_data.get("labels", {})
                if raw_lm_path:
                    if isinstance(raw_lm_path, list):
                        resolved_path = tuple(resolve_workspace_path(raw_lm_path))
                        p0 = resolved_path[0]
                    else:
                        resolved_path = resolve_workspace_path(raw_lm_path)
                        p0 = resolved_path

                    if os.path.exists(p0):
                        # Sidecar JSON check
                        sidecar_dict = {}
                        base_p = p0[:-3] if p0.lower().endswith(".gz") else p0
                        json_candidate = os.path.splitext(base_p)[0] + ".json"
                        if os.path.exists(json_candidate):
                            try:
                                with open(json_candidate, "r") as jf:
                                    sidecar_dict = json.load(jf)
                            except Exception:
                                sidecar_dict = {}

                        sidecar_labels, sidecar_colors = _parse_label_map_json(
                            sidecar_dict
                        )

                        base_name = controller.roi._clean_roi_name(p0)
                        expected_labels = set(labels_dict.keys()) | set(
                            str(k) for k in sidecar_labels.keys()
                        )
                        valid_rois_to_load.append(
                            {
                                "new_id": new_id,
                                "path": resolved_path,
                                "is_label_map": True,
                                "labels_dict": labels_dict,
                                "sidecar_labels": sidecar_labels,
                                "sidecar_colors": sidecar_colors,
                                "base_name": base_name,
                                "expected_count": max(1, len(expected_labels)),
                                "state": {
                                    "source_mode": "Target FG (val)",
                                    "source_type": "Label Map",
                                    "name": base_name,
                                },
                            }
                        )
                    else:
                        warnings.append(f"Missing Label Map: {os.path.basename(p0)}")

    return valid_rois_to_load


def _load_workspace_roi_file(controller, r_path, tasks):
    """Worker: read one ROI file (mask, label map or RT-Struct) and compute
    the ROIs of its tasks; returns [(task, pending, error)], registered on
    the main thread."""
    import SimpleITK as sitk

    results = []
    is_rtstruct = any(t["state"].get("rtstruct_info") for t in tasks)

    actual_path = list(r_path) if isinstance(r_path, tuple) else r_path
    path_for_print = (
        os.path.basename(actual_path[0])
        if isinstance(actual_path, list)
        else os.path.basename(actual_path)
    )

    if is_rtstruct:
        try:
            import pydicom

            rt_path = (
                actual_path[0] if isinstance(actual_path, list) else actual_path
            )
            ds = pydicom.dcmread(rt_path, force=True)
            for task in tasks:
                try:
                    pending = controller.roi.load_rtstruct_roi(
                        task["new_id"],
                        rt_path,
                        task["state"]["rtstruct_info"],
                        ds=ds,
                        defer=True,
                    )
                    results.append((task, pending, None))
                except Exception as e:
                    results.append(
                        (
                            task,
                            None,
                            f"- Failed to load {task['state'].get('name')}: {e}",
                        )
                    )
        except Exception as e:
            for task in tasks:
                results.append(
                    (
                        task,
                        None,
                        f"- Failed to read {path_for_print}: {e}",
                    )
                )
    else:
        try:
            read_path = actual_path
            if isinstance(read_path, (list, tuple)):
                read_path = [
                    p for p in read_path if not p.lower().endswith(".json")
                ]
                if len(read_path) == 1:
                    read_path = read_path[0]
            img = sitk.ReadImage(read_path)
            data = sitk.GetArrayViewFromImage(img)
            bboxes = None

            # Fast-path: Only compute heavy bboxes if a label map extraction is actually requested!
            if any(
                t.get("is_label_map")
                or t["state"].get("source_mode") == "Target FG (val)"
                for t in tasks
            ):
                bboxes = _compute_label_bboxes(img)

            for task in tasks:
                if task.get("is_label_map"):
                    labels_dict = task.get("labels_dict", {})
                    sidecar_labels = task.get("sidecar_labels", {})
                    sidecar_colors = task.get("sidecar_colors", {})
                    base_name = task.get("base_name") or controller.roi._clean_roi_name(path_for_print)
                    new_id = task["new_id"]

                    # The file on disk is the source of truth for which labels exist.
                    file_labels = sorted(bboxes.keys()) if bboxes else []
                    if not file_labels and bboxes is not None:
                        unique_vals = np.unique(data)
                        file_labels = [int(v) for v in unique_vals if v != 0]

                    for val_int in file_labels:
                        val_str = str(val_int)
                        l_info = labels_dict.get(val_str) or labels_dict.get(str(float(val_int)))

                        if isinstance(l_info, dict):
                            name = (
                                sidecar_labels.get(val_int)
                                or l_info.get("name")
                                or f"Label {val_int}"
                            )
                            raw_col = sidecar_colors.get(val_int) or l_info.get("color")
                            opacity = l_info.get("opacity", 0.5)
                            visible = l_info.get("visible", True)
                            is_contour = l_info.get("is_contour", False)
                            thickness = l_info.get("thickness", 1.0)
                        else:
                            name = sidecar_labels.get(val_int) or (
                                str(l_info) if l_info else f"{base_name} - Lbl {val_int}"
                            )
                            raw_col = sidecar_colors.get(val_int) or ROI_COLORS[(val_int - 1) % len(ROI_COLORS)]
                            opacity = 0.5
                            visible = True
                            is_contour = False
                            thickness = 1.0

                        color = (
                            [int(c) for c in raw_col[:3]]
                            if isinstance(raw_col, (list, tuple)) and len(raw_col) >= 3
                            else [255, 0, 0]
                        )

                        sub_state = {
                            "source_mode": "Target FG (val)",
                            "source_val": float(val_int),
                            "source_type": "Label Map",
                            "name": name,
                            "color": color,
                            "opacity": opacity,
                            "visible": visible,
                            "is_contour": is_contour,
                            "thickness": thickness,
                        }
                        sub_task = {
                            "new_id": new_id,
                            "path": actual_path,
                            "state": sub_state,
                        }

                        pending = None
                        err = None
                        try:
                            bbox = bboxes.get(val_int) if bboxes else None
                            pending = controller.roi.extract_label_from_image(
                                new_id,
                                read_path,
                                img,
                                data,
                                val_int,
                                name,
                                color,
                                bbox,
                                defer=True,
                            )
                            if pending is not None:
                                vol = pending["vol"]
                                if isinstance(actual_path, list):
                                    vol.file_paths = actual_path
                                else:
                                    vol.file_paths = [actual_path]
                        except Exception as e:
                            err = f"- Failed to load {name}: {e}"

                        results.append((sub_task, pending, err))
                    continue

                mode = task["state"].get("source_mode", "Ignore BG (val)")
                target_val = task["state"].get("source_val", 0.0)
                pending = None  # computed here, registered on the main thread
                err = None

                try:
                    # --- FAST PATH FOR LABEL MAPS ---
                    if mode == "Target FG (val)" and bboxes is not None:
                        val_int = int(target_val)
                        if float(val_int) == target_val:
                            pending = controller.roi.extract_label_from_image(
                                task["new_id"],
                                read_path,
                                img,
                                data,
                                val_int,
                                task["state"].get("name"),
                                task["state"].get("color", [255, 0, 0]),
                                bboxes.get(val_int),
                                defer=True,
                            )

                    # --- SLOW PATH FALLBACK ---
                    # Note: For Label Maps (Target FG), if extract_label_from_image returned None,
                    # the label is genuinely not in the image and should not be created as an empty mask.
                    if pending is None and task["state"].get("source_type") != "Label Map":
                        pending = controller.roi.load_binary_mask(
                            task["new_id"],
                            read_path,
                            name=task["state"].get("name"),
                            color=task["state"].get("color", [255, 0, 0]),
                            mode=mode,
                            target_val=target_val,
                            preloaded_sitk=img,
                            defer=True,
                        )

                    if pending is not None:
                        vol = pending["vol"]
                        if isinstance(actual_path, list):
                            vol.file_paths = actual_path
                        else:
                            vol.file_paths = [actual_path]
                except Exception as e:
                    err = f"- Failed to load {task['state'].get('name')}: {e}"

                results.append((task, pending, err))
        except Exception as e:
            for task in tasks:
                results.append(
                    (
                        task,
                        None,
                        f"- Failed to read {path_for_print}: {e}",
                    )
                )

    return results


def _restore_workspace_rois(controller, ws, id_map, warnings, resolve_workspace_path):
    """[generator] Load the ROIs of a workspace (PHASE 5 of
    load_workspace_sequence), one file per worker, registered on the main thread."""
    from collections import defaultdict

    valid_rois_to_load = _gather_workspace_rois(
        controller, ws, id_map, warnings, resolve_workspace_path
    )
    total_rois = sum(
        t.get("expected_count", 1) if t.get("is_label_map") else 1
        for t in valid_rois_to_load
    )
    if total_rois == 0:
        show_loading_modal("Loading image...", "Restoring ROIs...")
        yield
        return

    tasks_by_path = defaultdict(list)
    for task in valid_rois_to_load:
        tasks_by_path[task["path"]].append(task)

    done_count = [0]

    def on_file_done(path, future):
        tasks = tasks_by_path[path]
        try:
            group_results = future.result()
        except Exception as e:
            group_results = [
                (task, None, f"- Failed to load {task['state'].get('name')}: {e}")
                for task in tasks
            ]
        for task, pending, err in group_results:
            roi_id = controller.roi.register_roi(pending)
            if err:
                warnings.append(err)
            elif roi_id:
                roi = controller.view_states[task["new_id"]].rois.get(roi_id)
                if roi:
                    r_state = task["state"]
                    roi.opacity = r_state.get("opacity", 0.5)
                    roi.visible = r_state.get("visible", True)
                    roi.is_contour = r_state.get("is_contour", False)
                    roi.thickness = r_state.get("thickness", 1.0)
        done_count[0] += len(group_results)
        cur_total = max(total_rois, done_count[0])
        show_loading_modal(
            "Loading image...",
            f"Restoring ROIs ({done_count[0]}/{cur_total})",
            progress=(done_count[0] / cur_total) if cur_total > 0 else 1.0,
        )

    yield from _run_parallel(
        list(tasks_by_path),
        lambda path: _load_workspace_roi_file(controller, path, tasks_by_path[path]),
        on_file_done,
    )


def load_workspace_sequence(gui, controller, filepath):
    """Safely restores a full workspace using ID mapping, strict hierarchy, and Parallel Loading."""
    import json
    from vvv.utils import ViewMode

    try:
        with open(filepath, "r") as f:
            ws = json.load(f)
    except Exception as e:
        gui.show_status_message(f"Failed to load workspace: {e}")
        return

    display_name = "Reading Workspace Data..."
    show_loading_modal("Loading image...", display_name)

    warnings = []

    workspace_path_stored = ws.get("workspace_path") or ws.get("workspace_file_path")
    local_workspace_filepath = filepath

    def resolve_workspace_path(stored_path):
        if not stored_path:
            return stored_path
        if isinstance(stored_path, (list, tuple)):
            if len(stored_path) == 0:
                return stored_path
            resolved_first = resolve_workspace_path(stored_path[0])
            resolved_list = [resolved_first]
            for item in stored_path[1:]:
                if isinstance(item, str) and item.lower().endswith(".json"):
                    try:
                        orig_dir = os.path.dirname(os.path.expanduser(stored_path[0]))
                        item_abs = os.path.expanduser(item)
                        rel_to_orig = os.path.relpath(item_abs, orig_dir)
                        resolved_dir = os.path.dirname(resolved_first)
                        candidate = os.path.abspath(
                            os.path.join(resolved_dir, rel_to_orig)
                        )
                        resolved_list.append(candidate)
                    except Exception:
                        resolved_list.append(resolve_workspace_path(item))
                else:
                    resolved_list.append(resolve_workspace_path(item))
            return (
                resolved_list if isinstance(stored_path, list) else tuple(resolved_list)
            )
        if isinstance(stored_path, str) and stored_path.startswith("4D:"):
            return stored_path

        p = os.path.expanduser(stored_path)
        if os.path.exists(p):
            return p

        # Resolve relative to the local workspace location
        if workspace_path_stored and local_workspace_filepath:
            stored_ws_dir = os.path.dirname(os.path.expanduser(workspace_path_stored))
            local_ws_dir = os.path.dirname(os.path.abspath(local_workspace_filepath))
            try:
                rel_p = os.path.relpath(p, stored_ws_dir)
                local_resolved = os.path.abspath(os.path.join(local_ws_dir, rel_p))
                if os.path.exists(local_resolved):
                    return local_resolved
            except Exception:
                pass

        # Try suffix matching/guesswork relative to local_ws_dir
        if local_workspace_filepath:
            local_ws_dir = os.path.dirname(os.path.abspath(local_workspace_filepath))
            parts = p.split(os.sep)
            for i in range(len(parts) - 1, 0, -1):
                subpath = os.sep.join(parts[i:])
                candidate = os.path.abspath(os.path.join(local_ws_dir, subpath))
                if os.path.exists(candidate):
                    return candidate
                candidate_parent = os.path.abspath(
                    os.path.join(os.path.dirname(local_ws_dir), subpath)
                )
                if os.path.exists(candidate_parent):
                    return candidate_parent
        return p

    # --- PHASE 1: GATHER ALL UNIQUE FILES TO LOAD ---
    tasks_to_load = []
    legacy_overlays = []
    for old_id, img_data in ws.get("images", {}).items():
        # Add Base Image
        raw_path = img_data.get("path")
        if raw_path:
            if isinstance(raw_path, list):
                resolved_list = resolve_workspace_path(raw_path)
                p0 = resolved_list[0]
                if os.path.exists(p0):
                    tasks_to_load.append((old_id, tuple(resolved_list)))
                else:
                    warnings.append(
                        f"Missing DICOM File: {os.path.basename(raw_path[0])}"
                    )
            elif isinstance(raw_path, str) and raw_path.startswith("4D:"):
                tasks_to_load.append((old_id, raw_path))
            else:
                p = resolve_workspace_path(raw_path)
                if os.path.exists(p):
                    tasks_to_load.append((old_id, p))
                else:
                    warnings.append(f"Missing File: {os.path.basename(raw_path)}")

        # Add Fusion Overlay
        ov_info = img_data.get("overlay")
        if ov_info and "id" not in ov_info:
            ov_raw_path = ov_info.get("path")
            if ov_raw_path:
                if isinstance(ov_raw_path, list):
                    resolved_list = resolve_workspace_path(ov_raw_path)
                    p0 = resolved_list[0]
                    if os.path.exists(p0):
                        legacy_overlays.append((old_id, tuple(resolved_list)))
                    else:
                        warnings.append(
                            f"Missing Overlay DICOM: {os.path.basename(ov_raw_path[0])}"
                        )
                elif isinstance(ov_raw_path, str) and ov_raw_path.startswith("4D:"):
                    legacy_overlays.append((old_id, ov_raw_path))
                else:
                    ov_path = resolve_workspace_path(ov_raw_path)
                    if os.path.exists(ov_path):
                        legacy_overlays.append((old_id, ov_path))
                    else:
                        warnings.append(
                            f"Missing Overlay: {os.path.basename(ov_raw_path)}"
                        )

    total_files = len(tasks_to_load) + len(legacy_overlays)
    id_map = {}
    legacy_overlay_map = {}

    # --- PHASE 2: PARALLEL LOAD ALL IMAGES & OVERLAYS ---
    load_jobs = [("base", old_id, p) for old_id, p in tasks_to_load] + [
        ("legacy_ov", parent_old_id, p) for parent_old_id, p in legacy_overlays
    ]
    done_count = [0]

    def read_job(job):
        p = job[2]
        return controller.file.read_image(
            list(p) if isinstance(p, tuple) else p, ignore_history=True
        )

    def on_image_done(job, future):
        task_type, task_id, p = job
        try:
            new_id = controller.file.register_image(future.result())
            if task_type == "base":
                id_map[task_id] = new_id
            else:
                legacy_overlay_map[task_id] = new_id
        except Exception as e:
            name = os.path.basename(p[0] if isinstance(p, tuple) else p)
            warnings.append(f"- {name}: {e}")
        done_count[0] += 1
        show_loading_modal(
            "Loading image...",
            f"Restoring Images & Overlays ({done_count[0]}/{total_files})",
            progress=(done_count[0] / total_files),
        )

    yield from _run_parallel(load_jobs, read_job, on_image_done)

    # --- PHASE 3: APPLY STATES SYNCHRONOUSLY ---
    from vvv.core.view_state import ProfileLineState

    for old_id, img_data in ws.get("images", {}).items():
        if old_id in id_map:
            new_id = id_map[old_id]

            controller.volumes[new_id].is_overlay_only = img_data.get(
                "is_overlay_only", False
            )
            if "unit" in img_data and img_data["unit"] is not None:
                controller.volumes[new_id].unit = img_data["unit"]
            if "unit_source" in img_data and img_data["unit_source"] is not None:
                controller.volumes[new_id].unit_source = img_data["unit_source"]

            vs = controller.view_states[new_id]
            vs.display.from_dict(img_data.get("display", {}))
            vs.camera.from_dict(img_data.get("camera", {}))
            if "extraction" in img_data:
                vs.extraction.from_dict(img_data["extraction"])
            if "dvf" in img_data:
                vs.dvf.from_dict(img_data["dvf"])
            # Restore plugin state (including ROI filter/sort via roi_plugin)
            plugins_data = img_data.get("plugins", {})
            # Backward compat: old workspaces stored roi_filter/roi_sort_order
            # as top-level keys instead of under plugins.roi_plugin.
            if "roi_plugin" not in plugins_data:
                legacy_filter = img_data.get("roi_filter", "")
                legacy_sort = img_data.get("roi_sort_order", 0)
                if legacy_filter or legacy_sort:
                    plugins_data["roi_plugin"] = {
                        "roi_filter": legacy_filter,
                        "roi_sort_order": legacy_sort,
                    }
            if plugins_data and gui:
                for plugin in gui.plugins:
                    plugin_data = plugins_data.get(plugin.plugin_id, {})
                    if plugin_data:
                        plugin.restore_image_state(
                            new_id, plugin_data, context="workspace"
                        )
            vs.sync_group = img_data.get("sync_group", 0)
            vs.sync_wl_group = img_data.get("sync_wl_group", 0)

            # Restore Profiles
            for p_dict in img_data.get("profiles", []):
                p = ProfileLineState()
                p.from_dict(p_dict)
                vs.profiles[p.id] = p

            # Apply Overlays immediately since they are already loaded in RAM
            ov_info = img_data.get("overlay")
            if ov_info:
                ov_id = None
                if "id" in ov_info:
                    ov_id = id_map.get(ov_info["id"])
                else:
                    # Legacy support
                    ov_id = legacy_overlay_map.get(old_id)
                    if not ov_id:
                        ov_raw_path = ov_info.get("path")
                        if ov_raw_path:
                            if isinstance(ov_raw_path, list):
                                ov_p = tuple(resolve_workspace_path(ov_raw_path))
                            elif isinstance(
                                ov_raw_path, str
                            ) and ov_raw_path.startswith("4D:"):
                                ov_p = ov_raw_path
                            else:
                                ov_p = resolve_workspace_path(ov_raw_path)

                                for t_old_id, t_p in tasks_to_load:
                                    if t_p == ov_p and t_old_id in id_map:
                                        ov_id = id_map[t_old_id]
                                        break

                if ov_id and ov_id in controller.volumes:
                    if "id" not in ov_info:
                        controller.volumes[ov_id].is_overlay_only = True
                    ov_vs = controller.view_states[ov_id]
                    ov_vs.display.colormap = ov_info.get("colormap", "Grayscale")
                    if "threshold" in ov_info and ov_info["threshold"] is not None:
                        ov_vs.display.min_threshold = ov_info["threshold"]

                    vs.set_overlay(ov_id, controller.volumes[ov_id])
                    # On the image's JobRunner: cannot race another resample of it
                    controller.resample_image(new_id)
                    vs.display.overlay.mode = ov_info.get("mode", "Registration")
                    vs.display.overlay.opacity = ov_info.get("opacity", 0.5)

    # --- PHASE 4: MAP VIEWERS ---
    saved_viewers = ws.get("viewers", {})
    for tag in ["V1", "V2", "V3", "V4"]:
        if tag in saved_viewers and saved_viewers[tag].get("image_id") in id_map:
            v_data = saved_viewers[tag]
            new_id = id_map[v_data["image_id"]]

            # 1. Update the global layout state
            controller.layout[tag] = new_id

            # 2. Force the mount immediately so we can safely override the default boot-up re-center flag.
            viewer = controller.viewers.get(tag)
            if viewer:
                viewer.set_image(new_id)
                viewer.orientation = ViewMode[v_data["orientation"]]
                viewer.is_geometry_dirty = True
                viewer.is_viewer_data_dirty = True
                viewer.needs_recenter = False

                if "zoom" in v_data:
                    viewer.zoom = v_data["zoom"]
                if "pan_offset" in v_data:
                    viewer.pan_offset = v_data["pan_offset"]
        else:
            controller.layout[tag] = None
            viewer = controller.viewers.get(tag)
            if viewer:
                viewer.drop_image()
    yield

    show_loading_modal("Loading image...", "Restoring ROIs...")

    # --- PHASE 5: RESTORE ROIs (Parallelized to quickly load large label maps) ---
    yield from _restore_workspace_rois(
        controller, ws, id_map, warnings, resolve_workspace_path
    )

    # --- PHASE 6: FINALIZE ---
    # 1. Reorder dictionaries to strictly match the original workspace save order
    ordered_vs = {}
    ordered_vol = {}

    for old_id in ws.get("images", {}).keys():
        if old_id in id_map:
            new_id = id_map[old_id]
            if new_id in controller.view_states:
                ordered_vs[new_id] = controller.view_states[new_id]
                ordered_vol[new_id] = controller.volumes[new_id]

    # 2. Add overlays that were hidden from the main list
    for old_id, img_data in ws.get("images", {}).items():
        ov_info = img_data.get("overlay")
        if ov_info:
            ov_id = None
            if "id" in ov_info:
                ov_id = id_map.get(ov_info["id"])
            else:
                ov_id = legacy_overlay_map.get(old_id)

            if ov_id and ov_id in controller.view_states and ov_id not in ordered_vs:
                ordered_vs[ov_id] = controller.view_states[ov_id]
                ordered_vol[ov_id] = controller.volumes[ov_id]

    # 3. Add any remaining items (like pre-existing images and ROIs)
    for v_id, vs in list(controller.view_states.items()):
        if v_id not in ordered_vs:
            ordered_vs[v_id] = vs
    for v_id, vol in list(controller.volumes.items()):
        if v_id not in ordered_vol:
            ordered_vol[v_id] = vol

    controller.view_states.clear()
    controller.view_states.update(ordered_vs)

    controller.volumes.clear()
    controller.volumes.update(ordered_vol)

    for new_id in id_map.values():
        controller.sync.propagate_sync(new_id)
        controller.update_all_viewers_of_image(new_id)

        # Re-open restored plot windows
        vs = controller.view_states[new_id]
        for p_id, p in vs.profiles.items():
            if getattr(p, "plot_open", False):
                profile_plugin = next(
                    (pl for pl in gui.plugins if pl.plugin_id == "profile_plugin"), None
                )
                if profile_plugin:
                    profile_plugin._ui.on_plot_clicked(None, None, p_id)

    controller.ui_needs_refresh = True
    controller._flag_all_viewers_dirty()

    if gui:
        for plugin in gui.plugins:
            if hasattr(plugin, "_controller") and hasattr(
                plugin._controller, "clear_viewer_cache"
            ):
                for v_tag in ["V1", "V2", "V3", "V4"]:
                    plugin._controller.clear_viewer_cache(v_tag)

        active_tag = ws.get("active_viewer", "V1")
        if active_tag in controller.viewers:
            gui.set_context_viewer(controller.viewers[active_tag])
        elif id_map and "V1" in controller.viewers:
            gui.set_context_viewer(controller.viewers["V1"])

        layout_mode = str(ws.get("layout_mode") or ws.get("viewport_layout") or "4")
        saved_visible = ws.get("visible_viewers")
        if layout_mode in ["1", "2", "4"]:
            gui.set_viewport_layout(layout_mode, visible_viewers=saved_visible)
        else:
            gui.on_window_resize()
    elif gui:
        gui.on_window_resize()

    yield from _handle_warnings_and_cleanup(
        gui, warnings, "Workspace Warnings", "Some files could not be found or loaded:"
    )

    # Check for out-of-bounds ROIs
    all_rois = {}
    for vs in controller.view_states.values():
        all_rois.update(vs.rois)
    yield from _warn_rois_outside_fov(gui, controller, all_rois)


def create_boot_sequence(
    gui, controller, image_tasks, sync=False, link_all=False, link_all_wl=False
):
    if not image_tasks:
        return

    total_files = len(image_tasks) + sum(1 for t in image_tasks if t["fusion"])
    warnings = []
    loaded_ids = []
    id_to_group = {}

    # 1. Gather all file tasks that need loading
    # Each job is (task_idx, role, path) where role is "base" or "fusion"
    jobs = []
    for idx, task in enumerate(image_tasks):
        jobs.append((idx, "base", task["base"]))
        if task["fusion"]:
            jobs.append((idx, "fusion", task["fusion"]["path"]))

    task_results = {}
    base_ids = []

    # --- THE PARALLEL LOADER & REAL PROGRESS BAR ---
    if total_files == 1:
        # Bypasses threads, modals and frame yields entirely for maximum boot speed
        idx, role, path = jobs[0]
        try:
            img_id = controller.file.load_image(path)
            task_results[(idx, role)] = img_id
        except Exception as e:
            warnings.append(f"- {os.path.basename(path)}: {e}")
    else:
        # Show loading modal immediately without extra delays
        show_loading_modal("Loading images...", "Initializing...", progress=0.0)
        done_count = [0]

        def on_done(job, future):
            idx, role, path = job
            try:
                img_id = controller.file.register_image(future.result())
                task_results[(idx, role)] = img_id
            except Exception as e:
                warnings.append(f"- {os.path.basename(path)}: {e}")
            done_count[0] += 1
            show_loading_modal(
                "Initializing...",
                f"Loaded {os.path.basename(path)} ({done_count[0]}/{total_files})",
                progress=(done_count[0] / total_files),
            )

        yield from _run_parallel(
            jobs, lambda job: controller.file.read_image(job[2]), on_done, poll_s=0.005
        )
    # -----------------------------------------------

    # 3. Now wire up the loaded data into the ViewStates synchronously
    for idx, task in enumerate(image_tasks):
        if (idx, "base") not in task_results:
            continue

        base_id = task_results[(idx, "base")]
        base_ids.append(base_id)
        loaded_ids.append(base_id)
        id_to_group[base_id] = task.get("sync_group", 0)

        if task.get("base_cmap"):
            controller.view_states[base_id].display.colormap = task["base_cmap"]
            if task.get("min_threshold") is not None:
                controller.view_states[base_id].display.min_threshold = task[
                    "min_threshold"
                ]
            controller.view_states[base_id].is_data_dirty = True

        if task["fusion"]:
            if (idx, "fusion") in task_results:
                fuse_id = task_results[(idx, "fusion")]
                loaded_ids.append(fuse_id)
                id_to_group[fuse_id] = task.get("sync_group", 0)

                fuse_vs = controller.view_states[fuse_id]
                fuse_vs.display.colormap = task["fusion"]["cmap"]
                fuse_vs.is_data_dirty = True

                if task["fusion"].get("threshold") is not None:
                    fuse_vs.display.min_threshold = task["fusion"]["threshold"]

                base_vs = controller.view_states[base_id]
                base_vs.set_overlay(fuse_id, fuse_vs.volume)
                # On the image's JobRunner: cannot race another resample of it
                controller.resample_image(base_id)
                base_vs.display.overlay.opacity = task["fusion"]["opacity"]

                if "mode" in task["fusion"]:
                    base_vs.display.overlay.mode = task["fusion"]["mode"]

        # Load associated labels (ROIs) for the base image
        if task.get("labels"):
            for label_path in task["labels"]:
                for val in load_label_map_sequence(
                    gui, controller, base_id, label_path
                ):
                    yield val

    controller.default_viewers_orientation()

    for i, img_id in enumerate(base_ids):
        if i == 0:
            for tag in ["V1", "V2", "V3", "V4"]:
                controller.layout[tag] = img_id
        elif i == 1:
            controller.layout["V3"] = img_id
            controller.layout["V4"] = img_id
        elif i == 2:
            controller.layout["V2"] = base_ids[1]
            controller.layout["V3"] = img_id
            controller.layout["V4"] = img_id
        elif i >= 3:
            controller.layout["V4"] = img_id

    for img_id in loaded_ids:
        same_viewers = [
            v.tag for v in controller.viewers.values() if v.image_id == img_id
        ]
        if same_viewers:
            controller.sync.propagate_ppm(same_viewers)

    for img_id in loaded_ids:
        if sync or link_all:
            controller.set_sync_group(img_id, 1)
        elif id_to_group.get(img_id, 0) > 0:
            controller.set_sync_group(img_id, id_to_group[img_id])

    if link_all_wl:
        controller.sync.link_all_wl()

    gui.on_window_resize()

    if "V1" in controller.viewers:
        gui.set_context_viewer(controller.viewers["V1"])

    controller.ui_needs_refresh = True

    yield from _handle_warnings_and_cleanup(
        gui,
        warnings,
        "Boot Sequence Warning",
        "Some files provided via command line failed to load:",
    )
