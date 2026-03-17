import dearpygui.dearpygui as dpg
import json
import os
from .core import DEFAULT_SETTINGS


class SettingsWindow:
    def __init__(self, controller):
        self.controller = controller
        self.window_tag = "settings_floating_window"
        self.tree_container = "settings_tree_container"

    def show(self):
        # If it's already open, just bring it to the front
        if dpg.does_item_exist(self.window_tag):
            dpg.focus_item(self.window_tag)
            return

        with dpg.window(
            tag=self.window_tag,
            label="Settings",
            width=480,
            height=650,
            no_collapse=False,
            on_close=lambda: dpg.delete_item(self.window_tag),
        ):
            dpg.add_spacer(height=5)

            # Header Path
            with dpg.group(horizontal=True):
                btn = dpg.add_button(label="\uf0c5", callback=self.copy_path)
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn, "icon_font_tag")
                dpg.add_input_text(
                    default_value=str(self.controller.settings.config_path),
                    readonly=True,
                    width=-1,
                )

            dpg.add_spacer(height=5)
            # Legend
            with dpg.group(horizontal=True):
                dpg.add_text("Legend: ")
                dpg.add_text("Default", color=[150, 150, 150])
                dpg.add_text("Customized", color=[0, 255, 255])
                dpg.add_text("Unsaved", color=[255, 255, 0])

            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Body Container
            # FIX: Increased from -45 to -70 to guarantee the footer buttons don't get pushed off the bottom edge!
            with dpg.child_window(tag=self.tree_container, height=-70, border=False):
                pass  # Populated dynamically below!

            # Footer
            dpg.add_separator()
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", width=80, callback=self.on_save)
                dpg.add_button(label="Reload", width=80, callback=self.on_reload)
                dpg.add_button(
                    label="Reset Defaults", width=120, callback=self.on_reset
                )
                dpg.add_spacer(width=10)
                dpg.add_text("", tag="settings_status_text")

        self.build_tree()

        # Center the floating window
        vp_width = dpg.get_viewport_client_width()
        vp_height = dpg.get_viewport_client_height()
        dpg.set_item_pos(
            self.window_tag,
            [max(50, vp_width // 2 - 240), max(50, vp_height // 2 - 325)],
        )

    def copy_path(self):
        dpg.set_clipboard_text(str(self.controller.settings.config_path))
        self.set_status("Copied to clipboard!", [0, 255, 0])

    def set_status(self, msg, color=[150, 255, 150]):
        if dpg.does_item_exist("settings_status_text"):
            dpg.set_value("settings_status_text", msg)
            dpg.configure_item("settings_status_text", color=color)

    def get_saved_dict(self):
        """Reads the exact current state of the config file on disk."""
        path = self.controller.settings.config_path
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except:
                pass
        return {}

    def build_tree(self):
        """Recursively auto-generates the UI based on the Settings dictionary."""
        if not dpg.does_item_exist(self.tree_container):
            return
        dpg.delete_item(self.tree_container, children_only=True)

        live_dict = self.controller.settings.data
        dpg.push_container_stack(self.tree_container)
        self._build_node(live_dict, [])
        dpg.pop_container_stack()

        self.update_label_colors()

    def _build_node(self, parent_dict, keys_path):
        for k, v in parent_dict.items():
            curr_keys = keys_path + [k]

            if isinstance(v, dict):
                # Folder Node
                with dpg.tree_node(
                    label=k.replace("_", " ").capitalize(), default_open=True
                ):
                    self._build_node(v, curr_keys)
            else:
                # Leaf Node (Input Widget)
                is_color = len(keys_path) > 0 and keys_path[0] == "colors"
                text_tag = f"settings_lbl_{'-'.join(curr_keys)}"
                widget_tag = f"settings_val_{'-'.join(curr_keys)}"

                with dpg.group(horizontal=True):
                    dpg.add_text(f"{k.replace('_', ' ').capitalize()}:", tag=text_tag)

                    # Closure to lock in the specific keys for the callback
                    def make_callback(keys):
                        return lambda s, a: self.on_value_changed(keys, a)

                    cb = make_callback(curr_keys)

                    # Dynamic Widget Generation based on Python type()
                    if is_color:
                        dpg.add_color_edit(
                            default_value=v,
                            callback=cb,
                            no_alpha=False,
                            width=150,
                            tag=widget_tag,
                        )
                    elif isinstance(v, bool):
                        dpg.add_checkbox(default_value=v, callback=cb, tag=widget_tag)
                    elif isinstance(v, int):
                        if "shortcuts" in keys_path:
                            dpg.add_input_text(
                                default_value=str(v),
                                callback=cb,
                                width=150,
                                tag=widget_tag,
                            )
                        else:
                            dpg.add_input_int(
                                default_value=v, callback=cb, width=150, tag=widget_tag
                            )
                    elif isinstance(v, float):
                        dpg.add_input_float(
                            default_value=v,
                            callback=cb,
                            width=150,
                            step=0.05 if v < 1 else 1.0,
                            tag=widget_tag,
                        )
                    elif isinstance(v, str):
                        if k == "active_viewer_mode":
                            dpg.add_combo(
                                items=["hybrid", "click", "hover"],
                                default_value=v,
                                callback=cb,
                                width=150,
                                tag=widget_tag,
                            )
                        else:
                            dpg.add_input_text(
                                default_value=v, callback=cb, width=150, tag=widget_tag
                            )

                    # --- Reset Button ---
                    def make_reset_cb(keys, w_tag):
                        return lambda: self.reset_single_value(keys, w_tag)

                    btn = dpg.add_button(
                        label="\uf01e", callback=make_reset_cb(curr_keys, widget_tag)
                    )
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn, "icon_font_tag")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn, "icon_button_theme")

    def reset_single_value(self, keys, widget_tag):
        """Fetches the factory default for a single setting and applies it."""
        val = DEFAULT_SETTINGS
        for k in keys:
            val = val[k]

        # Safely update the widget on screen
        if dpg.does_item_exist(widget_tag):
            if "shortcuts" in keys:
                dpg.set_value(widget_tag, str(val))
            else:
                dpg.set_value(widget_tag, val)

        # Push the change to the controller
        self.on_value_changed(keys, val)

    def on_value_changed(self, keys, value):
        # Format shortcuts strings/ints cleanly
        if "shortcuts" in keys:
            try:
                value = int(value)
            except ValueError:
                pass
        self.controller.update_setting(keys, value)
        self.update_label_colors()  # Instantly updates text colors without rebuilding the UI!

    def _get_val_for_cmp(self, val, keys_path):
        """Helper to safely compare color tuples vs lists."""
        is_color = len(keys_path) > 0 and keys_path[0] == "colors"
        if is_color and isinstance(val, (list, tuple)):
            return [int(x) for x in val[:3]]
        return val

    def _evaluate_color(self, val, keys_path, default_dict, saved_dict):
        """Calculates the 3-way difference to determine the text label color."""
        def_v = default_dict
        for k in keys_path:
            def_v = def_v.get(k, {}) if isinstance(def_v, dict) else None

        sav_v = saved_dict
        for k in keys_path:
            sav_v = sav_v.get(k, {}) if isinstance(sav_v, dict) else None

        v_cmp = self._get_val_for_cmp(val, keys_path)
        d_cmp = self._get_val_for_cmp(def_v, keys_path)
        s_cmp = self._get_val_for_cmp(sav_v, keys_path)

        is_custom = v_cmp != d_cmp
        is_unsaved = (s_cmp is not None and v_cmp != s_cmp) or (
            s_cmp is None and is_custom
        )

        if is_unsaved:
            return [255, 255, 0]  # Yellow
        elif is_custom:
            return [0, 255, 255]  # Cyan
        return [150, 150, 150]  # Gray (Default)

    def update_label_colors(self):
        saved_dict = self.get_saved_dict()
        live_dict = self.controller.settings.data

        def traverse(parent_dict, keys_path):
            for k, v in parent_dict.items():
                curr_keys = keys_path + [k]
                if isinstance(v, dict):
                    traverse(v, curr_keys)
                else:
                    text_tag = f"settings_lbl_{'-'.join(curr_keys)}"
                    if dpg.does_item_exist(text_tag):
                        c = self._evaluate_color(
                            v, curr_keys, DEFAULT_SETTINGS, saved_dict
                        )
                        dpg.configure_item(text_tag, color=c)

        traverse(live_dict, [])

    def on_save(self):
        self.controller.save_settings()
        self.set_status("Settings saved!")
        self.update_label_colors()

    def on_reload(self):
        self.controller.reload_settings()
        self.set_status("Settings reloaded!")
        self.build_tree()

    def on_reset(self):
        self.controller.reset_settings()
        self.set_status("Settings reset to defaults!")
        self.build_tree()
