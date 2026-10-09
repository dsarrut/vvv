#!/usr/bin/env python3
"""
Automated documentation screenshot generator for VVV.

Captures GUI widgets, panels, and application states for inclusion
in the user documentation (`user_docs/images/`).
"""

import os
import sys
import argparse
from pathlib import Path

import dearpygui.dearpygui as dpg
from PIL import ImageGrab

from vvv.core.controller import Controller
from vvv.ui.gui import MainGUI
from vvv.ui.viewer import SliceViewer


def get_window_crop_bounds(window_title, item_min, item_max, padding=6):
    """
    Computes screen pixel bounding box for a DPG item on macOS or Linux/Windows.
    """
    if sys.platform == "darwin":
        from Cocoa import NSApplication

        app = NSApplication.sharedApplication()
        for w in app.windows():
            if w.title() == window_title:
                w.makeKeyAndOrderFront_(None)
                frame = w.frame()
                content_rect = w.contentRectForFrameRect_(frame)
                scale = w.backingScaleFactor()
                screen_h = w.screen().frame().size.height

                win_x = content_rect.origin.x
                win_y = screen_h - (content_rect.origin.y + content_rect.size.height)

                x1 = win_x + item_min[0] - padding
                y1 = win_y + item_min[1] - padding
                x2 = win_x + item_max[0] + padding
                y2 = win_y + item_max[1] + padding

                return (
                    int(round(x1 * scale)),
                    int(round(y1 * scale)),
                    int(round(x2 * scale)),
                    int(round(y2 * scale)),
                )
    else:
        vx, vy = dpg.get_viewport_pos()
        x1 = vx + item_min[0] - padding
        y1 = vy + item_min[1] - padding
        x2 = vx + item_max[0] + padding
        y2 = vy + item_max[1] + padding
        return (int(x1), int(y1), int(x2), int(y2))

    return None


def generate_help_buttons_screenshot(output_path: str):
    """Generates the screenshot showing the two bottom-left help buttons."""
    dpg.create_context()
    controller = Controller()
    controller.use_history = False

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui

    vp_title = "VVV Documentation Screenshot Session"
    dpg.create_viewport(title=vp_title, width=1000, height=700, x_pos=100, y_pos=100)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("PrimaryWindow", True)
    gui.on_window_resize()

    if sys.platform == "darwin":
        from Cocoa import NSApplication

        app = NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)

    # Render enough frames for layout and font rasterization
    for _ in range(25):
        dpg.render_dearpygui_frame()

    b_beg_min = dpg.get_item_rect_min("btn_beginner")
    b_help_max = dpg.get_item_rect_max("btn_help")

    bbox = get_window_crop_bounds(vp_title, b_beg_min, b_help_max, padding=6)
    if bbox:
        img_off = ImageGrab.grab(bbox=bbox)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        img_off.save(output_path)
        print(f"Generated (OFF): {output_path} ({img_off.size[0]}x{img_off.size[1]})")

        # Toggle to ON and capture active state
        gui.on_toggle_beginner_mode("btn_beginner", None, None)
        for _ in range(10):
            dpg.render_dearpygui_frame()

        img_on = ImageGrab.grab(bbox=bbox)
        on_path = str(Path(output_path).with_name("doc_01_help_buttons_on.png"))
        img_on.save(on_path)
        print(f"Generated (ON): {on_path} ({img_on.size[0]}x{img_on.size[1]})")

        # Create combined side-by-side comparison
        from PIL import Image

        spacing = 16
        combined_w = img_off.width + img_on.width + spacing
        combined_h = max(img_off.height, img_on.height)
        combined = Image.new("RGBA", (combined_w, combined_h), (0, 0, 0, 0))
        combined.paste(img_off, (0, 0))
        combined.paste(img_on, (img_off.width + spacing, 0))
        states_path = str(Path(output_path).with_name("doc_01_help_buttons_states.png"))
        combined.save(states_path)
        print(f"Generated (States): {states_path} ({combined_w}x{combined_h})")
    else:
        print(f"Error: Could not locate window '{vp_title}' for crop capture.")

    dpg.destroy_context()


