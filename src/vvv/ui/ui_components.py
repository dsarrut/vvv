import dearpygui.dearpygui as dpg

# Standard UI toolbar icon glyphs
ICON_SAVE = "\uf0c7"  # Floppy disk
ICON_SAVE_AS = "\ue001"  # Floppy disk with down arrow badge


def _ensure_separator_theme():
    """Ensures clean_separator_theme exists, creating it if register_dynamic_themes has not been called."""
    if not dpg.does_item_exist("clean_separator_theme"):
        with dpg.theme(tag="clean_separator_theme"):
            with dpg.theme_component(dpg.mvTable):
                dpg.add_theme_style(dpg.mvStyleVar_CellPadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)


def build_horizontal_separator(width=-8, space_below=4, parent=None):
    """A reusable UI component for a clean horizontal separator with margins on both sides and below."""
    _ensure_separator_theme()
    kwargs = {
        "header_row": False,
        "policy": dpg.mvTable_SizingStretchProp,
    }
    if width is not None:
        kwargs["width"] = width
    if parent is not None:
        kwargs["parent"] = parent

    with dpg.table(**kwargs) as table:
        dpg.bind_item_theme(table, "clean_separator_theme")
        dpg.add_table_column()
        with dpg.table_row():
            dpg.add_separator()

    if space_below and space_below > 0:
        if parent is not None:
            dpg.add_spacer(height=space_below, parent=parent)
        else:
            dpg.add_spacer(height=space_below)

    return table


def build_section_title(label, color, sep_width=-8, space_below=4):
    """A reusable UI component for a section title with a horizontal separator."""
    dpg.add_text(label, color=color)
    return build_horizontal_separator(width=sep_width, space_below=space_below)


def build_help_button(text, gui):
    """A reusable help icon button that only appears when Beginner Mode is active."""
    tag = dpg.generate_uuid()
    btn = dpg.add_button(label="\uf059", width=20, tag=tag, show=getattr(gui, "is_beginner_mode", False))
    if dpg.does_item_exist("icon_font_tag"):
        dpg.bind_item_font(btn, "icon_font_tag")
    if dpg.does_item_exist("help_button_theme"):
        dpg.bind_item_theme(btn, "help_button_theme")
        
    build_beginner_tooltip(btn, text, gui)
    
    if not hasattr(gui, "beginner_tags"):
        gui.beginner_tags = []
    gui.beginner_tags.append(tag)
    return btn


def build_icon_button(
    icon,
    callback=None,
    tooltip=None,
    gui=None,
    width=20,
    theme="icon_button_theme",
    tag=None,
    user_data=None,
    enabled=True,
    show=True,
):
    """Creates a standardized icon button with optional always-on tooltip (U15.1, U21)."""
    kwargs = {"label": icon, "width": width, "enabled": enabled, "show": show}
    if tag is not None:
        kwargs["tag"] = tag
    if user_data is not None:
        kwargs["user_data"] = user_data
    if callback is not None:
        kwargs["callback"] = callback

    btn = dpg.add_button(**kwargs)
    if dpg.does_item_exist("icon_font_tag"):
        dpg.bind_item_font(btn, "icon_font_tag")
    if theme and dpg.does_item_exist(theme):
        dpg.bind_item_theme(btn, theme)
    if tooltip and gui:
        build_tooltip(btn, tooltip, gui, always_on=True)
    return btn


def build_delete_button(
    label="\uf00d", width=20, user_data=None, callback=None, tooltip="Delete", gui=None
):
    """Creates a standardized red icon close/delete button."""
    return build_icon_button(
        icon=label,
        width=width,
        user_data=user_data,
        callback=callback,
        tooltip=tooltip,
        gui=gui,
        theme="delete_button_theme",
    )


REGISTERED_INPUT_FILTER_TAGS = set()

# Room kept right of the filter input (it fills the rest of the row): the two
# 24 px buttons, the "M / N" count and the item spacing (6-8 px).
_FILTER_BTN_W = 24
_FILTER_COUNT_W = 56
_FILTER_RESERVE_W = 2 * (_FILTER_BTN_W + 8) + _FILTER_COUNT_W + 8
_FILTER_COUNT_DY = 2  # (frame height - small text height) / 2 - frame padding


