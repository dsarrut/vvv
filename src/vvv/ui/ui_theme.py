import sys
import dearpygui.dearpygui as dpg


def build_ui_config(controller):
    """Centralizes all layout dimensions, margins, and colors."""
    shared_margin = 7
    is_mac = sys.platform == "darwin"

    # Mac Retina scaling makes text blocks taller and gaps slightly tighter
    av_h = 360 if is_mac else 360  # Active Viewer Height
    ch_h = 160 if is_mac else 150  # Crosshair Height
    item_gap = 6 if is_mac else 8

    return {
        "layout": {
            "panel_av_h": av_h,
            "panel_ch_h": ch_h,
            "roi_detail_h": 190,
            "roi_detail_bottom_margin": 10,
            "sidebar_margin_bot": 10,
            "sidebar_top_spacer": 5,
            "sidebar_item_gap": item_gap,
            "menu_h": 27,
            "menu_m_top": 0,
            "menu_m_bottom": 5 + shared_margin,
            "menu_m_left": 0,
            "menu_m_right": 0,
            "side_panel_w": controller.settings.data["layout"]["side_panel_width"],
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

    if not dpg.does_item_exist("sidebar_bg_theme"):
        with dpg.theme(tag="sidebar_bg_theme"):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_sidebar"])
                dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["border_black"])
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg_l["rounding"])

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
