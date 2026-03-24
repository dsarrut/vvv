import os
import json
import shlex
import dearpygui.dearpygui as dpg
from vvv.config import ROI_COLORS
from vvv.utils import ViewMode, resolve_relative_path


def load_single_image_sequence(gui, controller, file_path):
    is_4d = file_path.startswith("4D:")
    display_name = "4D Sequence" if is_4d else os.path.basename(file_path)

    with dpg.window(
        tag="loading_modal",
        modal=True,
        show=True,
        no_title_bar=True,
        no_resize=True,
        no_move=True,
        width=350,
        height=100,
    ):
        dpg.add_text(f"Loading image...\n{display_name}", tag="loading_text")
        dpg.add_spacer(height=5)
        dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.5)

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])

    for _ in range(3):
        yield

    try:
        img_id = controller.file.load_image(file_path)

        if dpg.does_item_exist("loading_text"):
            dpg.set_value("loading_text", "Applying synchronization and layouts...")
        if dpg.does_item_exist("loading_progress"):
            dpg.set_value("loading_progress", 1.0)
        yield

        target_viewer = (
            gui.context_viewer if gui.context_viewer else controller.viewers["V1"]
        )
        target_viewer.set_image(img_id)

        empty_viewers = [v for v in controller.viewers.values() if v.image_id is None]
        if empty_viewers:
            controller.default_viewers_orientation()
            for v in empty_viewers:
                v.set_image(img_id)

        same_image_viewers = [
            v.tag for v in controller.viewers.values() if v.image_id == img_id
        ]
        if same_image_viewers:
            controller.sync.propagate_ppm(same_image_viewers)

        gui.set_context_viewer(target_viewer)
        gui.refresh_image_list_ui()
        gui.refresh_rois_ui()

        if dpg.does_item_exist("loading_modal"):
            dpg.delete_item("loading_modal")
        yield

    except Exception as e:
        if dpg.does_item_exist("loading_modal"):
            dpg.delete_item("loading_modal")
        yield
        gui.show_message("File Load Error", f"Failed to load image:\n{display_name}")
        while dpg.does_item_exist("generic_message_modal"):
            yield


def load_batch_images_sequence(gui, controller, file_paths):
    total_files = len(file_paths)
    warnings = []

    with dpg.window(
        tag="loading_modal",
        modal=True,
        show=True,
        no_title_bar=True,
        no_resize=True,
        no_move=True,
        width=350,
        height=100,
    ):
        dpg.add_text(f"Loading {total_files} images...", tag="loading_text")
        dpg.add_spacer(height=5)
        dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.0)

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])
    yield

    loaded_ids = []
    for i, path in enumerate(file_paths):

        if isinstance(path, (list, tuple)) and len(path) > 0:
            filename = os.path.basename(os.path.dirname(path[0])) + " (DICOM Series)"
            path = list(path)  # Force it to a list for VolumeData
        else:
            filename = os.path.basename(path)

        if dpg.does_item_exist("loading_text"):
            dpg.set_value("loading_text", f"Loading ({i+1}/{total_files}):\n{filename}")
        if dpg.does_item_exist("loading_progress"):
            dpg.set_value("loading_progress", i / total_files)
        yield

        try:
            img_id = controller.file.load_image(path)
            loaded_ids.append(img_id)
        except Exception as e:
            warnings.append(f"- {filename}: {e}")
        yield

    if dpg.does_item_exist("loading_text"):
        dpg.set_value("loading_text", "Applying layouts...")
    if dpg.does_item_exist("loading_progress"):
        dpg.set_value("loading_progress", 1.0)
    yield

    if loaded_ids:
        target_viewer = (
            gui.context_viewer if gui.context_viewer else controller.viewers["V1"]
        )
        target_viewer.set_image(loaded_ids[0])

        empty_viewers = [v for v in controller.viewers.values() if v.image_id is None]
        if empty_viewers:
            controller.default_viewers_orientation()
            for v in empty_viewers:
                v.set_image(loaded_ids[0])

        gui.set_context_viewer(target_viewer)
        gui.refresh_image_list_ui()
        gui.refresh_rois_ui()

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


