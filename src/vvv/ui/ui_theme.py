import sys
import dearpygui.dearpygui as dpg
import os
import logging

from vvv.utils import get_resource_path

logger = logging.getLogger(__name__)

TOOLTIP_DELAY_NORMAL = 0.6
TOOLTIP_DELAY_BEGINNER = 0.1


def build_ui_config(controller):
    """Centralizes all layout dimensions, margins, and colors."""
    shared_margin = 7
    is_mac = sys.platform == "darwin"

    # macOS uses Helvetica (14/11 px), Linux/Windows uses Liberation Sans (16.24/13 px)
    # With larger fonts and wider line height on Linux/Windows, panels need slightly more vertical room
    # Sized so the bottom space below the last control matches the top space (~10 px)
    av_h = 345 if is_mac else 378  # Active Viewer Height
    ch_h = 160 if is_mac else 178  # Crosshair Height
    nav_w = controller.settings.data["layout"]["nav_panel_width"]
    if not is_mac:
        nav_w = max(nav_w, 90)
    item_gap = 6 if is_mac else 8

    return {
        "layout": {
            "panel_av_h": av_h,
            "panel_ch_h": ch_h,
            "sidebar_gap": controller.settings.data["layout"].get("sidebar_gap", 5),
            "roi_detail_h": 170,
            "sidebar_margin_bot": 10,
            "sidebar_top_spacer": 5,
            "sidebar_item_gap": item_gap,
            "gap_center": 5,
            "menu_h": 27,
            "menu_m_top": 0,
            "menu_m_bottom": 5 + shared_margin,
            "menu_m_left": 0,
            "menu_m_right": 0,
            "side_panel_w": controller.settings.data["layout"]["side_panel_width"],
            "nav_panel_w": nav_w,
            "nav_btn_h": 35,
            "gap_center": shared_margin,
            "left_m_left": shared_margin,
            "left_m_bottom": shared_margin,
            "left_m_top": 0,
            "left_inner_m": shared_margin,
            "right_inner_m": shared_margin,
            "right_m_right": shared_margin,
            "right_m_bottom": shared_margin,
            "right_m_top": 0,
            "rounding": 8,
            "viewport_padding": 4,
            "pad_frame_menu": [8, 10],
            "pad_frame_readonly": [0, 3],
            "pad_frame_sidebar": [4, 3],
            "pad_menu_popup": [12, 12],
            "space_menu_item": [10, 6],
        },
        "colors": {
            "bg_window": [0, 0, 0, 255],
            "bg_menubar": [37, 37, 38, 255],
            "bg_menu": [27, 27, 28, 255],
            "bg_menu_hover": [70, 70, 75, 255],
            "bg_menu_active": [80, 80, 85, 255],
            "bg_sidebar": [37, 37, 38, 255],
            "border_black": [0, 0, 0, 255],
            "text_dim": [140, 140, 140],
            "text_header": [93, 93, 93],
            "text_active": [0, 246, 7, 255],
            "text_status_ok": [150, 255, 150],
            "text_muted": [150, 150, 150],
            "transparent": [0, 0, 0, 0],
            "outdated": [255, 180, 50],
            "working": [255, 180, 50],
            "warning": [255, 100, 100],
            "help": [100, 180, 255],
        },
    }


