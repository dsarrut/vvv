import dearpygui.dearpygui as dpg


def build_section_title(label, color):
    """A reusable UI component for a section title with a horizontal separator."""
    dpg.add_text(label, color=color)
    dpg.add_separator()


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
            dpg.add_checkbox(tag=check_tag, enabled=False, callback=check_cb)

        if has_color:
            dpg.add_color_edit(
                default_value=color_default,
                tag=color_tag,
                callback=color_cb,
                no_inputs=True,
                no_label=True,
                no_alpha=True,
                width=20,
                height=20,
            )

        dpg.add_text(label)

        # 1. The Slider
        # Width = -55 ensures room for the two 20px buttons + padding on the right
        dpg.add_drag_float(
            tag=tag,
            width=-55,
            format=format,
            speed=1.0,
            min_value=min_val,
            max_value=max_val,
            default_value=default_val,
            enabled=not has_checkbox,
            callback=callback,
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