def load_batch_rois_sequence(
    gui,
    controller,
    base_image_id,
    file_paths,
    roi_type="Binary Mask",
    mode="Ignore BG (val)",
    val=0.0,
):
    total_files = len(file_paths)
    warnings = []

    with dpg.window(
        tag="loading_modal",
        modal=True,
        show=True,
        no_title_bar=True,
        no_resize=True,
        no_move=True,
        width=350,
        height=100,
    ):
        dpg.add_text(f"Loading {total_files} ROIs...", tag="loading_text")
        dpg.add_spacer(height=5)
        dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.0)

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])
    yield

    vs = controller.view_states[base_image_id]
    color_idx = len(vs.rois)

    for i, path in enumerate(file_paths):
        if not os.path.exists(path):
            continue

        filename = os.path.basename(path)
        if dpg.does_item_exist("loading_text"):
            dpg.set_value(
                "loading_text", f"Loading ROI ({i+1}/{total_files}):\n{filename}"
            )
        if dpg.does_item_exist("loading_progress"):
            dpg.set_value("loading_progress", i / total_files)
        yield

        try:
            if roi_type == "Binary Mask":
                color = ROI_COLORS[color_idx % len(ROI_COLORS)]
                controller.roi.load_binary_mask(
                    base_image_id, path, color=color, mode=mode, target_val=val
                )
                color_idx += 1
            elif roi_type == "Label Map":
                loaded = controller.load_label_map(base_image_id, path, color_idx)
                color_idx += loaded
        except Exception as e:
            warnings.append(f"- {filename}: {e}")
            # print(f"Failed to load ROI {filename}: {e}")
        yield

    if dpg.does_item_exist("loading_text"):
        dpg.set_value("loading_text", "Applying ROIs...")
    if dpg.does_item_exist("loading_progress"):
        dpg.set_value("loading_progress", 1.0)
    yield

    vs = controller.view_states[base_image_id]
    if vs.rois:
        gui.active_roi_id = list(vs.rois.keys())[-1]

    gui.refresh_rois_ui()
    controller.update_all_viewers_of_image(base_image_id)

    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")
    yield

    if warnings:
        gui.show_message(
            "ROI Import Warning", "Some ROIs were skipped:\n\n" + "\n".join(warnings)
        )
        while dpg.does_item_exist("generic_message_modal"):
            yield