def register_dynamic_themes(ui_cfg, controller):
    """Builds and registers all UI themes dynamically based on the ui_cfg."""
    cfg_l = ui_cfg["layout"]
    cfg_c = ui_cfg["colors"]

    if not dpg.does_item_exist("primary_black_theme"):
        with dpg.theme(tag="primary_black_theme"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, cfg_c["bg_window"])
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, cfg_c["text_muted"])

            disabled_bg = [35, 35, 35, 255]  # Static dark grey # FIXME config

            # Explicit component targeting
            with dpg.theme_component(dpg.mvAll, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_muted"])
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_Button, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, disabled_bg)

            with dpg.theme_component(dpg.mvCheckbox, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, cfg_c["text_muted"])

            with dpg.theme_component(dpg.mvSliderFloat, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_muted"])

            with dpg.theme_component(dpg.mvSliderInt, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_muted"])

            with dpg.theme_component(dpg.mvDragFloat, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_muted"])

            with dpg.theme_component(dpg.mvInputFloat, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_Button, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_muted"])

            with dpg.theme_component(dpg.mvCombo, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_Button, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_muted"])

            with dpg.theme_component(dpg.mvButton, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_Button, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, disabled_bg)
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_muted"])

    if not dpg.does_item_exist("black_viewer_theme"):
        with dpg.theme(tag="black_viewer_theme"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_window"])
                dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["border_black"])
                dpg.add_theme_style(
                    dpg.mvStyleVar_WindowPadding,
                    cfg_l["viewport_padding"],
                    cfg_l["viewport_padding"],
                )
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg_l["rounding"])

    if not dpg.does_item_exist("active_black_viewer_theme"):
        with dpg.theme(tag="active_black_viewer_theme"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_window"])
                v_col = controller.settings.data["colors"]["viewer"]
                dpg.add_theme_color(dpg.mvThemeCol_Border, v_col)
                dpg.add_theme_style(
                    dpg.mvStyleVar_WindowPadding,
                    cfg_l["viewport_padding"],
                    cfg_l["viewport_padding"],
                )
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 2)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg_l["rounding"])

    if not dpg.does_item_exist("floating_menu_theme"):
        with dpg.theme(tag="floating_menu_theme"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(
                    dpg.mvStyleVar_FramePadding, *cfg_l["pad_frame_menu"]
                )
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, cfg_c["bg_menu"])
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, cfg_c["bg_menu"])
                dpg.add_theme_color(
                    dpg.mvThemeCol_HeaderHovered, cfg_c["bg_menu_hover"]
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_HeaderActive, cfg_c["bg_menu_active"]
                )

            with dpg.theme_component(dpg.mvMenu):
                dpg.add_theme_style(
                    dpg.mvStyleVar_WindowPadding, *cfg_l["pad_menu_popup"]
                )
                dpg.add_theme_style(
                    dpg.mvStyleVar_ItemSpacing, *cfg_l["space_menu_item"]
                )

            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_menubar"])
                dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, cfg_c["bg_menubar"])
                dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["transparent"])
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg_l["rounding"])
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)

            with dpg.theme_component(dpg.mvMenuBar):
                dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, cfg_c["bg_menubar"])
                dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["transparent"])
                dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 0)

    if not dpg.does_item_exist("no_spacing_theme"):
        with dpg.theme(tag="no_spacing_theme"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)

    if not dpg.does_item_exist("clean_separator_theme"):
        with dpg.theme(tag="clean_separator_theme"):
            with dpg.theme_component(dpg.mvTable):
                dpg.add_theme_style(dpg.mvStyleVar_CellPadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)

    if not dpg.does_item_exist("sidebar_bg_theme"):
        with dpg.theme(tag="sidebar_bg_theme"):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_sidebar"])
                dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["border_black"])
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg_l["rounding"])
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(
                    dpg.mvStyleVar_ItemSpacing, cfg_l["sidebar_item_gap"], 4
                )

    if not dpg.does_item_exist("nav_panel_bg_theme"):
        with dpg.theme(tag="nav_panel_bg_theme"):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_window"])
                dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["transparent"])
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 4, 0)

    if not dpg.does_item_exist("sleek_readonly_theme"):
        with dpg.theme(tag="sleek_readonly_theme"):
            with dpg.theme_component(dpg.mvInputText):
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, cfg_c["transparent"])
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)
                dpg.add_theme_style(
                    dpg.mvStyleVar_FramePadding, *cfg_l["pad_frame_readonly"]
                )

            # Keep W/L inputs completely transparent when disabled
            with dpg.theme_component(dpg.mvInputText, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, cfg_c["transparent"])
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, cfg_c["transparent"])
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_dim"])
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)
                dpg.add_theme_style(
                    dpg.mvStyleVar_FramePadding, *cfg_l["pad_frame_readonly"]
                )
    if not dpg.does_item_exist("active_image_list_theme"):
        with dpg.theme(tag="active_image_list_theme"):
            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_active"])

    if not dpg.does_item_exist("slider_overlay_theme"):
        with dpg.theme(tag="slider_overlay_theme"):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [0, 0, 0, 204])
                dpg.add_theme_color(dpg.mvThemeCol_Border, [0, 0, 0, 0])
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0.0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 4.0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 8)

    if not dpg.does_item_exist("left_panel_padding_theme"):
        with dpg.theme(tag="left_panel_padding_theme"):
            with dpg.theme_component(dpg.mvAll):
                # Change 0 to 4 to stop the macOS tab background from bleeding!
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 4, 12)
                dpg.add_theme_style(
                    dpg.mvStyleVar_FramePadding, *cfg_l["pad_frame_sidebar"]
                )

    if not dpg.does_item_exist("outdated_item_theme"):
        with dpg.theme(tag="outdated_item_theme"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["outdated"])

    if not dpg.does_item_exist("help_button_theme"):
        with dpg.theme(tag="help_button_theme"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [60, 60, 60])
                dpg.add_theme_color(
                    dpg.mvThemeCol_Text, cfg_c.get("help", [100, 180, 255])
                )
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)

    if not dpg.does_item_exist("theme_help_nav"):
        with dpg.theme(tag="theme_help_nav"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
                dpg.add_theme_color(
                    dpg.mvThemeCol_Text, cfg_c.get("help", [100, 180, 255])
                )

    if not dpg.does_item_exist("orange_button_theme"):
        with dpg.theme(tag="orange_button_theme"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
                dpg.add_theme_color(dpg.mvThemeCol_Button, cfg_c["outdated"])
                dpg.add_theme_color(
                    dpg.mvThemeCol_ButtonHovered,
                    [min(255, c + 30) for c in cfg_c["outdated"]],
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_ButtonActive,
                    [min(255, c + 50) for c in cfg_c["outdated"]],
                )
                dpg.add_theme_color(dpg.mvThemeCol_Text, [0, 0, 0, 255])

    if not dpg.does_item_exist("theme_rounded_nav"):
        with dpg.theme(tag="theme_rounded_nav"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)

    # Nav button of a tool that does not apply to the current image (still clickable)
    if not dpg.does_item_exist("theme_rounded_nav_muted"):
        with dpg.theme(tag="theme_rounded_nav_muted"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_muted"])

    if not dpg.does_item_exist("theme_ws_nav_btn"):
        with dpg.theme(tag="theme_ws_nav_btn"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, cfg_c["bg_window"])
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [22, 22, 25, 255])
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, [40, 40, 44, 255])
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
            with dpg.theme_component(dpg.mvButton, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_Button, cfg_c["bg_window"])
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, cfg_c["bg_window"])
                dpg.add_theme_color(dpg.mvThemeCol_Text, [55, 55, 60, 255])

    if not dpg.does_item_exist("active_nav_button_theme"):
        with dpg.theme(tag="active_nav_button_theme"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
                dpg.add_theme_color(dpg.mvThemeCol_Button, cfg_c["bg_menu_active"])
                dpg.add_theme_color(
                    dpg.mvThemeCol_ButtonHovered, cfg_c["bg_menu_active"]
                )
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_active"])

    # Same colors, square corners: panel buttons (the nav column is rounded)
    if not dpg.does_item_exist("active_button_theme"):
        with dpg.theme(tag="active_button_theme"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, cfg_c["bg_menu_active"])
                dpg.add_theme_color(
                    dpg.mvThemeCol_ButtonHovered, cfg_c["bg_menu_active"]
                )
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_active"])

    if not dpg.does_item_exist("outdated_image_input_theme"):
        with dpg.theme(tag="outdated_image_input_theme"):
            with dpg.theme_component(dpg.mvInputText):
                dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["outdated"])

    if not dpg.does_item_exist("theme_beginner_btn"):
        with dpg.theme(tag="theme_beginner_btn"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)

    if not dpg.does_item_exist("theme_beginner_active"):
        with dpg.theme(tag="theme_beginner_active"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
                dpg.add_theme_color(dpg.mvThemeCol_Button, [215, 220, 230, 255])
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [235, 240, 250, 255])
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, [185, 190, 200, 255])
                dpg.add_theme_color(dpg.mvThemeCol_Text, [20, 25, 30, 255])


