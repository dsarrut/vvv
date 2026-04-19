import os
import dearpygui.dearpygui as dpg
from vvv.config import ROI_COLORS
from vvv.ui.ui_notifications import show_loading_modal, hide_loading_modal


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

    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")
    yield

    hide_loading_modal()


def load_batch_images_sequence(gui, controller, file_paths):
    import time
    import concurrent.futures

    total_files = len(file_paths)
    warnings = []

    display_name = f"Loading {total_files} images..."
    show_loading_modal("Loading image...", display_name)
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
        futures = [executor.submit(controller.file.load_image, p) for p in clean_paths]

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
        target_tag = gui.context_viewer.tag if gui.context_viewer else "V1"
        controller.layout[target_tag] = loaded_ids[0]

        target_viewer = controller.viewers[target_tag]
        target_viewer.set_orientation(
            controller.view_states[loaded_ids[0]].camera.last_orientation
        )

        if None in controller.layout.values():
            controller.default_viewers_orientation()
            for tag, current_id in controller.layout.items():
                if current_id is None:
                    controller.layout[tag] = loaded_ids[0]

        gui.set_context_viewer(target_viewer)
        controller.ui_needs_refresh = True

    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")
    yield

    if warnings:
        gui.show_message(
            "Image Load Warning",
            "Some images failed to load:\n\n" + "\n".join(warnings),
        )
        while dpg.does_item_exist("generic_message_modal"):
            yield

    hide_loading_modal()


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

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])
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
                loaded_count = controller.roi.load_label_map(
                    base_image_id, path, color_idx
                )
                color_idx += loaded_count
        except Exception as e:
            warnings.append(f"- {filename}: {e}")

    # 3. Finalize & Cleanup
    show_loading_modal("Loading ROIs...", "Applying changes...", progress=1.0)
    yield

    if vs.rois:
        gui.active_roi_id = list(vs.rois.keys())[-1]

    controller.ui_needs_refresh = True
    controller.update_all_viewers_of_image(base_image_id)

    # Let the helper cleanly destroy the modal
    hide_loading_modal()
    yield

    # 4. Display warnings safely after the loading modal is gone
    if warnings:
        gui.show_message(
            "ROI Import Warning", "Some ROIs were skipped:\n\n" + "\n".join(warnings)
        )
        while dpg.does_item_exist("generic_message_modal"):
            yield


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

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])
    yield

    warnings = []

    # --- PHASE 1: GATHER ALL UNIQUE FILES TO LOAD ---
    paths_to_load = set()
    for old_id, img_data in ws.get("images", {}).items():
        # Add Base Image
        raw_path = img_data.get("path")
        if raw_path:
            p = os.path.expanduser(raw_path)
            if os.path.exists(p):
                paths_to_load.add(p)
            else:
                warnings.append(f"Missing File: {os.path.basename(raw_path)}")

        # Add Fusion Overlay
        ov_info = img_data.get("overlay")
        if ov_info:
            ov_path = os.path.expanduser(ov_info["path"])
            if os.path.exists(ov_path):
                paths_to_load.add(ov_path)
            else:
                warnings.append(f"Missing Overlay: {os.path.basename(ov_info['path'])}")

    paths_list = list(paths_to_load)
    total_files = len(paths_list)
    path_map = {}  # Maps absolute file paths to the newly generated vs_id

    # --- PHASE 2: PARALLEL LOAD ALL IMAGES & OVERLAYS ---
    if total_files > 0:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(total_files, 8)
        ) as executor:
            future_to_path = {
                executor.submit(controller.file.load_image, p): p for p in paths_list
            }
            futures = list(future_to_path.keys())
            completed = 0

            while completed < total_files:
                for i, future in enumerate(futures):
                    if future is not None and future.done():
                        p = future_to_path[future]
                        try:
                            new_id = future.result()
                            path_map[p] = new_id
                        except Exception as e:
                            warnings.append(f"- {os.path.basename(p)}: {e}")

                        futures[i] = None
                        completed += 1

                        show_loading_modal(
                            "Loading image...",
                            f"Restoring Images & Overlays ({completed}/{total_files})",
                            progress=(completed / total_files),
                        )
                # MAGIC: Keep DearPyGui alive!
                yield
                time.sleep(0.01)

    # --- PHASE 3: APPLY STATES SYNCHRONOUSLY ---
    id_map = {}
    for old_id, img_data in ws.get("images", {}).items():
        raw_path = img_data.get("path")
        if raw_path:
            p = os.path.expanduser(raw_path)
            if p in path_map:
                new_id = path_map[p]
                id_map[old_id] = new_id

                vs = controller.view_states[new_id]
                vs.display.from_dict(img_data.get("display", {}))
                vs.camera.from_dict(img_data.get("camera", {}))
                vs.sync_group = img_data.get("sync_group", 0)

                # Apply Overlays immediately since they are already loaded in RAM
                ov_info = img_data.get("overlay")
                if ov_info:
                    ov_path = os.path.expanduser(ov_info["path"])
                    if ov_path in path_map:
                        ov_id = path_map[ov_path]
                        controller.volumes[ov_id].is_overlay_only = True
                        ov_vs = controller.view_states[ov_id]
                        ov_vs.display.colormap = ov_info.get("colormap", "Grayscale")

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

    # --- PHASE 5: RESTORE ROIs (Synchronous since there's fewer of them and already cropped) ---
    # 1. Gather all valid ROIs first to calculate total progress
    valid_rois_to_load = []
    for old_id, img_data in ws.get("images", {}).items():
        if old_id in id_map:
            new_id = id_map[old_id]
            for roi_data in img_data.get("rois", []):
                raw_r_path = roi_data.get("path", "")
                r_path = os.path.expanduser(raw_r_path)
                if r_path and os.path.exists(r_path):
                    valid_rois_to_load.append(
                        {
                            "new_id": new_id,
                            "path": r_path,
                            "state": roi_data.get("state", {}),
                        }
                    )
                elif r_path:
                    warnings.append(f"Missing ROI: {os.path.basename(raw_r_path)}")

    total_rois = len(valid_rois_to_load)

    if total_rois == 0:
        show_loading_modal("Loading image...", "Restoring ROIs...")
        yield
    else:
        # 2. Iterate and update the progress bar for each ROI
        for i, roi_task in enumerate(valid_rois_to_load, 1):
            show_loading_modal(
                "Loading image...",
                f"Restoring ROIs ({i}/{total_rois})",
                progress=(i / total_rois),
            )
            # MAGIC: Let DearPyGui render a frame to update the progress bar!
            yield

            new_id = roi_task["new_id"]
            r_path = roi_task["path"]
            r_state = roi_task["state"]
            vs = controller.view_states[new_id]

            try:
                controller.roi.load_binary_mask(
                    new_id,
                    r_path,
                    name=r_state.get("name"),
                    color=r_state.get("color", [255, 0, 0]),
                    mode=r_state.get("source_mode", "Ignore BG (val)"),
                    target_val=r_state.get("source_val", 0.0),
                )
                # Apply restored states to the newly created ROI
                latest_roi_id = list(vs.rois.keys())[-1]
                vs.rois[latest_roi_id].opacity = r_state.get("opacity", 0.5)
                vs.rois[latest_roi_id].visible = r_state.get("visible", True)
                vs.rois[latest_roi_id].is_contour = r_state.get("is_contour", False)
            except Exception as e:
                warnings.append(f"- Failed to load ROI {os.path.basename(r_path)}: {e}")

    # --- PHASE 6: FINALIZE ---
    for new_id in id_map.values():
        controller.sync.propagate_sync(new_id)
        controller.update_all_viewers_of_image(new_id)

    controller.ui_needs_refresh = True
    gui.on_window_resize()

    if id_map:
        gui.set_context_viewer(controller.viewers["V1"])

    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")
    yield

    # SHOW WORKSPACE WARNINGS
    if warnings:
        gui.show_message(
            "Workspace Warnings",
            "Some files could not be found or loaded:\n\n" + "\n".join(warnings),
        )
        # Yield while the modal is open so the UI doesn't freeze
        while dpg.does_item_exist("generic_message_modal"):
            yield

    hide_loading_modal()


def create_boot_sequence(gui, controller, image_tasks, sync=False, link_all=False):
    import time
    import concurrent.futures

    if not image_tasks:
        return

    total_files = len(image_tasks) + sum(1 for t in image_tasks if t["fusion"])
    warnings = []

    display_name = "Initializing..."
    show_loading_modal("Loading image...", display_name)

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])
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
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(total_files, 8)
    ) as executor:
        future_to_path = {
            executor.submit(controller.file.load_image, path): path for path in jobs
        }
        futures = list(future_to_path.keys())

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

            # Let DearPyGui render a frame
            yield
            time.sleep(0.01)
    # -----------------------------------------------

    show_loading_modal(
        "Loading image...", "Applying synchronization and layouts...", progress=1.0
    )
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

    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")
    yield

    if warnings:
        gui.show_message(
            "Boot Sequence Warning",
            "Some files provided via command line failed to load:\n\n"
            + "\n".join(warnings),
        )
        while dpg.does_item_exist("generic_message_modal"):
            yield

    hide_loading_modal()
