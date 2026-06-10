#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import click
from vvv.ui.gui import MainGUI
import dearpygui.dearpygui as dpg
from vvv.ui.viewer import SliceViewer
from vvv.maths.image import VolumeData
from vvv.core.controller import Controller
from vvv.resources import get_resource_path


def set_macos_dock_info(name, icon_path=None):
    """Promotes script, sets focus, icon, process name, and fixes Cmd+Q."""
    if sys.platform != "darwin":
        return

    try:
        import setproctitle

        setproctitle.setproctitle(name)
    except ImportError:
        pass

    try:
        from Cocoa import (  # type: ignore
            NSApplication,  # type: ignore
            NSImage,  # type: ignore
            NSApplicationActivationPolicyRegular,  # type: ignore
            NSMenu,  # type: ignore
            NSMenuItem,  # type: ignore
        )

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)

        main_menu = NSMenu.alloc().init()
        app.setMainMenu_(main_menu)

        app_menu_item = NSMenuItem.alloc().init()
        main_menu.addItem_(app_menu_item)

        app_menu = NSMenu.alloc().init()
        app_menu_item.setSubmenu_(app_menu)

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Quit {name}", "terminate:", "q"
        )
        app_menu.addItem_(quit_item)

        if icon_path and os.path.exists(icon_path):
            image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
            app.setApplicationIconImage_(image)

    except ImportError:
        pass


