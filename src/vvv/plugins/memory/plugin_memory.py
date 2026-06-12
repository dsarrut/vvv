import os
import numpy as np
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
                dpg.add_text("Total Memory Usage:")
                dpg.add_text("Computing...", tag=self._t("total_val"), color=[200, 200, 255])

            dpg.add_spacer(height=5)
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Refresh button
            with dpg.group(horizontal=True):
                dpg.add_button(label="Refresh", width=100, callback=self.refresh)
                dpg.add_text("Displays memory usage of all loaded volumes, caches and process.", color=[150, 150, 150])

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

        # 2. Collect all loaded volumes
        all_roi_ids = set()
        view_states = self._api.get_view_states()
        for vs in view_states.values():
            all_roi_ids.update(vs.rois.keys())

        volumes_items = list(self._api.get_volumes().items())
        view_state_keys = set(view_states.keys())

        vol_mem_info = {}

        for vol_id, vol in volumes_items:
            vol_mem = getattr(vol, "memory_mb", 0.0)

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

            vol_mem_info[vol_id] = {
                "id": vol_id,
                "type": v_type,
                "name": vol.name,
                "shape": shape_str,
                "dtype": getattr(vol, "pixel_type", ""),
                "raw_mem": vol_mem,
                "resampled_base": 0.0,
                "resampled_overlay": 0.0,
                "mip_cache": 0.0,
                "slice_cache": 0.0,
            }

        # 3. Calculate Resampled Base and Overlay memory from view states
        for vs_id, vs in view_states.items():
            # Base display buffer (rotation preview resampling)
            if vs.base_display_data is not None and isinstance(vs.base_display_data, np.ndarray):
                mem_mb = vs.base_display_data.nbytes / (1024 * 1024)
                if vs_id in vol_mem_info:
                    vol_mem_info[vs_id]["resampled_base"] += mem_mb

            # Overlay display buffer (registration resampling onto base grid)
            if vs.display.overlay.image_id:
                ov_id = vs.display.overlay.image_id
                if vs.display.overlay_data is not None and isinstance(vs.display.overlay_data, np.ndarray):
                    mem_mb = vs.display.overlay_data.nbytes / (1024 * 1024)
                    if ov_id in vol_mem_info:
                        vol_mem_info[ov_id]["resampled_overlay"] += mem_mb

        # 4. Calculate MIP cache from MIP plugin
        mip_plugin = next(
            (p for p in self._api._gui.plugins if p.plugin_id == "mip_plugin"), None
        )
        if mip_plugin and hasattr(mip_plugin, "_controller") and hasattr(mip_plugin._controller, "_caches"):
            for tag, cache_dict in mip_plugin._controller._caches.items():
                for k, v in list(cache_dict.items()):
                    # Key format: (img_id, time_idx, orientation, depth_cueing, current_angle, id(data_3d))
                    if isinstance(k, tuple) and len(k) > 0:
                        img_id = k[0]
                        if isinstance(v, np.ndarray):
                            mem_mb = v.nbytes / (1024 * 1024)
                            if img_id in vol_mem_info:
                                vol_mem_info[img_id]["mip_cache"] += mem_mb

        # 5. Calculate Viewer 2D slice caches
        for viewer in self._api.get_viewers().values():
            # Base image slice cache
            if viewer.image_id and hasattr(viewer, "_preview_slices") and viewer._preview_slices:
                for k, v in list(viewer._preview_slices.items()):
                    if isinstance(v, np.ndarray):
                        mem_mb = v.nbytes / (1024 * 1024)
                        if viewer.image_id in vol_mem_info:
                            vol_mem_info[viewer.image_id]["slice_cache"] += mem_mb
                    elif isinstance(v, tuple):
                        for item in v:
                            if isinstance(item, np.ndarray):
                                mem_mb = item.nbytes / (1024 * 1024)
                                if viewer.image_id in vol_mem_info:
                                    vol_mem_info[viewer.image_id]["slice_cache"] += mem_mb

            # Overlay slice cache
            vs = viewer.view_state
            if vs and vs.display.overlay.image_id and hasattr(viewer, "_overlay_preview_slices") and viewer._overlay_preview_slices:
                ov_id = vs.display.overlay.image_id
                for k, v in list(viewer._overlay_preview_slices.items()):
                    if isinstance(v, np.ndarray):
                        mem_mb = v.nbytes / (1024 * 1024)
                        if ov_id in vol_mem_info:
                            vol_mem_info[ov_id]["slice_cache"] += mem_mb
                    elif isinstance(v, tuple):
                        for item in v:
                            if isinstance(item, np.ndarray):
                                mem_mb = item.nbytes / (1024 * 1024)
                                if ov_id in vol_mem_info:
                                    vol_mem_info[ov_id]["slice_cache"] += mem_mb

        # 6. Build final table rows
        total_vol_mem = 0.0
        table_rows = []
        dim_color = self._api.get_ui_config()["colors"].get("text_dim", [150, 150, 150])

        # Group and order
        for vol_id, info in vol_mem_info.items():
            total_item_mem = (
                info["raw_mem"]
                + info["resampled_base"]
                + info["resampled_overlay"]
                + info["mip_cache"]
                + info["slice_cache"]
            )
            total_vol_mem += total_item_mem

            # Add main row
            table_rows.append({
                "id": vol_id,
                "type": info["type"],
                "name": info["name"],
                "shape": info["shape"],
                "dtype": info["dtype"],
                "mem": f"{total_item_mem:.2f} MB",
                "mem_val": total_item_mem,
                "is_subrow": False,
            })

            # Add sub-rows if any cache/buffer is > 0.01 MB to avoid cluttering with zero entries
            if info["raw_mem"] > 0.01 and total_item_mem > info["raw_mem"] + 0.01:
                table_rows.append({
                    "id": "",
                    "type": "  └─ Raw Volume Data",
                    "name": "",
                    "shape": "",
                    "dtype": "",
                    "mem": f"{info['raw_mem']:.2f} MB",
                    "mem_val": info["raw_mem"],
                    "is_subrow": True,
                })
            if info["resampled_base"] > 0.01:
                table_rows.append({
                    "id": "",
                    "type": "  └─ Resampled Base Buffer",
                    "name": "",
                    "shape": "",
                    "dtype": "",
                    "mem": f"{info['resampled_base']:.2f} MB",
                    "mem_val": info["resampled_base"],
                    "is_subrow": True,
                })
            if info["resampled_overlay"] > 0.01:
                table_rows.append({
                    "id": "",
                    "type": "  └─ Resampled Overlay Buffer",
                    "name": "",
                    "shape": "",
                    "dtype": "",
                    "mem": f"{info['resampled_overlay']:.2f} MB",
                    "mem_val": info["resampled_overlay"],
                    "is_subrow": True,
                })
            if info["mip_cache"] > 0.01:
                table_rows.append({
                    "id": "",
                    "type": "  └─ MIP Projection Cache",
                    "name": "",
                    "shape": "",
                    "dtype": "",
                    "mem": f"{info['mip_cache']:.2f} MB",
                    "mem_val": info["mip_cache"],
                    "is_subrow": True,
                })
            if info["slice_cache"] > 0.01:
                table_rows.append({
                    "id": "",
                    "type": "  └─ Viewer 2D Slice Cache",
                    "name": "",
                    "shape": "",
                    "dtype": "",
                    "mem": f"{info['slice_cache']:.2f} MB",
                    "mem_val": info["slice_cache"],
                    "is_subrow": True,
                })

        total_val_tag = self._t("total_val")
        if dpg.does_item_exist(total_val_tag):
            dpg.set_value(total_val_tag, f"{total_vol_mem:.2f} MB")

        # Refill table rows
        if dpg.does_item_exist(self.table_id):
            dpg.delete_item(self.table_id, children_only=True, slot=1)
            
            # Sort main rows but keep sub-rows directly underneath their parents
            # To do that, we sort the grouped entries before flattening them into table_rows.
            # We already generated table_rows, but we can do a structured sort.
            # Let's sort the vol_mem_info dict keys by type, then by total memory DESC.
            sorted_vol_ids = sorted(
                vol_mem_info.keys(),
                key=lambda x: (
                    vol_mem_info[x]["type"],
                    -(vol_mem_info[x]["raw_mem"] +
                      vol_mem_info[x]["resampled_base"] +
                      vol_mem_info[x]["resampled_overlay"] +
                      vol_mem_info[x]["mip_cache"] +
                      vol_mem_info[x]["slice_cache"])
                )
            )

            # Re-generate table_rows in sorted order
            final_sorted_rows = []
            for vol_id in sorted_vol_ids:
                for row in table_rows:
                    # Match row by parent or if it's the main row matching the vol_id
                    if row["id"] == vol_id:
                        final_sorted_rows.append(row)
                        # Find all subsequent subrows for this parent
                        parent_idx = table_rows.index(row)
                        sub_idx = parent_idx + 1
                        while sub_idx < len(table_rows) and table_rows[sub_idx]["id"] == "" and table_rows[sub_idx]["is_subrow"]:
                            final_sorted_rows.append(table_rows[sub_idx])
                            sub_idx += 1
                        break

            for row_data in final_sorted_rows:
                with dpg.table_row(parent=self.table_id):
                    col = dim_color if row_data["is_subrow"] else None
                    dpg.add_text(row_data["id"], color=col if col else [255, 255, 255])
                    dpg.add_text(row_data["type"], color=col if col else [255, 255, 255])
                    dpg.add_text(row_data["name"], color=col if col else [255, 255, 255])
                    dpg.add_text(row_data["shape"], color=col if col else [255, 255, 255])
                    dpg.add_text(row_data["dtype"], color=col if col else [255, 255, 255])
                    dpg.add_text(row_data["mem"], color=col if col else [255, 255, 255])

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
