import time
import dearpygui.dearpygui as dpg


def show_message(title, message):
    """Displays a generic blocking popup message."""
    modal_tag = "generic_message_modal"
    if dpg.does_item_exist(modal_tag):
        dpg.delete_item(modal_tag)

    with dpg.window(
            tag=modal_tag, modal=True, show=True, label=title, no_collapse=True, width=450
    ):
        dpg.add_text(message, wrap=430)
        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=160)
            dpg.add_button(
                label="OK", width=100, callback=lambda: dpg.delete_item(modal_tag)
            )

    vp_width = max(dpg.get_viewport_client_width(), 800)
    vp_height = max(dpg.get_viewport_client_height(), 600)
    dpg.set_item_pos(modal_tag, [vp_width // 2 - 225, vp_height // 2 - 100])


def show_status_message(gui, message, duration=3.0, color=None):
    """Displays a temporary text status in the top right menu bar."""
    if color is None:
        color = gui.ui_cfg["colors"]["text_status_ok"]

    if dpg.does_item_exist("global_status_text"):
        dpg.set_value("global_status_text", f"[{message}]")
        dpg.configure_item("global_status_text", color=color)

    gui.status_message_expire_time = time.time() + duration


def show_loading_modal(title, message, progress=0.5):
    """Creates or updates a centralized loading modal with a progress bar."""
    modal_tag = "loading_modal"

    if not dpg.does_item_exist(modal_tag):
        with dpg.window(
                tag=modal_tag,
                modal=True,
                show=True,
                no_title_bar=True,
                no_resize=True,
                no_move=True,
                width=350,
                height=100,
        ):
            dpg.add_text(f"{title}\n{message}", tag="loading_text")
            dpg.add_spacer(height=5)
            dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=progress)

        vp_width = max(dpg.get_viewport_client_width(), 800)
        vp_height = max(dpg.get_viewport_client_height(), 600)
        dpg.set_item_pos(modal_tag, [vp_width // 2 - 175, vp_height // 2 - 50])
    else:
        # If it already exists, just update the text and progress to avoid flickering!
        dpg.set_value("loading_text", f"{title}\n{message}")
        dpg.set_value("loading_progress", progress)


def hide_loading_modal():
    """Safely removes the loading modal."""
    if dpg.does_item_exist("loading_modal"):
        dpg.delete_item("loading_modal")