import os
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginProtocol, PluginTagMixin

class MemoryPlugin(PluginProtocol, PluginTagMixin):
    plugin_id = "memory_plugin"
    label = "Memory"
    description = "Tracks system and volume memory consumption."
    order = 100
    show_in_sidebar = False  # Hidden from the sidebar

    def __init__(self):
        self._plugin_id = self.plugin_id
        self.window_tag = self._t("window")
        self.table_id = self._t("table")
        self._api = None

    def create_ui(self, parent, api: PluginAPI) -> None:
        self._api = api
        
        # Add the menu directly to the main menu bar
        if dpg.does_item_exist("main_menu_bar"):
            # If the menu already exists, delete it first to avoid duplicates on rebuilds
            if dpg.does_item_exist(self._t("menu")):
                dpg.delete_item(self._t("menu"))
                
            with dpg.menu(label="Memory", parent="main_menu_bar", tag=self._t("menu")):
                dpg.add_menu_item(
                    label="Memory Synthesis...",
                    callback=self.toggle_memory_window,
                )

    def toggle_memory_window(self, sender=None, app_data=None, user_data=None):
        if dpg.does_item_exist(self.window_tag):
            dpg.delete_item(self.window_tag)
            return

        with dpg.window(
            tag=self.window_tag,
            label="Memory Synthesis",
            width=650,
            height=450,
            on_close=lambda: dpg.delete_item(self.window_tag),
        ):
            dpg.add_spacer(height=5)

            # Process / system overall memory
            with dpg.group(horizontal=True):
                dpg.add_text("Process Memory RSS:")
                dpg.add_text("Computing...", tag=self._t("process_val"), color=[200, 200, 255])
                dpg.add_spacer(width=20)
                dpg.add_text("Total Volume Memory:")
                dpg.add_text("Computing...", tag=self._t("total_val"), color=[200, 200, 255])

            dpg.add_spacer(height=5)
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Refresh button
            with dpg.group(horizontal=True):
                dpg.add_button(label="Refresh", width=100, callback=self.refresh)
                dpg.add_text("Displays memory usage of all loaded volumes and process.", color=[150, 150, 150])

            dpg.add_spacer(height=5)

            with dpg.child_window(height=-1, border=True):
                with dpg.table(
                    tag=self.table_id,
                    header_row=True,
                    resizable=True,
                    borders_outerH=True,
                    borders_innerH=True,
                    borders_outerV=True,
                    borders_innerV=True,
                    scrollY=True,
                ):
                    dpg.add_table_column(label="ID")
                    dpg.add_table_column(label="Type")
                    dpg.add_table_column(label="Name")
                    dpg.add_table_column(label="Dimensions")
                    dpg.add_table_column(label="Data Type")
                    dpg.add_table_column(label="Memory")

            self.refresh()

            # Center the floating window
            vp_width = dpg.get_viewport_client_width()
            vp_height = dpg.get_viewport_client_height()
            dpg.set_item_pos(
                self.window_tag,
                [max(50, vp_width // 2 - 325), max(50, vp_height // 2 - 225)],
            )

    def refresh(self, sender=None, app_data=None, user_data=None):
        if not dpg.does_item_exist(self.window_tag) or not self._api:
            return

        # 1. Update Process memory
        try:
            import psutil
            process = psutil.Process(os.getpid())
            process_mem_mb = process.memory_info().rss / (1024 * 1024)
            process_str = f"{process_mem_mb:.2f} MB"
        except ImportError:
            process_str = "psutil N/A"

        process_val_tag = self._t("process_val")
        if dpg.does_item_exist(process_val_tag):
            dpg.set_value(process_val_tag, process_str)

        # 2. Get all volumes, categorizing them
        loaded_images = []
        all_roi_ids = set()
        
        view_states = self._api.get_view_states()
        for vs in view_states.values():
            all_roi_ids.update(vs.rois.keys())

        volumes_items = list(self._api.get_volumes().items())
        view_state_keys = set(view_states.keys())

        total_vol_mem = 0.0

        for vol_id, vol in volumes_items:
            vol_mem = getattr(vol, "memory_mb", 0.0)
            total_vol_mem += vol_mem

            if vol_id in view_state_keys:
                v_type = "Image"
            elif vol_id in all_roi_ids:
                v_type = "Label/ROI"
            else:
                v_type = "Other"

            # Dimensions representation
            shape_str = f"{vol.shape3d[0]}x{vol.shape3d[1]}x{vol.shape3d[2]}"
            if getattr(vol, "num_timepoints", 1) > 1:
                shape_str += f" x {vol.num_timepoints}t"

            loaded_images.append({
                "id": vol_id,
                "type": v_type,
                "name": vol.name,
                "shape": shape_str,
                "dtype": getattr(vol, "pixel_type", ""),
                "mem": f"{vol_mem:.2f} MB",
                "mem_val": vol_mem
            })

        total_val_tag = self._t("total_val")
        if dpg.does_item_exist(total_val_tag):
            dpg.set_value(total_val_tag, f"{total_vol_mem:.2f} MB")

        # Clear and refill table rows
        if dpg.does_item_exist(self.table_id):
            dpg.delete_item(self.table_id, children_only=True, slot=1)
            
            # Sort by type, then memory desc
            loaded_images.sort(key=lambda x: (x["type"], -x["mem_val"]))

            for row_data in loaded_images:
                with dpg.table_row(parent=self.table_id):
                    dpg.add_text(row_data["id"])
                    dpg.add_text(row_data["type"])
                    dpg.add_text(row_data["name"])
                    dpg.add_text(row_data["shape"])
                    dpg.add_text(row_data["dtype"])
                    dpg.add_text(row_data["mem"])

    def update(self, api: PluginAPI) -> None:
        pass

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        if dpg.does_item_exist(self.window_tag):
            self.refresh()

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return {}

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        pass

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        if dpg.does_item_exist(self.window_tag):
            dpg.delete_item(self.window_tag)
        if dpg.does_item_exist(self._t("menu")):
            dpg.delete_item(self._t("menu"))