# macOS: the system Helvetica (sharpest on 1x external screens, the layout was
# tuned on it). Elsewhere: the shipped Liberation Sans (SIL OFL 1.1, see
# fonts/LiberationSans-LICENSE.txt). DPG sizes a font by its line height
# (ascent + descent) and does not hint glyphs, so on 1x screens text is sharp
# only when the cap height lands on whole pixels: Liberation Sans cap height =
# 0.6158 x size -> 16.24 gives 10 px (Helvetica 14: 10.04 px), 13 gives 8 px.
MACOS_UI_FONT = ("/System/Library/Fonts/Helvetica.ttc", 14, 11)
SHIPPED_UI_FONT = ("LiberationSans-Regular.ttf", 16.24, 13)


def _pick_ui_font():
    """(path, size, small size) of the UI text font, or None for the DPG default."""
    if sys.platform == "darwin" and os.path.exists(MACOS_UI_FONT[0]):
        return MACOS_UI_FONT
    name, size, small = SHIPPED_UI_FONT
    path = get_resource_path(os.path.join("fonts", name))
    if os.path.exists(path):
        return path, size, small
    logger.warning(f"UI font not found ({path}), using a system font instead.")
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        path = os.path.join(windir, "Fonts", "segoeui.ttf")
    else:
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists(path):
        return path, 14, 11
    logger.warning("No system font found: using the DearPyGui default font.")
    return None


