import dearpygui.dearpygui as dpg


def build_section_title(label, color):
    """A reusable UI component for a section title with a horizontal separator."""
    dpg.add_text(label, color=color)
    dpg.add_separator()


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


def build_delete_button(label="\uf00d", width=20, user_data=None, callback=None, tooltip="Delete"):
    """Creates a standardized red icon close/delete button."""
    if callback is not None:
        btn = dpg.add_button(label=label, width=width, user_data=user_data, callback=callback)
    else:
        btn = dpg.add_button(label=label, width=width, user_data=user_data)
    if dpg.does_item_exist("icon_font_tag"):
        dpg.bind_item_font(btn, "icon_font_tag")
    if dpg.does_item_exist("delete_button_theme"):
        dpg.bind_item_theme(btn, "delete_button_theme")
    if tooltip:
        with dpg.tooltip(btn):
            dpg.add_text(tooltip)
    return btn


REGISTERED_INPUT_FILTER_TAGS = set()


def build_name_filter_bar(
    group_tag,
    input_tag,
    btn_clear_tag,
    on_filter_changed,
    on_clear_clicked,
    hint="Filter by name...",
    width=180,
    api=None,
):
    """Creates a standardized search/filter input field with a clear button (X)."""
    if input_tag:
        REGISTERED_INPUT_FILTER_TAGS.add(input_tag)
    with dpg.group(horizontal=True, tag=group_tag):
        dpg.add_input_text(
            hint=hint,
            tag=input_tag,
            width=width,
            callback=lambda s, a: on_filter_changed(a),
        )
        if api:
            build_beginner_tooltip(
                input_tag,
                "Type to search and filter the list by name.",
                api,
            )

        btn_clear = dpg.add_button(
            label="X",
            tag=btn_clear_tag,
            width=24,
            callback=lambda: on_clear_clicked(),
        )
        if api:
            build_beginner_tooltip(
                btn_clear,
                "Clears the name filter.",
                api,
            )
    return group_tag


def build_batch_action_toolbar(
    tag_prefix,
    on_color_changed=None,
    on_show_clicked=None,
    on_hide_clicked=None,
    on_toggle_visible=None,
    on_toggle_names=None,
    on_reset_colors=None,
    on_snap_clicked=None,
    on_delete_clicked=None,
    show_contour=False,
    on_contour_clicked=None,
    show_above_overlay=False,
    on_above_overlay_clicked=None,
    api=None,
):
    """Creates a standardized icon-based batch action toolbar.
    Icon order: Color Picker, Reset Colors, Toggle Visible (or Show/Hide), Toggle Names, Snap All, (Contour/Overlay), Delete
    """
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
            with dpg.tooltip(col_picker):
                dpg.add_text("Apply color to listed/filtered items")

        # 2. Reset Colors
        if on_reset_colors:
            btn_reset_col = dpg.add_button(
                label="\uf0e2",
                width=20,
                tag=f"{tag_prefix}_batch_reset_colors",
                callback=lambda: on_reset_colors(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_reset_col, "icon_font_tag")
            with dpg.tooltip(btn_reset_col):
                dpg.add_text("Reset colors to default initial sequence")

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
            with dpg.tooltip(btn_toggle_vis):
                dpg.add_text("Toggle show/hide listed/filtered items")
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
                with dpg.tooltip(btn_show):
                    dpg.add_text("Show listed/filtered items")

            if on_hide_clicked:
                btn_hide = dpg.add_button(
                    label="\uf070",
                    width=20,
                    tag=f"{tag_prefix}_batch_hide",
                    callback=lambda: on_hide_clicked(),
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_hide, "icon_font_tag")
                with dpg.tooltip(btn_hide):
                    dpg.add_text("Hide listed/filtered items")

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
            with dpg.tooltip(btn_names):
                dpg.add_text("Toggle name labels for listed/filtered items")

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
            with dpg.tooltip(btn_snap):
                dpg.add_text("Snap all items to nearest voxel grid center")

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
            with dpg.tooltip(btn_contour):
                dpg.add_text("Show as contour")

        if show_above_overlay and on_above_overlay_clicked:
            btn_overlay = dpg.add_button(
                label="\uf5fd",
                width=20,
                tag=f"{tag_prefix}_batch_overlay",
                callback=lambda: on_above_overlay_clicked(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_overlay, "icon_font_tag")
            with dpg.tooltip(btn_overlay):
                dpg.add_text("Toggle on top of fusion overlay")

        # 6. Delete
        if on_delete_clicked:
            build_delete_button(
                label="\uf00d",
                width=20,
                callback=lambda: on_delete_clicked(),
                tooltip="Delete listed/filtered items",
            )

def build_beginner_tooltip(parent, text, gui):
    """A reusable tooltip attached to an existing widget that only appears when Beginner Mode is active."""
    tag = dpg.add_tooltip(parent=parent, show=getattr(gui, "is_beginner_mode", False))
    dpg.add_text(text, parent=tag, color=gui.ui_cfg["colors"].get("text_dim", [150, 150, 150]))
    if not hasattr(gui, "beginner_tags"):
        gui.beginner_tags = []
    gui.beginner_tags.append(tag)
    return tag

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
