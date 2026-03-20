import os
import time
import json
import shlex
import dearpygui.dearpygui as dpg

from vvv.utils import ViewMode, resolve_relative_path, resolve_history_path_key
from vvv.config import ROI_COLORS


def load_history_rois_sequence(gui, controller, img_id):
    """Yielding generator to animate the progress bar while restoring ROIs."""
    if not controller.use_history:
        return

    vol = controller.volumes[img_id]
    vs = controller.view_states[img_id]

    history_entry = controller.history.get_image_state(vol)
    if not history_entry or not history_entry.get("rois"):
        return

    rois = history_entry["rois"]
    total_rois = len(rois)

    for i, roi_data in enumerate(rois):
        roi_path = resolve_history_path_key(roi_data["path"])
        filename = os.path.basename(roi_path)

        if dpg.does_item_exist("loading_text"):
            dpg.set_value(
                "loading_text", f"Restoring ROI ({i+1}/{total_rois}):\n{filename}"
            )
        if dpg.does_item_exist("loading_progress"):
            dpg.set_value("loading_progress", i / total_rois)

        time.sleep(0.05)
        yield  # Forces the UI to visually update!

        if os.path.exists(roi_path):
            try:
                # Safely extract the original rules from the history save
                mode = roi_data["state"].get("source_mode", "Ignore BG (val)")
                val = roi_data["state"].get("source_val", 0.0)
                new_roi_id = controller.load_binary_mask(
                    img_id, roi_path, mode=mode, target_val=val
                )
                vs.rois[new_roi_id].from_dict(roi_data["state"])
            except Exception as e:
                print(f"Failed to restore ROI {filename}: {e}")
        yield


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
        img_id = controller.load_image(file_path)
        yield from load_history_rois_sequence(gui, controller, img_id)

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
            controller.unify_ppm(same_image_viewers)

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
            img_id = controller.load_image(path)
            loaded_ids.append(img_id)
            yield from load_history_rois_sequence(gui, controller, img_id)
        except Exception as e:
            print(f"Failed to load {filename}: {e}")
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
                controller.load_binary_mask(
                    base_image_id, path, color=color, mode=mode, target_val=val
                )
                color_idx += 1
            elif roi_type == "Label Map":
                loaded = controller.load_label_map(base_image_id, path, color_idx)
                color_idx += loaded
        except Exception as e:
            print(f"Failed to load ROI {filename}: {e}")
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


