import os
import dearpygui.dearpygui as dpg
from vvv.config import ROI_COLORS
from vvv.ui.ui_notifications import show_loading_modal, hide_loading_modal


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


def _handle_warnings_and_cleanup(gui, warnings, title, message):
    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")
    yield
    if warnings:
        gui.show_message(title, f"{message}\n\n" + "\n".join(warnings))
        while dpg.does_item_exist("generic_message_modal"):
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
    import os
    import time
    import concurrent.futures

    is_4d = file_path.startswith("4D:")
    display_name = "4D Sequence" if is_4d else os.path.basename(file_path)

    # Start the progress bar at 20% to show it is active
    show_loading_modal("Loading image...", display_name, progress=0.2)

    for _ in range(3):
        yield

    img_id = None
    load_error = None

    # NON-BLOCKING FOR SINGLE FILES & 4D SEQUENCES
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(controller.file.load_image, file_path)

        # Keep DearPyGui spinning while SimpleITK loads the heavy file!
        while not future.done():
            yield  # Hands control back to gui.py so the UI doesn't freeze
            time.sleep(0.01)

        try:
            img_id = future.result()
        except Exception as e:
            load_error = e

    if load_error:
        if dpg.does_item_exist("loading_modal"):
            dpg.delete_item("loading_modal")
        yield
        gui.show_message(
            "File Load Error", f"Failed to load image:\n{display_name}\n\n{load_error}"
        )
        while dpg.does_item_exist("generic_message_modal"):
            yield
        hide_loading_modal()
        return

    show_loading_modal(
        "Loading image...", "Applying synchronization and layouts...", progress=1.0
    )
    yield

    _apply_default_layout(gui, controller, img_id)
    yield from _handle_warnings_and_cleanup(gui, [], "", "")


def load_batch_images_sequence(gui, controller, file_paths):
    import time
    import concurrent.futures

    total_files = len(file_paths)
    warnings = []

    display_name = f"Loading {total_files} images..."
    show_loading_modal("Loading image...", display_name)
    # Yield multiple times to guarantee the OS paints the window
    for _ in range(3):
        yield

    loaded_ids = []
    clean_paths = []
    for path in file_paths:
        if isinstance(path, (list, tuple)) and len(path) > 0:
            clean_paths.append(list(path))  # Force it to a list for VolumeData
        else:
            clean_paths.append(path)

    # --- THE PARALLEL LOADER & REAL PROGRESS BAR ---
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(total_files, 8)
    ) as executor:
        # Submit all tasks simultaneously
        futures: list[concurrent.futures.Future | None] = [
            executor.submit(controller.file.load_image, p) for p in clean_paths
        ]

        completed = 0
        while completed < total_files:
            for i, future in enumerate(futures):
                if future is not None and future.done():
                    try:
                        img_id = future.result()
                        loaded_ids.append(img_id)
                    except Exception as e:
                        warnings.append(f"- Failed: {e}")

                    futures[i] = None  # Mark as processed
                    completed += 1

                    show_loading_modal(
                        "Loading image...",
                        f"Loaded ({completed}/{total_files})",
                        progress=(completed / total_files),
                    )

            # Let DearPyGui render a frame while the background threads work!
            yield
            time.sleep(0.01)

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


def _rasterize_and_load_labels(
    gui, controller, base_image_id, filepath, unique_labels, label_dict
):
    """
    [REUSABLE_WORKER]
    The core, multithreaded engine for rasterizing a label map.
    Called by both the interactive loader and the workspace loader.
    """
    import time
    import concurrent.futures
    import numpy as np
    import SimpleITK as sitk
    from vvv.maths.image import VolumeData
    from vvv.core.roi_manager import ROIState
    from vvv.config import ROI_COLORS

    vs = controller.view_states[base_image_id]
    base_vol = controller.volumes[base_image_id]
    total_lbls = len(unique_labels)
    base_name = controller.roi._clean_roi_name(filepath)

    # --- Read the full image ONCE ---
    img = sitk.ReadImage(filepath)
    data = sitk.GetArrayViewFromImage(img)

    # --- PRE-EXTRACT BOUNDING BOXES FOR THREAD SAFETY ---
    bboxes = _compute_label_bboxes(img, unique_labels)

    def _process_label(val_int, custom_name, color, bbox):
        return controller.roi.extract_label_from_image(
            base_image_id, filepath, img, data, val_int, custom_name, color, bbox
        )

    # --- PARALLEL PROCESSING ---
    with vs.loading_shield():
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(total_lbls, 8)
        ) as executor:
            futures: list[concurrent.futures.Future | None] = []
            for i, val in enumerate(unique_labels, 1):
                val_int = int(val)
                custom_name = label_dict.get(val_int, f"{base_name} - Lbl {val_int}")
                color = ROI_COLORS[(val_int - 1) % len(ROI_COLORS)]
                bbox = bboxes.get(val_int)
                futures.append(
                    executor.submit(_process_label, val_int, custom_name, color, bbox)
                )

            completed = 0
            while completed < total_lbls:
                for i, future in enumerate(futures):
                    if future is not None and future.done():
                        res = future.result()
                        futures[i] = None
                        completed += 1
                        yield res

                # Yield control to DearPyGui while waiting for threads
                yield "KEEP_ALIVE"
                time.sleep(0.01)