def generate_doc_02_screenshots(img_dir: Path):
    """Generates screenshots for doc_02 (Images, formats, list, and active viewer panel)."""
    dpg.create_context()
    ctrl = Controller()
    ctrl.use_history = False
    for tag in ["V1", "V2", "V3", "V4"]:
        ctrl.viewers[tag] = SliceViewer(tag, ctrl)

    gui = MainGUI(ctrl)
    ctrl.gui = gui

    vp_title = "VVV Doc Session"
    dpg.create_viewport(title=vp_title, width=1280, height=800, x_pos=50, y_pos=50)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("PrimaryWindow", True)
    gui.on_window_resize()

    from vvv.ui.ui_sequences import create_boot_sequence

    tasks = [
        {"base": "data/spect.nii.gz", "base_cmap": None, "fusion": None, "labels": []},
        {"base": "data/ct.nii.gz", "base_cmap": None, "fusion": None, "labels": []},
    ]
    boot_gen = create_boot_sequence(gui, ctrl, tasks)
    list(boot_gen)

    # Set layout: ct.nii.gz on V1 and V2 (top), spect.nii.gz on V3 and V4 (bottom)
    ctrl.layout["V1"] = "2"
    ctrl.layout["V2"] = "2"
    ctrl.layout["V3"] = "1"
    ctrl.layout["V4"] = "1"
    gui.set_context_viewer(ctrl.viewers["V2"])

    import numpy as np
    from vvv.core.view_state import ViewMode

    vs_ct = ctrl.view_states["2"]
    vs_ct.update_crosshair_from_phys(np.array([-32.9, -16.6, 1565.5]))

    # Set camera zoom & pan to show the full body sagittal view like user example
    vs_ct.camera.zoom[("V2", ViewMode.SAGITTAL)] = 2.94
    vs_ct.camera.zoom[ViewMode.SAGITTAL] = 2.94
    vs_ct.camera.pan[("V2", ViewMode.SAGITTAL)] = [-20.0, 180.0]
    vs_ct.camera.pan[ViewMode.SAGITTAL] = [-20.0, 180.0]

    # Clean up status message and any landmarks for clean doc screenshot
    ctrl.status_message = None
    for p in gui.plugins:
        if hasattr(p, "landmarks"):
            p.landmarks.clear()

    if sys.platform == "darwin":
        from Cocoa import NSApplication

        app = NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)

    for _ in range(50):
        ctrl.tick()
        gui._refresh_all_ui_panels()
        gui.update_sidebar_crosshair(gui.context_viewer)
        dpg.render_dearpygui_frame()

    main_w = app.windows()[0]
    main_w.makeKeyAndOrderFront_(None)
    content_rect = main_w.contentRectForFrameRect_(main_w.frame())
    scale = main_w.backingScaleFactor()
    screen_h = main_w.screen().frame().size.height

    win_x = content_rect.origin.x
    win_y = screen_h - (content_rect.origin.y + content_rect.size.height)

    # 1. Full Layout
    bbox_full = (
        int(round(win_x * scale)),
        int(round(win_y * scale)),
        int(round((win_x + content_rect.size.width) * scale)),
        int(round((win_y + content_rect.size.height) * scale)),
    )
    im_full = ImageGrab.grab(bbox=bbox_full)
    im_full.save(img_dir / "doc_02_main_layout.png")
    print(f"Generated: doc_02_main_layout.png ({im_full.size[0]}x{im_full.size[1]})")

    def crop_item(min_pt, max_pt, pad=4):
        x1 = win_x + min_pt[0] - pad
        y1 = win_y + min_pt[1] - pad
        x2 = win_x + max_pt[0] + pad
        y2 = win_y + max_pt[1] + pad
        return (
            int(round(x1 * scale)),
            int(round(y1 * scale)),
            int(round(x2 * scale)),
            int(round(y2 * scale)),
        )

    # 2. Images List
    img_min = dpg.get_item_rect_min("image_list_container")
    img_max = dpg.get_item_rect_max("image_list_container")
    bbox_img = crop_item(img_min, img_max, pad=10)
    im_img = ImageGrab.grab(bbox=bbox_img)
    im_img.save(img_dir / "doc_02_images_list.png")
    print(f"Generated: doc_02_images_list.png ({im_img.size[0]}x{im_img.size[1]})")

    # 3. Active Viewer Info
    av_min = dpg.get_item_rect_min("image_info_group")
    av_max = dpg.get_item_rect_max("image_info_group")
    bbox_av = crop_item(av_min, av_max, pad=10)
    im_av = ImageGrab.grab(bbox=bbox_av)
    im_av.save(img_dir / "doc_02_active_viewer.png")
    print(f"Generated: doc_02_active_viewer.png ({im_av.size[0]}x{im_av.size[1]})")

    dpg.destroy_context()