def load_workspace_sequence(gui, controller, filepath):
    """Safely restores a full workspace using ID mapping and strict hierarchy."""
    import os
    import json
    from vvv.utils import ViewMode

    try:
        with open(filepath, "r") as f:
            ws = json.load(f)
    except Exception as e:
        gui.show_status_message(f"Failed to load workspace: {e}")
        return

    with dpg.window(
        tag="loading_modal",
        modal=True,
        show=True,
        no_title_bar=True,
        no_resize=True,
        no_move=True,
        width=350,
        height=100,
    ):
        dpg.add_text("Loading Workspace Bases...", tag="loading_text")
        dpg.add_spacer(height=5)
        dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.0)

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])
    yield

    if dpg.does_item_exist("loading_text"):
        dpg.set_value("loading_text", "Loading Workspace Bases...")
    yield

    id_map = {}  # Maps old JSON vs_id to the newly assigned vs_id

    # PHASE 1: Load Base Images & Apply Intrinsic State
    for old_id, img_data in ws.get("images", {}).items():
        path = img_data.get("path")
        if path and os.path.exists(path):
            new_id = controller.file.load_image(path)
            id_map[old_id] = new_id

            vs = controller.view_states[new_id]
            vs.display.from_dict(img_data.get("display", {}))
            vs.camera.from_dict(img_data.get("camera", {}))
            vs.sync_group = img_data.get("sync_group", 0)
        yield

    # PHASE 2: Map Viewers to the New Bases
    for tag, v_data in ws.get("viewers", {}).items():
        old_img_id = v_data.get("image_id")
        if old_img_id in id_map:
            new_id = id_map[old_img_id]
            viewer = controller.viewers[tag]
            viewer.set_image(new_id)
            viewer.set_orientation(ViewMode[v_data["orientation"]])
            viewer.zoom = v_data.get("zoom", 1.0)
            viewer.pan_offset = v_data.get("pan_offset", [0, 0])
            viewer.needs_recenter = v_data.get("needs_recenter", False)
    yield

    if dpg.does_item_exist("loading_text"):
        dpg.set_value("loading_text", "Restoring Overlays and ROIs...")

    total_images = len(ws.get("images", {}))  # Get the total count!
    current_image = 0

    # PHASE 3: Load Overlays and ROIs
    for old_id, img_data in ws.get("images", {}).items():
        current_image += 1
        if old_id not in id_map:
            continue
        new_id = id_map[old_id]
        vs = controller.view_states[new_id]

        # 3A: Overlay
        ov_info = img_data.get("overlay")
        if ov_info and os.path.exists(ov_info["path"]):
            ov_id = controller.file.load_image(ov_info["path"])
            controller.volumes[ov_id].is_overlay_only = True
            ov_vs = controller.view_states[ov_id]
            ov_vs.display.colormap = ov_info.get("colormap", "Grayscale")
            vs.set_overlay(ov_id, controller.volumes[ov_id])
            vs.display.overlay_mode = ov_info.get("mode", "Registration")
            vs.display.overlay_opacity = ov_info.get("opacity", 0.5)

        # Update progress bar!
        if dpg.does_item_exist("loading_progress"):
            dpg.set_value("loading_progress", (current_image - 0.5) / total_images)
        yield

        # 3B: ROIs
        for roi_data in img_data.get("rois", []):
            r_path = roi_data.get("path")
            r_state = roi_data.get("state", {})
            if r_path and os.path.exists(r_path):
                controller.roi.load_binary_mask(
                    new_id,
                    r_path,
                    name=r_state.get("name"),
                    color=r_state.get("color", [255, 0, 0]),
                    mode=r_state.get("source_mode", "Ignore BG (val)"),
                    target_val=r_state.get("source_val", 0.0),
                )
                latest_roi_id = list(vs.rois.keys())[-1]
                vs.rois[latest_roi_id].opacity = r_state.get("opacity", 0.5)
                vs.rois[latest_roi_id].visible = r_state.get("visible", True)
                vs.rois[latest_roi_id].is_contour = r_state.get("is_contour", False)

        # Update progress bar!
        if dpg.does_item_exist("loading_progress"):
            dpg.set_value("loading_progress", current_image / total_images)
        yield

    # PHASE 4: Finalize Synchronization
    for new_id in id_map.values():
        controller.sync.propagate_sync(new_id)
        controller.update_all_viewers_of_image(new_id)

    gui.refresh_image_list_ui()
    gui.refresh_rois_ui()
    gui.refresh_sync_ui()
    gui.on_window_resize()

    if id_map:
        gui.set_context_viewer(controller.viewers["V1"])

    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")
    yield