def load_workspace_sequence(gui, controller, file_path):
    with open(file_path, "r") as f:
        data = json.load(f)

    workspace_dir = os.path.dirname(file_path)

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
        dpg.add_text("Cleaning up current session...", tag="loading_text")
        dpg.add_spacer(height=5)
        dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.0)

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])
    yield

    for vs_id in list(controller.view_states.keys()):
        controller.close_image(vs_id)
    yield

    prev_history = getattr(controller, "use_history", True)
    controller.use_history = False

    id_mapping = {}
    vols_data = data.get("volumes", {})
    total_vols = max(1, len(vols_data))
    processed = 0

    for old_id, v_data in vols_data.items():
        raw_path = v_data["path"]

        if isinstance(raw_path, list) and len(raw_path) > 0:
            filename = (
                os.path.basename(os.path.dirname(raw_path[0])) + " (DICOM Series)"
            )
        else:
            filename = os.path.basename(raw_path)

        if dpg.does_item_exist("loading_text"):
            dpg.set_value("loading_text", f"Loading volume...\n{filename}")
            dpg.set_value("loading_progress", processed / total_vols)
        yield

        if isinstance(raw_path, list):
            full_path = [resolve_relative_path(p, workspace_dir) for p in raw_path]
        elif isinstance(raw_path, str) and raw_path.startswith("4D:"):
            tokens = shlex.split(raw_path[3:].strip())
            abs_paths = [resolve_relative_path(p, workspace_dir) for p in tokens]
            full_path = "4D:" + " ".join(f'"{p}"' for p in abs_paths)
        else:
            full_path = resolve_relative_path(raw_path, workspace_dir)

        try:
            new_id = controller.load_image(full_path, is_auto_overlay=True)
            id_mapping[old_id] = new_id

            vs = controller.view_states[new_id]
            vs.sync_group = v_data.get("sync_group", 0)
            vs.camera.from_dict(v_data["camera"])
            vs.display.from_dict(v_data["display"])
            vs.is_data_dirty = True
        except Exception as e:
            print(f"Failed to load workspace volume: {full_path}")

        processed += 1
        yield

    if dpg.does_item_exist("loading_text"):
        dpg.set_value("loading_text", "Re-linking fusions and layouts...")
        dpg.set_value("loading_progress", 1.0)
    yield

    for old_id, v_data in vols_data.items():
        old_ov = v_data.get("overlay_id")
        if old_ov and old_ov in id_mapping and old_id in id_mapping:
            base_id = id_mapping[old_id]
            over_id = id_mapping[old_ov]
            controller.view_states[base_id].set_overlay(
                over_id, controller.volumes[over_id]
            )

        for roi_data in v_data.get("rois", []):
            abs_path = resolve_relative_path(roi_data["path"], workspace_dir)
            if os.path.exists(abs_path):
                try:
                    new_roi_id = controller.load_binary_mask(base_id, abs_path)
                    controller.view_states[base_id].rois[new_roi_id].from_dict(
                        roi_data["state"]
                    )
                except Exception as e:
                    print(f"Failed to load workspace ROI {abs_path}: {e}")

    for v_tag, v_data in data.get("viewers", {}).items():
        viewer = controller.viewers[v_tag]
        old_img_id = v_data.get("image_id")

        if old_img_id and old_img_id in id_mapping:
            viewer.set_image(id_mapping[old_img_id])
        else:
            viewer.drop_image()

        viewer.set_orientation(ViewMode[v_data.get("orientation", "AXIAL")])

    controller.use_history = prev_history
    gui.refresh_image_list_ui()
    gui.refresh_sync_ui()
    gui.set_context_viewer(controller.viewers["V1"])

    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")
    yield


def create_boot_sequence(gui, controller, image_tasks, sync=False, link_all=False):
    if not image_tasks:
        return
    total_files = len(image_tasks) + sum(1 for t in image_tasks if t["fusion"])

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
            base_id = controller.load_image(base_path)
            loaded_ids.append(base_id)
            id_to_group[base_id] = sync_group

            yield from load_history_rois_sequence(gui, controller, base_id)

            if task.get("base_cmap"):
                controller.view_states[base_id].colormap = task["base_cmap"]
                controller.view_states[base_id].is_data_dirty = True

            files_processed += 1
        except Exception as e:
            gui.show_message("Load Error", f"Failed to load:\n{filename}")
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
                fuse_id = controller.load_image(fuse_path)
                loaded_ids.append(fuse_id)
                id_to_group[fuse_id] = sync_group
                files_processed += 1

                fuse_vs = controller.view_states[fuse_id]
                fuse_vs.colormap = task["fusion"]["cmap"]
                fuse_vs.is_data_dirty = True

                base_vs = controller.view_states[base_id]
                base_vs.set_overlay(fuse_id, fuse_vs.volume)
                base_vs.overlay_opacity = task["fusion"]["opacity"]
                base_vs.overlay_threshold = task["fusion"]["threshold"]

                if "mode" in task["fusion"]:
                    base_vs.overlay_mode = task["fusion"]["mode"]

            except Exception as e:
                gui.show_message("Overlay Error", f"Failed to load/fuse:\n{fuse_name}")
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
            controller.unify_ppm(same_viewers)

    group_applied = False
    for img_id in loaded_ids:
        if sync or link_all:
            controller.on_sync_group_change(None, "Group 1", img_id)
            group_applied = True
        elif id_to_group.get(img_id, 0) > 0:
            controller.on_sync_group_change(
                None, f"Group {id_to_group[img_id]}", img_id
            )
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