def load_label_map_sequence(gui, controller, base_image_id, filepath):
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
    if os.path.exists(json_path):
        try:
            import json

            with open(json_path, "r") as f:
                raw_dict = json.load(f)
                label_dict = {int(k): str(v) for k, v in raw_dict.items()}
        except Exception as e:
            print(f"Warning: Failed to parse {json_path}: {e}")

    completed = 0
    for roi_id in _rasterize_and_load_labels(
        gui, controller, base_image_id, filepath, unique_labels, label_dict
    ):
        if roi_id == "KEEP_ALIVE":
            yield
            continue

        completed += 1

        show_loading_modal(
            "Loading Label Map...",
            f"Rasterizing Labels ({completed}/{total_lbls})...",
            progress=(completed / total_lbls),
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


def load_rtstruct_sequence(gui, controller, base_image_id, filepath, selected_rois):
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


def load_workspace_sequence(gui, controller, filepath):
    """Safely restores a full workspace using ID mapping, strict hierarchy, and Parallel Loading."""
    import json
    import time
    import concurrent.futures
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

    # --- PHASE 1: GATHER ALL UNIQUE FILES TO LOAD ---
    tasks_to_load = []
    legacy_overlays = []
    for old_id, img_data in ws.get("images", {}).items():
        # Add Base Image
        raw_path = img_data.get("path")
        if raw_path:
            if isinstance(raw_path, list):
                p0 = os.path.expanduser(raw_path[0])
                if os.path.exists(p0):
                    tasks_to_load.append((old_id, tuple(os.path.expanduser(p) for p in raw_path)))
                else:
                    warnings.append(f"Missing DICOM File: {os.path.basename(raw_path[0])}")
            elif isinstance(raw_path, str) and raw_path.startswith("4D:"):
                tasks_to_load.append((old_id, raw_path))
            else:
                p = os.path.expanduser(raw_path)
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
                    p0 = os.path.expanduser(ov_raw_path[0])
                    if os.path.exists(p0):
                        legacy_overlays.append((old_id, tuple(os.path.expanduser(p) for p in ov_raw_path)))
                    else:
                        warnings.append(f"Missing Overlay DICOM: {os.path.basename(ov_raw_path[0])}")
                elif isinstance(ov_raw_path, str) and ov_raw_path.startswith("4D:"):
                    legacy_overlays.append((old_id, ov_raw_path))
                else:
                    ov_path = os.path.expanduser(ov_raw_path)
                    if os.path.exists(ov_path):
                        legacy_overlays.append((old_id, ov_path))
                    else:
                        warnings.append(f"Missing Overlay: {os.path.basename(ov_raw_path)}")

    total_files = len(tasks_to_load) + len(legacy_overlays)
    id_map = {}
    legacy_overlay_map = {}

    # --- PHASE 2: PARALLEL LOAD ALL IMAGES & OVERLAYS ---
    if total_files > 0:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(total_files, 8)
        ) as executor:
            future_to_path = {}
            for old_id, p in tasks_to_load:
                f = executor.submit(controller.file.load_image, list(p) if isinstance(p, tuple) else p)
                future_to_path[f] = ("base", old_id, p)
            for parent_old_id, p in legacy_overlays:
                f = executor.submit(controller.file.load_image, list(p) if isinstance(p, tuple) else p)
                future_to_path[f] = ("legacy_ov", parent_old_id, p)
            
            futures: list[concurrent.futures.Future | None] = [
                f for f in future_to_path.keys()
            ]
            completed = 0

            while completed < total_files:
                for i, future in enumerate(futures):
                    if future is not None and future.done():
                        p = future_to_path[future]
                        try:
                            new_id = future.result()
                            task_type, task_id, _p = future_to_path[future]
                            if task_type == "base":
                                id_map[task_id] = new_id
                            else:
                                legacy_overlay_map[task_id] = new_id
                        except Exception as e:
                            task_type, task_id, _p = future_to_path[future]
                            if isinstance(_p, tuple):
                                warnings.append(f"- {os.path.basename(_p[0])}: {e}")
                            else:
                                warnings.append(f"- {os.path.basename(_p)}: {e}")

                        futures[i] = None
                        completed += 1

                        show_loading_modal(
                            "Loading image...",
                            f"Restoring Images & Overlays ({completed}/{total_files})",
                            progress=(completed / total_files),
                        )
                # Keep DearPyGui alive
                yield
                time.sleep(0.01)

    # --- PHASE 3: APPLY STATES SYNCHRONOUSLY ---
    from vvv.core.view_state import ProfileLineState
    for old_id, img_data in ws.get("images", {}).items():
        if old_id in id_map:
            new_id = id_map[old_id]
            
            controller.volumes[new_id].is_overlay_only = img_data.get("is_overlay_only", False)

            vs = controller.view_states[new_id]
            vs.display.from_dict(img_data.get("display", {}))
            vs.camera.from_dict(img_data.get("camera", {}))
            if "extraction" in img_data:
                vs.extraction.from_dict(img_data["extraction"])
            if "dvf" in img_data:
                vs.dvf.from_dict(img_data["dvf"])
            vs.sync_group = img_data.get("sync_group", 0)
            vs.sync_wl_group = img_data.get("sync_wl_group", 0)

            # Restore Profiles
            for p_dict in img_data.get("profiles", []):
                p = ProfileLineState()
                p.from_dict(p_dict)
                vs.profiles[p.id] = p

            if hasattr(gui, "roi_ui"):
                gui.roi_ui.roi_filters[new_id] = img_data.get("roi_filter", "")
                gui.roi_ui.roi_sort_orders[new_id] = img_data.get(
                    "roi_sort_order", 0
                )

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
                                ov_p = tuple(os.path.expanduser(x) for x in ov_raw_path)
                            elif isinstance(ov_raw_path, str) and ov_raw_path.startswith("4D:"):
                                ov_p = ov_raw_path
                            else:
                                ov_p = os.path.expanduser(ov_raw_path)
                                
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
                        ov_vs.display.base_threshold = ov_info["threshold"]

                    vs.set_overlay(ov_id, controller.volumes[ov_id], controller)
                    vs.display.overlay_mode = ov_info.get("mode", "Registration")
                    vs.display.overlay_opacity = ov_info.get("opacity", 0.5)

    # --- PHASE 4: MAP VIEWERS ---
    for tag, v_data in ws.get("viewers", {}).items():
        old_img_id = v_data.get("image_id")
        if old_img_id in id_map:
            new_id = id_map[old_img_id]

            # 1. Update the global layout state
            controller.layout[tag] = new_id

            # 2. Force the mount immediately so we can safely override the default boot-up re-center flag.
            # This ensures the viewer uses the exact zoom/pan we restored in Phase 3.
            viewer = controller.viewers[tag]
            viewer.set_image(new_id)
            viewer.orientation = ViewMode[v_data["orientation"]]
            viewer.needs_recenter = False
    yield

    show_loading_modal("Loading image...", "Restoring ROIs...")

    # --- PHASE 5: RESTORE ROIs (Parallelized to quickly load large label maps) ---
    # 1. Gather all valid ROIs first to calculate total progress
    valid_rois_to_load = []
    for old_id, img_data in ws.get("images", {}).items():
        if old_id in id_map:
            new_id = id_map[old_id]
            for roi_data in img_data.get("rois", []):
                raw_r_path = roi_data.get("path", "")
                if raw_r_path:
                    if isinstance(raw_r_path, list):
                        r_path = tuple(os.path.expanduser(x) for x in raw_r_path)
                        if os.path.exists(r_path[0]):
                            valid_rois_to_load.append({
                                "new_id": new_id,
                                "path": r_path,
                                "state": roi_data.get("state", {}),
                            })
                        else:
                            warnings.append(f"Missing ROI DICOM: {os.path.basename(r_path[0])}")
                    elif isinstance(raw_r_path, str) and raw_r_path.startswith("4D:"):
                        warnings.append("4D ROIs are not supported.")
                    else:
                        r_path = os.path.expanduser(raw_r_path)
                        if os.path.exists(r_path):
                            valid_rois_to_load.append({
                                "new_id": new_id,
                                "path": r_path,
                                "state": roi_data.get("state", {}),
                            })
                        else:
                            warnings.append(f"Missing ROI: {os.path.basename(raw_r_path)}")

    total_rois = len(valid_rois_to_load)

    if total_rois == 0:
        show_loading_modal("Loading image...", "Restoring ROIs...")
        yield
    else:
        from collections import defaultdict
        import SimpleITK as sitk

        tasks_by_path = defaultdict(list)
        for task in valid_rois_to_load:
            tasks_by_path[task["path"]].append(task)

        def process_file_group(r_path, tasks):
            results = []
            is_rtstruct = any(t["state"].get("rtstruct_info") for t in tasks)
            
            actual_path = list(r_path) if isinstance(r_path, tuple) else r_path
            path_for_print = os.path.basename(actual_path[0]) if isinstance(actual_path, list) else os.path.basename(actual_path)

            if is_rtstruct:
                try:
                    import pydicom

                    rt_path = actual_path[0] if isinstance(actual_path, list) else actual_path
                    ds = pydicom.dcmread(rt_path, force=True)
                    for task in tasks:
                        try:
                            roi_id = controller.roi.load_rtstruct_roi(
                                task["new_id"],
                                rt_path,
                                task["state"]["rtstruct_info"],
                                ds=ds,
                            )
                            results.append((task, roi_id, None))
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
                    img = sitk.ReadImage(actual_path)
                    data = sitk.GetArrayViewFromImage(img)
                    bboxes = None

                    # Fast-path: Only compute heavy bboxes if a label map extraction is actually requested!
                    if any(
                        t["state"].get("source_mode") == "Target FG (val)"
                        for t in tasks
                    ):
                        bboxes = _compute_label_bboxes(img)

                    for task in tasks:
                        mode = task["state"].get("source_mode", "Ignore BG (val)")
                        target_val = task["state"].get("source_val", 0.0)
                        roi_id = None
                        err = None

                        try:
                            # --- FAST PATH FOR LABEL MAPS ---
                            if mode == "Target FG (val)" and bboxes is not None:
                                val_int = int(target_val)
                                if float(val_int) == target_val:
                                    roi_id = controller.roi.extract_label_from_image(
                                        task["new_id"],
                                        actual_path,
                                        img,
                                        data,
                                        val_int,
                                        task["state"].get("name"),
                                        task["state"].get("color", [255, 0, 0]),
                                        bboxes.get(val_int),
                                    )

                            # --- SLOW PATH FALLBACK ---
                            if roi_id is None:
                                roi_id = controller.roi.load_binary_mask(
                                    task["new_id"],
                                    actual_path,
                                    name=task["state"].get("name"),
                                    color=task["state"].get("color", [255, 0, 0]),
                                    mode=mode,
                                    target_val=target_val,
                                    preloaded_sitk=img,
                                )
                        except Exception as e:
                            err = f"- Failed to load {task['state'].get('name')}: {e}"

                        results.append((task, roi_id, err))
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

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(tasks_by_path), 8)
        ) as executor:
            futures: list[concurrent.futures.Future | None] = [
                executor.submit(process_file_group, path, tasks)
                for path, tasks in tasks_by_path.items()
            ]

            completed_rois = 0
            while completed_rois < total_rois:
                for i, future in enumerate(futures):
                    if future is not None and future.done():
                        group_results = future.result()
                        for task, roi_id, err in group_results:
                            if err:
                                warnings.append(err)
                            elif roi_id:
                                vs = controller.view_states[task["new_id"]]
                                if roi_id in vs.rois:
                                    r_state = task["state"]
                                    vs.rois[roi_id].opacity = r_state.get(
                                        "opacity", 0.5
                                    )
                                    vs.rois[roi_id].visible = r_state.get(
                                        "visible", True
                                    )
                                    vs.rois[roi_id].is_contour = r_state.get(
                                        "is_contour", False
                                    )
                                    vs.rois[roi_id].thickness = r_state.get(
                                        "thickness", 1.0
                                    )
                            completed_rois += 1

                        futures[i] = None

                        show_loading_modal(
                            "Loading image...",
                            f"Restoring ROIs ({completed_rois}/{total_rois})",
                            progress=(completed_rois / total_rois),
                        )
                # Keep DearPyGui alive
                yield
                time.sleep(0.01)

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
                gui.profile_ui.on_profile_clicked(None, None, p_id)

    controller.ui_needs_refresh = True
    gui.on_window_resize()

    if id_map:
        gui.set_context_viewer(controller.viewers["V1"])

    yield from _handle_warnings_and_cleanup(
        gui, warnings, "Workspace Warnings", "Some files could not be found or loaded:"
    )


