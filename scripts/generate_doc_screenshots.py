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
        img = ImageGrab.grab(bbox=bbox)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        img.save(output_path)
        print(f"Generated: {output_path} ({img.size[0]}x{img.size[1]})")
    else:
        print(f"Error: Could not locate window '{vp_title}' for crop capture.")

    dpg.destroy_context()


def main():
    parser = argparse.ArgumentParser(description="Generate VVV documentation screenshots.")
    parser.add_argument(
        "--target",
        choices=["all", "help_buttons"],
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


if __name__ == "__main__":
    main()

