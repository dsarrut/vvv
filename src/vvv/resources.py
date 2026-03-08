import os
import sys
import dearpygui.dearpygui as dpg


def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)


def load_fonts():
    """Loads fonts and other external resources."""
    font_path = get_resource_path(os.path.join("fonts", "Font Awesome 7 Free-Solid-900.otf"))

    if not os.path.exists(font_path):
        print(f"WARNING: Font file not found at {font_path}")
        return None

    with dpg.font_registry():
        with dpg.font(font_path, 14, tag="icon_font_tag") as icon_font:
            dpg.add_font_range(0xf00d, 0xf021)
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
    return icon_font


def setup_themes():
    """Defines and binds themes for various UI components."""
    # Viewer Theme
    with dpg.theme(tag="viewer_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [0, 0, 0], category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Border, [50, 50, 50], category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 0, 0, category=dpg.mvThemeCat_Core)

    # Icon Button Theme
    with dpg.theme(tag="icon_button_theme"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [60, 60, 60])
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)

    # Delete Button Theme
    with dpg.theme(tag="delete_button_theme"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [150, 40, 40])
            dpg.add_theme_color(dpg.mvThemeCol_Text, [200, 100, 100])

    # Read-only Input Theme (for sidebar info)
    with dpg.theme(tag="readonly_theme"):
        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)
            dpg.add_theme_color(dpg.mvThemeCol_Text, [0, 246, 7])

    # Active Viewer Theme (Bright border)
    with dpg.theme(tag="active_viewer_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Border, [0, 246, 7, 50],
                                category=dpg.mvThemeCat_Core)  # Match your green crosshair
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 2, category=dpg.mvThemeCat_Core)
            # Keep other styles consistent with viewer_theme
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0, category=dpg.mvThemeCat_Core)

    # Active Image List Theme (Green background)
    with dpg.theme(tag="active_image_list_theme"):
        with dpg.theme_component(dpg.mvAll):
            # Change text to green and make it bold-ish if font supports it
            dpg.add_theme_color(dpg.mvThemeCol_Text, [0, 246, 7], category=dpg.mvThemeCat_Core)
