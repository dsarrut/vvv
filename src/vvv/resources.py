import os
import sys
import dearpygui.dearpygui as dpg


def get_resource_path(rel_path):
    """Get absolute path to resource, works for dev and for PyInstaller/cx_Freeze"""
    # PyInstaller creates a temp folder and stores path in _MEIPASS
    base_path = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base_path, rel_path)


def load_fonts():
    main_font_path = get_resource_path(os.path.join("fonts", "Roboto-Regular.ttf"))
    icon_font_path = get_resource_path(
        os.path.join("fonts", "Font Awesome 7 Free-Solid-900.otf")
    )

    if not os.path.exists(main_font_path):
        if sys.platform == "darwin":
            main_font_path = "/System/Library/Fonts/Helvetica.ttc"  # Native macOS font
        elif sys.platform == "win32":
            windir = os.environ.get("WINDIR", "C:\\Windows")
            main_font_path = os.path.join(windir, "Fonts", "segoeui.ttf")
        else:
            main_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    # Check DPG version to avoid calling deprecated no-op functions in >= 2.3
    is_legacy_dpg = False
    try:
        import dearpygui

        v_str = getattr(
            dearpygui,
            "__version__",
            dpg.get_app_configuration().get("version", "2.3.0"),
        )
        parts = v_str.split(".")
        if int(parts[0]) < 2 or (int(parts[0]) == 2 and int(parts[1]) < 3):
            is_legacy_dpg = True
    except Exception:
        is_legacy_dpg = True

    with dpg.font_registry():
        default_font = None

        # 1. Load the UI Text Font
        if os.path.exists(main_font_path):
            with dpg.font(main_font_path, 14) as font:
                if is_legacy_dpg:
                    try:
                        dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    except Exception:
                        pass
                default_font = font

            with dpg.font(main_font_path, 11, tag="small_font_tag"):
                if is_legacy_dpg:
                    try:
                        dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    except Exception:
                        pass

        # 2. Load the Icon Font
        if os.path.exists(icon_font_path):
            with dpg.font(icon_font_path, 14, tag="icon_font_tag"):
                if is_legacy_dpg:
                    try:
                        dpg.add_font_range(0xF000, 0xF021)
                        dpg.add_font_chars(
                            [
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
                                0xF05B,  #
                                0xF77C,  # Baby icon
                            ]
                        )
                        dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    except Exception:
                        pass
        else:
            print("ERROR: Icon font file not found! Buttons will show '?'.")

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