def create_boot_sequence(gui, controller, image_tasks, sync=False, link_all=False):
    import time
    import concurrent.futures

    if not image_tasks:
        return

    total_files = len(image_tasks) + sum(1 for t in image_tasks if t["fusion"])
    warnings = []

    display_name = "Initializing..."
    show_loading_modal("Loading image...", display_name)

    # Yield multiple times to guarantee the OS paints the boot modal!
    for _ in range(3):
        yield

    loaded_ids = []
    id_to_group = {}

    # 1. Gather all file paths that need loading
    jobs = []
    for task in image_tasks:
        jobs.append(task["base"])
        if task["fusion"]:
            jobs.append(task["fusion"]["path"])

    job_results = {}

    # --- THE PARALLEL LOADER & REAL PROGRESS BAR ---
    if total_files == 1:
        # Synchronous fast-path for single images to bypass threading delays and modal flashes!
        path = jobs[0]
        show_loading_modal(
            "Initializing...",
            f"Loading {os.path.basename(path)}...",
            progress=0.5,
        )
        for _ in range(2):
            yield
        try:
            job_results[path] = controller.file.load_image(path)
        except Exception as e:
            warnings.append(f"- {os.path.basename(path)}: {e}")
    else:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(total_files, 8)
        ) as executor:
            future_to_path = {
                executor.submit(controller.file.load_image, path): path for path in jobs
            }
            futures: list[concurrent.futures.Future | None] = [
                f for f in future_to_path.keys()
            ]

            completed = 0
            while completed < total_files:
                for i, future in enumerate(futures):
                    if future is not None and future.done():
                        path = future_to_path[future]
                        try:
                            img_id = future.result()
                            job_results[path] = img_id
                        except Exception as e:
                            warnings.append(f"- {os.path.basename(path)}: {e}")

                        futures[i] = None
                        completed += 1

                        show_loading_modal(
                            "Initializing...",
                            f"Loaded {os.path.basename(path)} ({completed}/{total_files})",
                            progress=(completed / total_files),
                        )

                if completed >= total_files:
                    break

                # Let DearPyGui render a frame
                yield
                time.sleep(0.01)
    # -----------------------------------------------

    show_loading_modal(
        "Loading image...", "Applying synchronization and layouts...", progress=1.0
    )
    for _ in range(2):
        yield

    # 3. Now wire up the loaded data into the ViewStates synchronously
    for task in image_tasks:
        base_path = task["base"]
        if base_path not in job_results:
            continue

        base_id = job_results[base_path]
        loaded_ids.append(base_id)
        id_to_group[base_id] = task.get("sync_group", 0)

        if task.get("base_cmap"):
            controller.view_states[base_id].display.colormap = task["base_cmap"]
            if task.get("base_threshold") is not None:
                controller.view_states[base_id].display.base_threshold = task[
                    "base_threshold"
                ]
            controller.view_states[base_id].is_data_dirty = True

        if task["fusion"]:
            fuse_path = task["fusion"]["path"]
            if fuse_path in job_results:
                fuse_id = job_results[fuse_path]
                loaded_ids.append(fuse_id)
                id_to_group[fuse_id] = task.get("sync_group", 0)

                fuse_vs = controller.view_states[fuse_id]
                fuse_vs.display.colormap = task["fusion"]["cmap"]
                fuse_vs.is_data_dirty = True

                if task["fusion"].get("threshold") is not None:
                    fuse_vs.display.base_threshold = task["fusion"]["threshold"]

                base_vs = controller.view_states[base_id]
                base_vs.set_overlay(fuse_id, fuse_vs.volume, controller)
                base_vs.display.overlay_opacity = task["fusion"]["opacity"]

                if "mode" in task["fusion"]:
                    base_vs.display.overlay_mode = task["fusion"]["mode"]

    controller.default_viewers_orientation()

    for i, img_id in enumerate(loaded_ids):
        if i == 0:
            for tag in ["V1", "V2", "V3", "V4"]:
                controller.layout[tag] = img_id
        elif i == 1:
            controller.layout["V3"] = img_id
            controller.layout["V4"] = img_id
        elif i == 2:
            controller.layout["V2"] = loaded_ids[1]
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
