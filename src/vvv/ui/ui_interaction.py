import math
from vvv.utils import ViewMode
import dearpygui.dearpygui as dpg


class NavigationTool:
    """The default tool for panning, zooming, Window/Level, and crosshair navigation."""

    def __init__(self, manager):
        self.manager = manager
        self.drag_viewer = None

    def on_click(self, button):
        if button != dpg.mvMouseButton_Left:
            return

        viewer = self.manager.get_hovered_viewer()
        if not viewer:
            return

        # Lock in the target for dragging
        self.drag_viewer = viewer
        self.manager.gui.set_context_viewer(viewer)

        # Trigger the viewer's anchor
        self.drag_viewer.on_mouse_down()

        if viewer.orientation != ViewMode.HISTOGRAM:
            if not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(
                dpg.mvKey_LControl
            ):
                px, py = viewer.get_mouse_slice_coords(ignore_hover=True)
                if px is not None:
                    viewer.update_crosshair_data(px, py)
                    self.manager.controller.sync.propagate_sync(viewer.image_id)

    def on_drag(self, drag_data):
        if self.drag_viewer:
            self.drag_viewer.on_drag(drag_data)

    def on_release(self, button):
        if self.drag_viewer:
            # Cleanup anchors
            self.drag_viewer.drag_start_mouse = None
            self.drag_viewer.drag_start_pan = None
            self.drag_viewer.last_dx, self.drag_viewer.last_dy = 0, 0

            self.drag_viewer = None

    def on_scroll(self, delta):
        target = self.manager.get_hovered_viewer()
        if target:
            is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
                dpg.mvKey_RControl
            )
            if is_ctrl:
                target.on_zoom("in" if delta > 0 else "out")
            else:
                target.on_scroll(int(delta))

    def on_key_press(self, key):
        target = self.manager.get_interaction_target()
        if target:
            target.on_key_press(key)


class InteractionManager:
    """Central hub routing mouse and keyboard events to the currently active tool."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

        # --- TOOL STATE MACHINE ---
        self.tools = {
            "navigation": NavigationTool(self)
            # Phase 5: "roi_draw": RoiDrawingTool(self),
        }
        self.active_tool_id = "navigation"

    @property
    def active_tool(self):
        return self.tools[self.active_tool_id]

    def set_tool(self, tool_id):
        if tool_id in self.tools:
            self.active_tool_id = tool_id
            self.gui.show_status_message(f"Tool changed: {tool_id.capitalize()}")

    def get_hovered_viewer(self):
        for viewer in self.controller.viewers.values():
            if dpg.is_item_hovered(f"win_{viewer.tag}"):
                return viewer
        return None

    def get_interaction_target(self):
        mode = self.controller.settings.data["interaction"].get(
            "active_viewer_mode", "hybrid"
        )
        if mode == "click":
            return self.gui.context_viewer
        return self.get_hovered_viewer() or self.gui.context_viewer

    # ==========================================
    # DPG event routers
    # ==========================================

    def on_mouse_click(self, sender, app_data, user_data):
        self.active_tool.on_click(app_data)

    def on_mouse_move(self, sender, app_data, user_data):
        import dearpygui.dearpygui as dpg

        current_pos = app_data

        # Initialize the tracker on the first frame
        if not hasattr(self, "last_mouse_pos"):
            self.last_mouse_pos = current_pos
            return

        # Calculate how far the mouse moved since the last frame
        dx = current_pos[0] - self.last_mouse_pos[0]
        dy = current_pos[1] - self.last_mouse_pos[1]
        self.last_mouse_pos = current_pos

        # Check for Shift (handling cross-platform key codes)
        is_shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(
            dpg.mvKey_RShift
        )

        if is_shift:
            viewer = self.get_hovered_viewer()
            if not viewer or not viewer.view_state:
                return

            vs = viewer.view_state

            base_sens = self.controller.settings.data["interaction"].get(
                "wl_drag_sensitivity", 1.0
            )

            # Exponential scaling for Window Width (Prevents "dead zones" at small widths)
            ww_multiplier = math.exp(dx * base_sens * 0.005)
            new_ww = max(1e-5, vs.display.ww * ww_multiplier)

            # Linear scaling for Level, proportional to the newly calculated width
            new_wl = vs.display.wl - (dy * new_ww * base_sens * 0.002)

            viewer.update_window_level(new_ww, new_wl)

    def on_mouse_drag(self, sender, app_data, user_data):
        if isinstance(app_data, int):
            return
        self.active_tool.on_drag(app_data)

    def on_mouse_release(self, sender, app_data, user_data):
        self.active_tool.on_release(app_data)

    def on_mouse_scroll(self, sender, app_data, user_data):
        self.active_tool.on_scroll(app_data)

    def on_key_press(self, sender, app_data, user_data):
        # Prevent keyboard shortcuts from triggering while typing in text/number fields
        active_item = dpg.get_active_item()
        if active_item:
            try:
                item_type = dpg.get_item_type(active_item)
                if item_type and "Input" in item_type:
                    return
            except Exception:
                pass

        # Intercept global Application shortcuts here (like Ctrl+O)
        is_cmd = dpg.is_key_down(dpg.mvKey_LWin) or dpg.is_key_down(dpg.mvKey_RWin)
        is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
            dpg.mvKey_RControl
        )

        if app_data == dpg.mvKey_O and (is_ctrl or is_cmd):
            self.gui.on_open_file_clicked()
            return

        # DICOM Browser Arrow Keys
        dicom_win = getattr(self.gui, "dicom_window", None)
        if (
            dicom_win
            and dpg.does_item_exist(dicom_win.window_tag)
            and dpg.is_item_shown(dicom_win.window_tag)
        ):
            if app_data == dpg.mvKey_Up:
                dicom_win.move_selection(-1)
                return
            elif app_data == dpg.mvKey_Down:
                dicom_win.move_selection(1)
                return

        # Pass everything else to the Active Tool
        self.active_tool.on_key_press(app_data)

    def update_trackers(self):
        """Continuously called by the render loop to update hover states and UI text."""
        mode = self.controller.settings.data["interaction"].get(
            "active_viewer_mode", "hybrid"
        )
        hover_viewer = self.get_hovered_viewer()

        # Safely check if the active tool is currently dragging something
        is_dragging = getattr(self.active_tool, "drag_viewer", None) is not None

        if mode == "hover":
            if (
                hover_viewer
                and hover_viewer != self.gui.context_viewer
                and not is_dragging
            ):
                self.gui.set_context_viewer(hover_viewer)

        # 1. Update viewer text individually
        for viewer in self.controller.viewers.values():
            viewer.update_tracker()

        # 2. OUTSIDE THE LOOP: Update the master UI state safely
        if self.gui.context_viewer and not is_dragging:
            show_xh = (
                self.gui.context_viewer.view_state.camera.show_crosshair
                if self.gui.context_viewer.view_state
                else False
            )
            theme = "active_black_viewer_theme" if show_xh else "black_viewer_theme"
            dpg.bind_item_theme(f"win_{self.gui.context_viewer.tag}", theme)

            # High-frequency 60fps text updates MUST be done directly, not via the heavy UI refresh flag!
            self.gui.update_sidebar_crosshair(self.gui.context_viewer)