def generate_doc_03_screenshots(img_dir: Path):
    """Generates screenshots for doc_03 (CLI examples: fusion overlay, label maps)."""
    from vvv.cli import parse_cli_arguments
    from vvv.ui.ui_sequences import create_boot_sequence

    dpg.create_context()
    ctrl = Controller()
    ctrl.use_history = False
    for tag in ["V1", "V2", "V3", "V4"]:
        ctrl.viewers[tag] = SliceViewer(tag, ctrl)

    gui = MainGUI(ctrl)
    ctrl.gui = gui

    vp_title = "VVV CLI Doc Session"
    dpg.create_viewport(title=vp_title, width=1280, height=800, x_pos=50, y_pos=50)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("PrimaryWindow", True)
    gui.on_window_resize()

    tasks = parse_cli_arguments(["data/ct.nii.gz,data/spect.nii.gz,hot,0.6", "+", "data/Sphere_1.nii.gz"])
    boot_gen = create_boot_sequence(gui, ctrl, tasks)
    for _ in boot_gen:
        ctrl.tick()
        dpg.render_dearpygui_frame()

    from vvv.core.view_state import ViewMode
    import numpy as np

    vs_ct = ctrl.view_states["2"]
    vs_ct.update_crosshair_from_phys(np.array([-32.9, -16.6, 1690.0]))
    vs_ct.camera.zoom[("V2", ViewMode.SAGITTAL)] = 2.94
    vs_ct.camera.zoom[ViewMode.SAGITTAL] = 2.94
    vs_ct.camera.pan[("V2", ViewMode.SAGITTAL)] = [-20.0, 180.0]
    vs_ct.camera.pan[ViewMode.SAGITTAL] = [-20.0, 180.0]

    ctrl.status_message = None

    if sys.platform == "darwin":
        from Cocoa import NSApplication

        app = NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)

    for _ in range(50):
        ctrl.tick()
        gui._refresh_all_ui_panels()
        gui.update_sidebar_crosshair(gui.context_viewer)
        dpg.render_dearpygui_frame()

    main_w = app.mainWindow() or app.keyWindow()
    if main_w is None or main_w.frame().size.width < 800:
        for w in app.windows():
            if w.frame().size.width >= 1000 and w.isVisible():
                main_w = w
                break

    main_w.makeKeyAndOrderFront_(None)
    content_rect = main_w.contentRectForFrameRect_(main_w.frame())
    scale = main_w.backingScaleFactor()
    screen_h = main_w.screen().frame().size.height

    win_x = content_rect.origin.x
    win_y = screen_h - (content_rect.origin.y + content_rect.size.height)

    bbox_full = (
        int(round(win_x * scale)),
        int(round(win_y * scale)),
        int(round((win_x + content_rect.size.width) * scale)),
        int(round((win_y + content_rect.size.height) * scale)),
    )
    im_full = ImageGrab.grab(bbox=bbox_full)
    im_full.save(img_dir / "doc_03_cli_fusion.png")
    print(f"Generated: doc_03_cli_fusion.png ({im_full.size[0]}x{im_full.size[1]})")

    dpg.destroy_context()


def main():
    parser = argparse.ArgumentParser(description="Generate VVV documentation screenshots.")
    parser.add_argument(
        "--target",
        choices=["all", "help_buttons", "doc_02", "doc_03"],
        default="all",
        help="Target screenshot(s) to generate (default: all)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    img_dir = project_root / "user_docs" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    if args.target in ("all", "help_buttons"):
        help_btn_img = img_dir / "doc_01_help_buttons.png"
        generate_help_buttons_screenshot(str(help_btn_img))

    if args.target in ("all", "doc_02"):
        generate_doc_02_screenshots(img_dir)

    if args.target in ("all", "doc_03"):
        generate_doc_03_screenshots(img_dir)


if __name__ == "__main__":
    main()