def name_matches(name, filter_text, invert=False):
    """Name filter rule shared by all lists: case-insensitive substring of the
    stripped filter text; invert keeps the non-matching names. An empty filter
    keeps everything, inverted or not."""
    text = (filter_text or "").strip().lower()
    if not text:
        return True
    return (text in (name or "").lower()) != bool(invert)


def set_filter_invert_state(btn_invert_tag, invert):
    """Highlight the invert button while the inverted filter is on."""
    if not dpg.does_item_exist(btn_invert_tag):
        return
    if invert and dpg.does_item_exist("active_nav_button_theme"):
        dpg.bind_item_theme(btn_invert_tag, "active_nav_button_theme")
    else:
        dpg.bind_item_theme(btn_invert_tag, 0)


def set_filter_count(count_tag, shown, total):
    """'M / N': items listed by the filter / all items."""
    if dpg.does_item_exist(count_tag):
        dpg.set_value(count_tag, f"{shown} / {total}")


def build_name_filter_bar(
    group_tag,
    input_tag,
    btn_clear_tag,
    on_filter_changed,
    on_clear_clicked,
    api=None,
    btn_invert_tag=None,
    on_invert_clicked=None,
    count_tag=None,
    hint="Filter ...",
):
    """Name filter row shared by the ROI, landmark, profile and DVH lists: input
    (fills the row), invert (!), clear (X) and an item count (see
    set_filter_count). Match names with name_matches."""
    if input_tag:
        REGISTERED_INPUT_FILTER_TAGS.add(input_tag)
    with dpg.group(horizontal=True, tag=group_tag):
        dpg.add_input_text(
            hint=hint,
            tag=input_tag,
            width=-_FILTER_RESERVE_W,
            callback=lambda s, a: on_filter_changed(a),
        )
        if api:
            build_beginner_tooltip(
                input_tag,
                "Type to search and filter the list by name.",
                api,
            )

        if btn_invert_tag and on_invert_clicked:
            btn_invert = dpg.add_button(
                label="!",
                tag=btn_invert_tag,
                width=_FILTER_BTN_W,
                callback=lambda: on_invert_clicked(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_invert, "icon_font_tag")
            if api:
                build_tooltip(
                    btn_invert,
                    "Invert filter: when active, excludes items containing this text.",
                    api,
                    always_on=True,
                )

        btn_clear = dpg.add_button(
            label="X",
            tag=btn_clear_tag,
            width=_FILTER_BTN_W,
            callback=lambda: on_clear_clicked(),
        )
        if api:
            build_tooltip(
                btn_clear,
                "Clears the name filter (and the invert).",
                api,
                always_on=True,
            )
        if count_tag:
            ui_cfg = getattr(api, "ui_cfg", None)
            color = (
                ui_cfg["colors"]["text_dim"]
                if isinstance(ui_cfg, dict)
                else (150, 150, 150)
            )
            # Small font: a spacer (no item spacing) centers it on the input row
            with dpg.group() as count_group:
                dpg.add_spacer(height=_FILTER_COUNT_DY)
                count = dpg.add_text("", tag=count_tag, color=color)
            if dpg.does_item_exist("small_font_tag"):
                dpg.bind_item_font(count, "small_font_tag")
            if not dpg.does_item_exist("filter_count_theme"):
                with dpg.theme(tag="filter_count_theme"):
                    with dpg.theme_component(dpg.mvAll):
                        dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
            dpg.bind_item_theme(count_group, "filter_count_theme")
    return group_tag


def build_color_picker_row(
    tag_prefix,
    on_color_changed=None,
    on_reset_colors=None,
    on_toggle_visible=None,
    on_show_clicked=None,
    on_hide_clicked=None,
    on_toggle_names=None,
    on_snap_clicked=None,
    show_contour=False,
    on_contour_clicked=None,
    show_above_overlay=False,
    on_above_overlay_clicked=None,
    on_delete_clicked=None,
    gui=None,
    api=None,
):
    """
    Creates a standardized row of batch management buttons for list tables.
    """
    g_obj = gui or api
    with dpg.group(horizontal=True, tag=f"{tag_prefix}_batch_toolbar"):
        # 1. Color Picker
        if on_color_changed:
            col_picker = dpg.add_color_edit(
                default_value=[255, 255, 255, 255],
                no_inputs=True,
                no_label=True,
                no_alpha=True,
                width=20,
                height=20,
                tag=f"{tag_prefix}_batch_color",
                callback=lambda s, a: on_color_changed(a),
            )

        # 2. Reset Colors
        if on_reset_colors:
            btn_reset_col = dpg.add_button(
                label="\uf043",
                width=20,
                tag=f"{tag_prefix}_batch_reset_colors",
                callback=lambda: on_reset_colors(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_reset_col, "icon_font_tag")
            if g_obj:
                build_tooltip(btn_reset_col, "Reset colors to default initial sequence", g_obj, always_on=True)

        # 3. Toggle Visible (or Show/Hide)
        if on_toggle_visible:
            btn_toggle_vis = dpg.add_button(
                label="\uf06e",
                width=20,
                tag=f"{tag_prefix}_batch_toggle_visible",
                callback=lambda: on_toggle_visible(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_toggle_vis, "icon_font_tag")
            if g_obj:
                build_tooltip(btn_toggle_vis, "Toggle show/hide listed/filtered items", g_obj, always_on=True)
        else:
            # Legacy: separate show/hide buttons
            if on_show_clicked:
                btn_show = dpg.add_button(
                    label="\uf06e",
                    width=20,
                    tag=f"{tag_prefix}_batch_show",
                    callback=lambda: on_show_clicked(),
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_show, "icon_font_tag")
                if g_obj:
                    build_tooltip(btn_show, "Show listed/filtered items", g_obj, always_on=True)

            if on_hide_clicked:
                btn_hide = dpg.add_button(
                    label="\uf070",
                    width=20,
                    tag=f"{tag_prefix}_batch_hide",
                    callback=lambda: on_hide_clicked(),
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_hide, "icon_font_tag")
                if g_obj:
                    build_tooltip(btn_hide, "Hide listed/filtered items", g_obj, always_on=True)

        # 4. Toggle Name Labels
        if on_toggle_names:
            btn_names = dpg.add_button(
                label="\uf02b",
                width=20,
                tag=f"{tag_prefix}_batch_toggle_names",
                callback=lambda: on_toggle_names(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_names, "icon_font_tag")
            if g_obj:
                build_tooltip(btn_names, "Toggle name labels for listed/filtered items", g_obj, always_on=True)

        # 5. Snap All
        if on_snap_clicked:
            btn_snap = dpg.add_button(
                label="\uf076",
                width=20,
                tag=f"{tag_prefix}_batch_snap",
                callback=lambda: on_snap_clicked(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_snap, "icon_font_tag")
            if g_obj:
                build_tooltip(btn_snap, "Snap all items to nearest voxel grid center", g_obj, always_on=True)

        # Contour & Overlay options
        if show_contour and on_contour_clicked:
            btn_contour = dpg.add_button(
                label="\uf040",
                width=20,
                tag=f"{tag_prefix}_batch_contour",
                callback=lambda: on_contour_clicked(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_contour, "icon_font_tag")
            if g_obj:
                build_tooltip(btn_contour, "Show as contour", g_obj, always_on=True)

        if show_above_overlay and on_above_overlay_clicked:
            btn_overlay = dpg.add_button(
                label="\uf5fd",
                width=20,
                tag=f"{tag_prefix}_batch_overlay",
                callback=lambda: on_above_overlay_clicked(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_overlay, "icon_font_tag")
            if g_obj:
                build_tooltip(btn_overlay, "Toggle on top of fusion overlay", g_obj, always_on=True)

        # 6. Delete
        if on_delete_clicked:
            build_delete_button(
                label="\uf00d",
                width=20,
                callback=lambda: on_delete_clicked(),
                tooltip="Delete listed/filtered items",
                gui=g_obj,
            )


build_batch_action_toolbar = build_color_picker_row


def get_tooltip_delay(gui, always_on=True):
    """Returns the delay in seconds for tooltips based on beginner mode and settings."""
    target_gui = getattr(gui, "_gui", gui) if hasattr(gui, "_gui") else gui
    is_beg = getattr(target_gui, "is_beginner_mode", False)
    controller = getattr(target_gui, "controller", None)
    cfg = {}
    if controller and hasattr(controller, "settings"):
        cfg = controller.settings.data.get("interaction", {})
    if is_beg:
        return float(cfg.get("tooltip_delay_beginner", 0.1))
    return float(cfg.get("tooltip_delay", 0.6)) if always_on else float(cfg.get("tooltip_delay_beginner", 0.1))


def set_item_show(item, show, gui=None):
    """Sets item visibility and synchronizes any attached tooltip visibility."""
    if dpg.does_item_exist(item):
        dpg.configure_item(item, show=show)
    target_gui = getattr(gui, "_gui", gui) if hasattr(gui, "_gui") else gui
    if target_gui and hasattr(target_gui, "tooltip_parent_map"):
        for tt_tag, p in getattr(target_gui, "tooltip_parent_map", {}).items():
            if p == item and dpg.does_item_exist(tt_tag):
                is_beg = getattr(target_gui, "is_beginner_mode", False)
                is_icon = tt_tag in getattr(target_gui, "icon_tooltip_tags", [])
                tt_show = show if is_icon else (is_beg and show)
                dpg.configure_item(tt_tag, show=tt_show)


def build_tooltip(parent, text, gui, tag=None, text_tag=None, always_on=True):
    """A reusable tooltip attached to an existing widget.

    If always_on=True (icon buttons, toolbars):
        Visible in both normal and beginner modes with an activation delay:
        - tooltip_delay (default 0.6s) in normal mode
        - tooltip_delay_beginner (default 0.1s) in beginner mode
        Registered in gui.icon_tooltip_tags so toggling beginner mode updates delay.
    If always_on=False (educational tooltips on text/sliders):
        Visible only when Beginner Mode is active (show=is_beginner, delay=0.1s).
        Registered in gui.beginner_tags so toggling beginner mode toggles visibility.
    """
    target_gui = getattr(gui, "_gui", gui) if hasattr(gui, "_gui") else gui
    is_beg = getattr(target_gui, "is_beginner_mode", False)
    delay = get_tooltip_delay(target_gui, always_on=always_on)
    parent_shown = True
    if dpg.does_item_exist(parent):
        parent_shown = bool(dpg.get_item_configuration(parent).get("show", True))
    show_initial = parent_shown if always_on else (is_beg and parent_shown)

    tt_kwargs = {"parent": parent, "show": show_initial, "delay": delay}
    if tag:
        tt_kwargs["tag"] = tag
    try:
        tt_tag = dpg.add_tooltip(**tt_kwargs)
    except (Exception, SystemError):
        return None

    if not hasattr(target_gui, "tooltip_parent_map") or not isinstance(
        target_gui.tooltip_parent_map, dict
    ):
        target_gui.tooltip_parent_map = {}
    target_gui.tooltip_parent_map[tt_tag] = parent

    colors = (
        getattr(target_gui, "ui_cfg", {}).get("colors", {})
        if hasattr(target_gui, "ui_cfg")
        else {}
    )
    dim_col = (
        colors.get("text_dim", [150, 150, 150])
        if isinstance(colors, dict)
        else [150, 150, 150]
    )
    try:
        if text_tag:
            dpg.add_text(text, parent=tt_tag, color=dim_col, tag=text_tag)
        else:
            dpg.add_text(text, parent=tt_tag, color=dim_col)
    except (Exception, SystemError):
        pass

    if always_on:
        if not hasattr(target_gui, "icon_tooltip_tags") or not isinstance(
            target_gui.icon_tooltip_tags, list
        ):
            target_gui.icon_tooltip_tags = []
        target_gui.icon_tooltip_tags.append(tt_tag)
    else:
        if hasattr(target_gui, "beginner_tags") and isinstance(
            target_gui.beginner_tags, list
        ):
            target_gui.beginner_tags.append(tt_tag)
    return tt_tag


def build_beginner_tooltip(parent, text, gui, text_tag=None, always_on=False):
    """A reusable tooltip attached to an existing widget that only appears when Beginner Mode is active."""
    return build_tooltip(
        parent=parent, text=text, gui=gui, text_tag=text_tag, always_on=always_on
    )

def build_stepped_slider(
    label,
    tag,
    callback,
    step_callback,
    min_val=-1e9,
    max_val=1e9,
    default_val=0.0,
    format="%.3f",
    has_checkbox=False,
    check_tag=None,
    check_cb=None,
    has_color=False,
    color_tag=None,
    color_cb=None,
    color_default=(255, 0, 0, 255),
    help_text=None,
    gui=None,
    label_width=None,
    user_data=None,
    use_slider=False,
):
    """A reusable UI component for a slider with + and - step buttons."""

    # --- INTERNAL STATE (Hidden closure) ---
    # Python closures capture dictionaries by reference. This means both buttons
    # share this exact multiplier state, and it doesn't pollute the global scope!
    state = {"mult": 1.0}

    def _change_speed(sender, app_data, user_data):
        # Update the hidden multiplier when the user clicks a popup item
        state["mult"] = user_data

    def _internal_step_wrapper(sender, app_data, user_data):
        # Scale the direction by the currently selected multiplier
        external_user_data = {
            "tag": user_data["tag"],
            "dir": user_data["base_dir"] * state["mult"],
        }

        # Fire the original caller's callback with the scaled value
        if step_callback:
            step_callback(sender, app_data, external_user_data)

    # ---------------------------------------

    with dpg.group(horizontal=True):
        if has_checkbox:
            dpg.add_checkbox(tag=check_tag or 0, enabled=False, callback=check_cb)  # type: ignore

        if has_color:
            dpg.add_color_edit(
                default_value=color_default,
                tag=color_tag or 0,
                callback=color_cb,  # type: ignore
                no_inputs=True,
                no_label=True,
                no_alpha=True,
                width=20,
                height=20,
            )

        if label_width:
            lw = label_width
            if has_color:
                spacing = gui.ui_cfg["layout"].get("sidebar_item_gap", 8) if (gui and hasattr(gui, "ui_cfg")) else 8
                lw -= (20 + spacing)
            t = dpg.add_input_text(default_value=label.strip(), width=lw, readonly=True)
            if dpg.does_item_exist("sleek_readonly_theme"):
                dpg.bind_item_theme(t, "sleek_readonly_theme")
        else:
            dpg.add_text(label)

        is_beg = getattr(gui, "is_beginner_mode", False) if gui else False

        # 1. The Slider
        if use_slider:
            dpg.add_slider_float(
                tag=tag,
                width=-100 if (help_text and is_beg) else -60,
                format=format,
                min_value=min_val,
                max_value=max_val,
                default_value=default_val,
                enabled=not has_checkbox,
                callback=callback,
                user_data=user_data,
            )
        else:
            dpg.add_drag_float(
                tag=tag,
                width=-100 if (help_text and is_beg) else -60,
                format=format,
                speed=1.0,
                min_value=min_val,
                max_value=max_val,
                default_value=default_val,
                enabled=not has_checkbox,
                callback=callback,
                user_data=user_data,
            )

        # 2. The Minus Button
        btn_minus = f"btn_{tag}_minus"
        dpg.add_button(
            label="-",
            width=20,
            tag=btn_minus,
            user_data={"tag": tag, "base_dir": -1},
            enabled=not has_checkbox,
            callback=_internal_step_wrapper,
        )
        if dpg.does_item_exist("icon_button_theme"):
            dpg.bind_item_theme(btn_minus, "icon_button_theme")

        # Hidden Right-Click Menu for Minus
        with dpg.popup(btn_minus, mousebutton=dpg.mvMouseButton_Right):
            dpg.add_text("Step Speed", color=[150, 150, 150])
            dpg.add_separator()
            dpg.add_selectable(
                label="Slow (0.1x)", user_data=0.1, callback=_change_speed
            )
            dpg.add_selectable(
                label="Normal (1.0x)", user_data=1.0, callback=_change_speed
            )
            dpg.add_selectable(
                label="Fast (10.0x)", user_data=10.0, callback=_change_speed
            )
            
        # 3. The Plus Button
        btn_plus = f"btn_{tag}_plus"
        dpg.add_button(
            label="+",
            width=20,
            tag=btn_plus,
            user_data={"tag": tag, "base_dir": 1},
            enabled=not has_checkbox,
            callback=_internal_step_wrapper,
        )
        if dpg.does_item_exist("icon_button_theme"):
            dpg.bind_item_theme(btn_plus, "icon_button_theme")

        # Hidden Right-Click Menu for Plus
        with dpg.popup(btn_plus, mousebutton=dpg.mvMouseButton_Right):
            dpg.add_text("Step Speed", color=[150, 150, 150])
            dpg.add_separator()
            dpg.add_selectable(
                label="Slow (0.1x)", user_data=0.1, callback=_change_speed
            )
            dpg.add_selectable(
                label="Normal (1.0x)", user_data=1.0, callback=_change_speed
            )
            dpg.add_selectable(
                label="Fast (10.0x)", user_data=10.0, callback=_change_speed
            )
            
        if help_text and gui:
            sp_tag = dpg.add_spacer(width=2, show=is_beg)
            build_help_button(help_text, gui)
            if not hasattr(gui, "beginner_tags"):
                gui.beginner_tags = []
            gui.beginner_tags.append(sp_tag)


def build_renamable_input(tag, default_value, callback, user_data=None, width=180, tooltip=None, gui=None, on_enter=True):
    """
    Creates a renamable text input widget that triggers `callback` on enter or on focus loss (deactivation).
    Passes the current text value of the input field to `callback` as its second argument (app_data).
    """
    if tag:
        REGISTERED_INPUT_FILTER_TAGS.add(tag)
    def _wrapped_callback(sender, app_data, u):
        val = dpg.get_value(sender)
        callback(sender, val, u)

    input_id = dpg.add_input_text(
        tag=tag,
        default_value=default_value,
        width=width,
        on_enter=on_enter,
        callback=_wrapped_callback,
        user_data=user_data,
    )

    handler_tag = f"handler_deact_{tag}"
    if not dpg.does_item_exist(handler_tag):
        with dpg.item_handler_registry(tag=handler_tag):
            dpg.add_item_deactivated_after_edit_handler(
                callback=lambda s, a, u: _wrapped_callback(input_id, None, u),
                user_data=user_data
            )
    dpg.bind_item_handler_registry(input_id, handler_tag)

    if tooltip and gui:
        build_beginner_tooltip(input_id, tooltip, gui)

    return input_id


def normalize_rgba_to_int(color, default_alpha=255):
    """
    Normalizes an input RGBA/RGB color sequence to a list of integers in range [0, 255].
    Handles float components in [0.0, 1.0], int components in [0, 255], and short RGB lists.
    """
    if not color:
        return [0, 0, 0, default_alpha]

    color_list = list(color)
    is_float = any(isinstance(c, float) for c in color_list) and all(c <= 1.0 for c in color_list) and any(c > 0.0 for c in color_list)

    if is_float:
        res = [int(c * 255.0) for c in color_list[:4]]
    else:
        res = [np_clip(c) for c in color_list[:4]]

    # Ensure 4 channels (RGBA)
    if len(res) == 3:
        res.append(default_alpha)

    return [max(0, min(255, c)) for c in res]


def np_clip(val):
    try:
        return int(val)
    except Exception:
        return 0