def load_fonts():
    ui_font = _pick_ui_font()
    icon_font_path = get_resource_path(
        os.path.join("fonts", "Font Awesome 7 Free-Solid-900.otf")
    )

    # Check DPG version to avoid calling deprecated no-op functions in >= 2.3
    is_legacy_dpg = False
    try:
        import dearpygui

        v_str = getattr(dearpygui, "__version__", None) or "2.3.0"
        if not v_str:
            v_str = "2.3.0"
        parts = v_str.split(".")
        if int(parts[0]) < 2 or (int(parts[0]) == 2 and int(parts[1]) < 3):
            is_legacy_dpg = True
    except Exception:
        is_legacy_dpg = True

    with dpg.font_registry():
        default_font = None

        # 1. Load the UI Text Font
        if ui_font:
            main_font_path, size, small_size = ui_font
            with dpg.font(main_font_path, size) as font:
                if is_legacy_dpg:
                    try:
                        # pyrefly: ignore [deprecated]
                        dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    except Exception:
                        pass
                default_font = font

            with dpg.font(main_font_path, small_size, tag="small_font_tag"):
                if is_legacy_dpg:
                    try:
                        # pyrefly: ignore [deprecated]
                        dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    except Exception:
                        pass

        # 2. Load the Icon Font (standard 14px and slightly larger 18px for prominent buttons)
        if os.path.exists(icon_font_path):
            with dpg.font(icon_font_path, 14, tag="icon_font_tag"):
                if is_legacy_dpg:
                    try:
                        # pyrefly: ignore [deprecated]
                        dpg.add_font_range(0xF000, 0xF35F)
                        # pyrefly: ignore [deprecated]
                        dpg.add_font_chars(
                            [
                                0xE001,  # Custom: Save As (floppy with down arrow badge)
                                0xF0C5,
                                0xF06E,
                                0xF070,
                                0xF062,
                                0xF063,
                                0xF05B,
                                0xF07C,
                                0xF0C7,
                                0xF013,
                                0xF059,
                                0xF040,
                                0xF07D,
                                0xF07E,
                                0xF0DC,
                                0xF00D,
                                0xF15D,
                                0xF15E,
                                0xF061,  # right arrow
                                0xF35D,  # external window icon
                                0xF05B,  #
                                0xF076,  # Magnet icon for snap
                                0xF77C,  # Baby icon
                                0xF111,  # Circle/Sphere
                                0xF0C8,  # Square/Rect
                                0xF0EC,  # Exchange / swap icon
                            ]
                        )
                        # pyrefly: ignore [deprecated]
                        dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    except Exception:
                        pass
            with dpg.font(icon_font_path, 18, tag="icon_font_18_tag"):
                if is_legacy_dpg:
                    try:
                        # pyrefly: ignore [deprecated]
                        dpg.add_font_chars([0xE001, 0xF77C, 0xF059, 0xF013])
                        # pyrefly: ignore [deprecated]
                        dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    except Exception:
                        pass
        else:
            logger.error("Icon font file not found! Buttons will show '?'.")

        # 3. Bind the default text font at the very end
        if default_font:
            dpg.bind_font(default_font)


def setup_themes():
    """Defines and binds themes for various UI components."""
    # Viewer Theme
    with dpg.theme(tag="viewer_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(
                dpg.mvThemeCol_ChildBg, [0, 0, 0], category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_Border, [50, 50, 50], category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_style(
                dpg.mvStyleVar_WindowPadding, 0, 0, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_style(
                dpg.mvStyleVar_ItemSpacing, 0, 0, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_style(
                dpg.mvStyleVar_FramePadding, 0, 0, category=dpg.mvThemeCat_Core
            )

    # Icon Button Theme
    with dpg.theme(tag="icon_button_theme"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [60, 60, 60])
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)
        with dpg.theme_component(dpg.mvButton, enabled_state=False):  # dimmed, no box
            dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_Text, [150, 150, 150])  # = text_muted

    # Delete Button Theme
    with dpg.theme(tag="delete_button_theme"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [150, 40, 40])
            dpg.add_theme_color(dpg.mvThemeCol_Text, [200, 100, 100])
        with dpg.theme_component(dpg.mvButton, enabled_state=False):  # dimmed, no box
            dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_Text, [150, 150, 150])  # = text_muted

    # Read-only Input Theme (for sidebar info)
    with dpg.theme(tag="readonly_theme"):
        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)
            dpg.add_theme_color(dpg.mvThemeCol_Text, [0, 246, 7])

    # Active Viewer Theme (Bright border)
    with dpg.theme(tag="active_viewer_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(
                dpg.mvThemeCol_Border, [0, 246, 7, 50], category=dpg.mvThemeCat_Core
            )  # Match your green crosshair
            dpg.add_theme_style(
                dpg.mvStyleVar_ChildBorderSize, 2, category=dpg.mvThemeCat_Core
            )
            # Keep other styles consistent with viewer_theme
            dpg.add_theme_style(
                dpg.mvStyleVar_WindowPadding, 0, 0, category=dpg.mvThemeCat_Core
            )

    # Active Image List Theme (Green background)
    with dpg.theme(tag="active_image_list_theme"):
        with dpg.theme_component(dpg.mvAll):
            # Change text to green and make it bold-ish if font supports it
            dpg.add_theme_color(
                dpg.mvThemeCol_Text, [0, 246, 7], category=dpg.mvThemeCat_Core
            )
