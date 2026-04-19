import dearpygui.dearpygui as dpg


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
):
    """A reusable UI component for a slider with + and - step buttons."""
    with dpg.group(horizontal=True):
        if has_checkbox:
            dpg.add_checkbox(tag=check_tag, enabled=False, callback=check_cb)
        dpg.add_text(label)
        dpg.add_button(
            label="-",
            width=20,
            tag=f"btn_{tag}_minus",
            user_data={"tag": tag, "dir": -1},
            enabled=not has_checkbox,
            callback=step_callback,
        )
        dpg.add_drag_float(
            tag=tag,
            width=-35,
            format=format,
            speed=1.0,
            min_value=min_val,
            max_value=max_val,
            default_value=default_val,
            enabled=not has_checkbox,
            callback=callback,
        )
        dpg.add_button(
            label="+",
            width=20,
            tag=f"btn_{tag}_plus",
            user_data={"tag": tag, "dir": 1},
            enabled=not has_checkbox,
            callback=step_callback,
        )