def parse_cli_arguments(datasets):
    """
    Parses raw command line arguments into structured image tasks.
    Handles shell-expanded 4D sequences, sync groups, and comma-separated fusion parameters.
    Automatically breaks 4D sequences if image size/spacing changes.
    Supports '+' prefix or separator to attach label map ROIs to base images.
    """
    import numpy as np
    import SimpleITK as sitk

    # 1. Normalize datasets by splitting any tokens containing '+'
    normalized_datasets = []
    for item in datasets:
        if item == "+":
            normalized_datasets.append("+")
        elif "+" in item:
            parts = item.split("+")
            for i, part in enumerate(parts):
                if i > 0:
                    normalized_datasets.append("+")
                if part:
                    normalized_datasets.append(part)
        else:
            normalized_datasets.append(item)

    # 2. Extract label maps associated with base images
    clean_datasets = []
    labels_for_path = {}  # maps base_path -> list of label paths
    current_base = None
    expect_label = False

    for item in normalized_datasets:
        if item == "+":
            expect_label = True
            continue
        
        if expect_label:
            if current_base:
                labels_for_path.setdefault(current_base, []).append(item)
            expect_label = False
        else:
            clean_datasets.append(item)
            current_base = item

    def get_info(path):
        """Ultra-fast header peek without loading pixel data."""
        try:
            reader = sitk.ImageFileReader()
            reader.SetFileName(path)
            reader.ReadImageInformation()
            return reader.GetSize(), reader.GetSpacing()
        except Exception:
            return None, None

    grouped_datasets = []
    buf = []
    in_4d = False
    ref_size = None
    ref_spacing = None

    def flush():
        nonlocal buf, in_4d, ref_size, ref_spacing
        if buf:
            grouped_datasets.append(" ".join(buf))
            buf = []
        in_4d = False
        ref_size = None
        ref_spacing = None

    # 3. Re-group shell-split arguments dynamically
    seq_prefixes = VolumeData.SEQUENCE_PREFIXES
    for item in clean_datasets:
        is_4d_tag = item.upper() in seq_prefixes
        clean_item = item.rstrip(",:")

        expecting_more = len(buf) > 0 and (
            buf[-1].endswith(",")
            or (buf[-1].endswith(":") and not buf[-1].upper().startswith(seq_prefixes))
        )

        if item.lower() in ("//", "::", "stop:", "end:"):
            flush()
            continue

        if is_4d_tag:
            if in_4d and not expecting_more:
                flush()
            in_4d = True
            buf.append(item)
            continue

        if in_4d and not expecting_more:
            if os.path.isfile(clean_item):
                size, spacing = get_info(clean_item)
                if size is not None:
                    if ref_size is None:
                        ref_size = size
                        ref_spacing = spacing
                        buf.append(item)
                    else:
                        if size == ref_size and spacing is not None and ref_spacing is not None and np.allclose(
                            spacing, ref_spacing, atol=1e-3
                        ):
                            buf.append(item)
                        else:
                            flush()
                            buf.append(item)
                else:
                    buf.append(item)
            else:
                buf.append(item)
        else:
            if not expecting_more and len(buf) > 0:
                flush()
            buf.append(item)

    flush()

    # 4. Parse the composite strings into tasks
    image_tasks = []

    known_cmaps = {
        "grayscale": "Grayscale",
        "hot": "Hot",
        "cold": "Cold",
        "jet": "Jet",
        "dosimetry": "Dosimetry",
        "segmentation": "Segmentation",
    }

    for ds in grouped_datasets:
        parts = [p.strip() for p in ds.split(",")]
        base_part = parts[0]
        sync_group = 0

        match = re.match(r"^(\d+):\s*(.*)$", base_part)
        if match:
            sync_group = int(match.group(1))
            base_part = match.group(2)

        task = {
            "base": base_part,
            "fusion": None,
            "sync_group": sync_group,
            "base_cmap": None,
            "labels": [],
        }

        if len(parts) > 1:
            overlay_path = parts[1].strip()
            cmap_input = parts[2].strip() if len(parts) > 2 else "Jet"
            mode = "Alpha"

            cmap_lower = cmap_input.lower()
            if cmap_lower in ["reg", "registration"]:
                cmap = "Grayscale"
                mode = "Registration"
            else:
                cmap = known_cmaps.get(cmap_lower, cmap_input.capitalize())

            if overlay_path:
                task["fusion"] = {
                    "path": overlay_path,
                    "cmap": cmap,
                    "mode": mode,
                    "opacity": float(parts[3]) if len(parts) > 3 else 0.5,
                    "threshold": float(parts[4]) if len(parts) > 4 else 0.0,
                }
            else:
                task["base_cmap"] = cmap
                if len(parts) > 4:
                    task["min_threshold"] = float(parts[4])

        # Associate labels with this task
        for path, lbls in labels_for_path.items():
            if path in ds:
                task["labels"].extend(lbls)

        image_tasks.append(task)

    return image_tasks


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.argument("datasets", nargs=-1)
# --linkall is kept as a legacy alias from the old `vv` application; --sync is the preferred form.
@click.option("--linkall", "-l", is_flag=True, help="Enable spatial sync for all images (legacy alias for --sync)")
@click.option("--sync", "-s", is_flag=True, help="Enable spatial sync for all images at startup")
@click.option("--linkall-wl", "-lw", is_flag=True, help="Enable Window/Level sync for all images at startup")
@click.option(
    "--no-history",
    "-nh",
    is_flag=True,
    help="Ignore saved history and load with defaults.",
)
@click.option("--debug", is_flag=True, help="Show FPS debug overlay with graph.")
@click.option("--fast-gl/--no-fast-gl", default=True, help="Enable/disable fast GL nearest-neighbor (Linux/Windows).")
def main(no_history, datasets, linkall, sync, linkall_wl, debug, fast_gl):
    """VVV — multi-image medical viewer.

    \b
    BASIC USAGE
      vvv image.mhd
      vvv ct.mhd spect.nii dose.nii        load multiple images side by side

    \b
    OVERLAY SYNTAX  (comma-separated fields, attached to the base image)
      vvv base.nii,overlay.nii             alpha overlay, Jet colormap, opacity 0.5
      vvv base.nii,overlay.nii,hot         colormaps: grayscale hot cold jet dosimetry segmentation
      vvv base.nii,overlay.nii,jet,0.7     custom opacity (0.0–1.0)
      vvv base.nii,overlay.nii,jet,0.5,100 minimum display threshold on the overlay
      vvv base.nii,overlay.nii,reg         registration mode: linked W/L, grayscale colormaps
      vvv base.nii,,hot                    apply colormap to base image only (empty overlay slot)

    \b
    SYNC GROUPS
      vvv 1:ct.mhd 1:spect.nii            assign images to spatial sync group 1 (pan/zoom/slice)
      vvv 1:ct.mhd 2:mri.nii              two separate sync groups
      vvv ct.mhd spect.nii --sync          link all images spatially at startup
      vvv ct.mhd spect.nii --linkall-wl    link all images by Window/Level at startup
      vvv ct.mhd spect.nii -s -lw          link both spatial and W/L at startup

    \b
    4D SEQUENCES
      vvv 4D frame1.nii frame2.nii ...    explicit 4D stack (use // to end the sequence)
      vvv frame*.nii                       shell glob: auto-grouped if same size and spacing

    \b
    LABEL MAPS / ROIs
      vvv ct.nii.gz + labels.nii.gz        load labels.nii.gz as ROIs on ct.nii.gz

    \b
    WORKSPACE
      vvv session.vvw                      restore a previously saved workspace
    """

    # Check dearpygui version compatibility
    try:
        import dearpygui
        dpg_ver = dearpygui.__version__
        parts = [int(p) for p in dpg_ver.split(".") if p.isdigit()]
        if parts and (parts[0] < 2 or (parts[0] == 2 and len(parts) > 1 and parts[1] < 3)):
            print(
                f"WARNING: dearpygui version {dpg_ver} is detected. Version >= 2.3.1 is highly recommended "
                f"to prevent segmentation faults/crashes, particularly under Python 3.14+ or in headless environments.",
                file=sys.stderr
            )
    except Exception:
        pass

    # Parse the tasks cleanly
    datasets = [ds for ds in datasets if ds.strip()]
    image_tasks = parse_cli_arguments(datasets)

    import vvv.ui.render_strategy as rs_mod
    if fast_gl:
        import platform as _platform
        rs_mod.GL_NEAREST_SUPPORTED = _platform.system() in ("Linux", "Windows")
    else:
        rs_mod.GL_NEAREST_SUPPORTED = False

    # --- Setup Application ---
    icon_png = get_resource_path(os.path.join("icons", "py_vv.png"))
    icon_ico = get_resource_path(os.path.join("icons", "py_vv.ico"))
    set_macos_dock_info("VVV", icon_path=icon_png)

    dpg.create_context()
    controller = Controller()

    controller.use_history = not no_history

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui
    win_w = controller.settings.data["layout"]["window_width"]
    win_h = controller.settings.data["layout"]["window_height"]

    dpg.create_viewport(title="VVV", width=win_w, height=win_h)

    active_icon = icon_ico if sys.platform == "win32" else icon_png
    dpg.set_viewport_small_icon(active_icon)
    dpg.set_viewport_large_icon(active_icon)

    # 1. Detect if a workspace file was passed in the arguments
    workspace_file = next((f for f in datasets if f.lower().endswith(".vvw")), None)

    # 2. Swap the boot generator based on the file type
    if workspace_file:
        if len(datasets) > 1:
            print(
                f"Find workspace {workspace_file}, ignoring other files on the command line"
            )
        # Use the workspace loader
        boot_gen = gui.load_workspace_sequence(workspace_file)
    else:
        # Standard image loading sequence
        boot_gen = gui.create_boot_sequence(image_tasks, sync, linkall, linkall_wl)

    # 3. Run the application
    gui.run(boot_generator=boot_gen, debug=debug)


if __name__ == "__main__":
    main()