def create_boot_sequence(gui, controller, image_tasks, sync=False, link_all=False):
    if not image_tasks:
        return
    total_files = len(image_tasks) + sum(1 for t in image_tasks if t["fusion"])
    warnings = []

    with dpg.window(
        tag="loading_modal",
        modal=True,
        show=True,
        no_title_bar=True,
        no_resize=True,
        no_move=True,
        width=350,
        height=100,
    ):
        dpg.add_text("Initializing...", tag="loading_text")
        dpg.add_spacer(height=5)
        dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.0)

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])
    yield

    loaded_ids, files_processed = [], 0
    id_to_group = {}

    for task in image_tasks:
        base_path = task["base"]
        filename = os.path.basename(base_path)
        sync_group = task.get("sync_group", 0)

        if dpg.does_item_exist("loading_text"):
            dpg.set_value("loading_text", f"Loading base...\n{filename}")
        if dpg.does_item_exist("loading_progress"):
            dpg.set_value("loading_progress", files_processed / total_files)
        yield

        try:
            base_id = controller.file.load_image(base_path)
            loaded_ids.append(base_id)
            id_to_group[base_id] = sync_group

            if task.get("base_cmap"):
                controller.view_states[base_id].display.colormap = task["base_cmap"]
                controller.view_states[base_id].is_data_dirty = True

            files_processed += 1
        except Exception as e:
            # gui.show_message("Load Error", f"Failed to load:\n{filename}")
            warnings.append(f"{filename}")
            yield
            continue

        if task["fusion"]:
            fuse_path = task["fusion"]["path"]
            fuse_name = os.path.basename(fuse_path)

            if dpg.does_item_exist("loading_text"):
                dpg.set_value("loading_text", f"Resampling overlay...\n{fuse_name}")
            if dpg.does_item_exist("loading_progress"):
                dpg.set_value("loading_progress", files_processed / total_files)
            yield

            try:
                fuse_id = controller.file.load_image(fuse_path)
                loaded_ids.append(fuse_id)
                id_to_group[fuse_id] = sync_group
                files_processed += 1

                fuse_vs = controller.view_states[fuse_id]
                fuse_vs.display.colormap = task["fusion"]["cmap"]
                fuse_vs.is_data_dirty = True

                base_vs = controller.view_states[base_id]
                base_vs.set_overlay(fuse_id, fuse_vs.volume)
                base_vs.overlay_opacity = task["fusion"]["opacity"]
                base_vs.overlay_threshold = task["fusion"]["threshold"]

                if "mode" in task["fusion"]:
                    base_vs.display.overlay_mode = task["fusion"]["mode"]

            except Exception as e:
                # gui.show_message("Overlay Error", f"Failed to load/fuse:\n{fuse_name}")
                warnings.append(f"- Overlay: {fuse_name}")
                yield
                continue

    if dpg.does_item_exist("loading_text"):
        dpg.set_value("loading_text", "Applying synchronization and layouts...")
    if dpg.does_item_exist("loading_progress"):
        dpg.set_value("loading_progress", 1.0)
    yield

    controller.default_viewers_orientation()

    for i, img_id in enumerate(loaded_ids):
        if i == 0:
            for tag in ["V1", "V2", "V3", "V4"]:
                controller.viewers[tag].set_image(img_id)
        elif i == 1:
            controller.viewers["V3"].set_image(img_id)
            controller.viewers["V4"].set_image(img_id)
        elif i == 2:
            controller.viewers["V2"].set_image(loaded_ids[1])
            controller.viewers["V3"].set_image(img_id)
            controller.viewers["V4"].set_image(img_id)
        elif i >= 3:
            controller.viewers["V4"].set_image(img_id)

    for img_id in loaded_ids:
        same_viewers = [
            v.tag for v in controller.viewers.values() if v.image_id == img_id
        ]
        if same_viewers:
            controller.sync.propagate_ppm(same_viewers)

    group_applied = False
    for img_id in loaded_ids:
        if sync or link_all:
            gui.on_sync_group_change(None, "Group 1", img_id)
            group_applied = True
        elif id_to_group.get(img_id, 0) > 0:
            gui.on_sync_group_change(None, f"Group {id_to_group[img_id]}", img_id)
            group_applied = True

    if group_applied:
        gui.refresh_sync_ui()

    gui.on_window_resize()
    gui.set_context_viewer(controller.viewers["V1"])
    gui.refresh_image_list_ui()
    gui.refresh_rois_ui()

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
