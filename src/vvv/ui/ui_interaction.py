import math
import numpy as np
from vvv.utils import (
    ViewMode,
    ProfileInteractionMode,
    voxel_to_slice,
    slice_to_voxel,
)
import dearpygui.dearpygui as dpg


class NavigationTool:
    """The default tool for panning, zooming, Window/Level, and crosshair navigation."""

    def __init__(self, manager):
        self.manager = manager
        self.drag_viewer = None
        # Profile drag state
        self.profile_drag_start_p1 = None
        self.profile_drag_start_p2 = None
        self.profile_drag_start_mouse_phys = None

    def on_click(self, button):
        # Allow Left, Middle, and Right clicks to lock the viewer for dragging
        if button not in (
            dpg.mvMouseButton_Left,
            dpg.mvMouseButton_Middle,
            dpg.mvMouseButton_Right,
        ):
            return

        viewer = self.manager.get_hovered_viewer()
        if not viewer:
            return

        # Lock in the target for dragging
        self.drag_viewer = viewer
        self.manager.gui.set_context_viewer(viewer)

        # Handle Profile Manipulation Grab
        if (
            button == dpg.mvMouseButton_Left
            and viewer.profile_mode == ProfileInteractionMode.IDLE
        ):
            p_id, handle_key = self.manager._check_profile_handle_hover(viewer)
            if p_id:
                viewer.profile_mode = ProfileInteractionMode.MANIPULATING
                viewer.active_profile_id, viewer.active_handle = p_id, handle_key

                # Initialize delta-drag state for segment movement
                if handle_key == "middle":
                    p = viewer.view_state.profiles[p_id]
                    self.profile_drag_start_p1 = p.pt1_phys.copy()
                    self.profile_drag_start_p2 = p.pt2_phys.copy()

                    px, py = viewer.get_mouse_slice_coords(ignore_hover=True)
                    if px is not None:
                        shape = viewer.get_slice_shape()
                        v = slice_to_voxel(
                            px, py, viewer.slice_idx, viewer.orientation, shape
                        )
                        self.profile_drag_start_mouse_phys = (
                            viewer.view_state.display_to_world(
                                np.array(v), is_buffered=viewer._is_buffered()
                            )
                        )
                # Trigger the viewer's anchor
                self.drag_viewer.on_mouse_down()
                return

        # Trigger the viewer's anchor
        self.drag_viewer.on_mouse_down()

        if viewer.orientation != ViewMode.HISTOGRAM:
            is_cmd = (
                dpg.is_key_down(getattr(dpg, "mvKey_LWin", 343))
                or dpg.is_key_down(getattr(dpg, "mvKey_RWin", 347))
                or dpg.is_key_down(343)
                or dpg.is_key_down(347)
            )
            is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
                dpg.mvKey_RControl
            )
            is_shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(
                dpg.mvKey_RShift
            )

            is_pan_mod = is_cmd or is_ctrl

            # Crosshair snap ONLY on un-modified Left Click
            if button == dpg.mvMouseButton_Left and not is_shift and not is_pan_mod:
                px, py = viewer.get_mouse_slice_coords(ignore_hover=True)
                if px is not None:
                    viewer.update_crosshair_data(px, py)
                    self.manager.controller.sync.propagate_sync(viewer.image_id)

    def on_drag(self, drag_data):
        if self.drag_viewer:
            if self.drag_viewer.profile_mode == ProfileInteractionMode.MANIPULATING:
                px, py = self.drag_viewer.get_mouse_slice_coords(
                    ignore_hover=True, allow_outside=True
                )
                if px is not None:
                    vs = self.drag_viewer.view_state
                    p = vs.profiles[self.drag_viewer.active_profile_id]

                    # Calculate physical position directly from slice coords for smoother manipulation
                    shape = self.drag_viewer.get_slice_shape()
                    v = slice_to_voxel(
                        px,
                        py,
                        self.drag_viewer.slice_idx,
                        self.drag_viewer.orientation,
                        shape,
                    )
                    phys = vs.display_to_world(
                        np.array(v), is_buffered=self.drag_viewer._is_buffered()
                    )

                    if self.drag_viewer.active_handle == "start":
                        p.pt1_phys = phys
                    elif self.drag_viewer.active_handle == "end":
                        p.pt2_phys = phys
                    elif self.drag_viewer.active_handle == "middle":
                        delta = phys - self.profile_drag_start_mouse_phys
                        p.pt1_phys = self.profile_drag_start_p1 + delta
                        p.pt2_phys = self.profile_drag_start_p2 + delta

                    # Trigger real-time plot update
                    self._update_profile_plot(p)
                    vs.is_geometry_dirty = True
                return

            self.drag_viewer.on_drag(drag_data)

    def on_release(self, button):
        if self.drag_viewer:
            # Cleanup anchors
            self.drag_viewer.drag_start_mouse = None
            self.drag_viewer.drag_start_pan = None
            self.drag_viewer.last_dx, self.drag_viewer.last_dy = 0, 0

            if self.drag_viewer.profile_mode == ProfileInteractionMode.MANIPULATING:
                self.drag_viewer.profile_mode = ProfileInteractionMode.IDLE
                self.profile_drag_start_p1 = None
                self.profile_drag_start_p2 = None
                self.profile_drag_start_mouse_phys = None

            self.drag_viewer = None

    def _update_profile_plot(self, profile):
        win_tag = f"plot_win_{profile.id}"
        if dpg.does_item_exist(win_tag):
            distances, intensities = self.manager.controller.profiles.get_profile_data(
                self.drag_viewer.image_id, profile
            )
            if distances:
                dpg.set_value(f"series_{profile.id}", [distances, intensities])

            # Update mm/voxel info text in the plot window
            self.manager.gui.profile_ui.update_plot_info(
                self.drag_viewer.image_id, profile
            )

    def on_scroll(self, delta):
        target = self.manager.get_hovered_viewer()
        if target:
            is_cmd = (
                dpg.is_key_down(getattr(dpg, "mvKey_LWin", 343))
                or dpg.is_key_down(getattr(dpg, "mvKey_RWin", 347))
                or dpg.is_key_down(343)
                or dpg.is_key_down(347)
            )
            is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
                dpg.mvKey_RControl
            )
            is_zoom_mod = is_cmd or is_ctrl
            if is_zoom_mod:
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

    def _check_profile_handle_hover(self, viewer):
        """Returns (profile_id, handle_key) if mouse is near an endpoint, else (None, None)."""
        if not viewer or not viewer.view_state or not viewer.is_image_orientation():
            return None, None

        win_tag = f"win_{viewer.tag}"
        if not dpg.does_item_exist(win_tag):
            return None, None

        try:
            m_pos = dpg.get_drawing_mouse_pos()
        except Exception:
            return None, None

        vs = viewer.view_state
        shape = viewer.get_slice_shape()
        real_h, real_w = max(1, shape[0]), max(1, shape[1])
        pmin, pmax = viewer.current_pmin, viewer.current_pmax
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]

        v_idx, _, _, _ = viewer._ORIENTATION_MAP.get(
            viewer.orientation, (None, 0, None, None)
        )
        if v_idx is None:
            return None, None

        curr_z = viewer.slice_idx

        for p_id, p in vs.profiles.items():
            if not p.visible:
                continue

            # Map points to display voxel space
            v1 = vs.world_to_display(p.pt1_phys, is_buffered=viewer._is_buffered())
            v2 = vs.world_to_display(p.pt2_phys, is_buffered=viewer._is_buffered())
            if v1 is None or v2 is None:
                continue

            # Project endpoints to screen pixels
            tx1, ty1 = voxel_to_slice(v1[0], v1[1], v1[2], viewer.orientation, shape)
            px1 = (tx1 / real_w) * disp_w + pmin[0]
            py1 = (ty1 / real_h) * disp_h + pmin[1]

            tx2, ty2 = voxel_to_slice(v2[0], v2[1], v2[2], viewer.orientation, shape)
            px2 = (tx2 / real_w) * disp_w + pmin[0]
            py2 = (ty2 / real_h) * disp_h + pmin[1]

            # 1. Handle Proximity Check (Depth-first)
            if abs(curr_z - v1[v_idx]) <= 0.5:
                if math.hypot(m_pos[0] - px1, m_pos[1] - py1) < 12.0:
                    return p_id, "start"

            if abs(curr_z - v2[v_idx]) <= 0.5:
                if math.hypot(m_pos[0] - px2, m_pos[1] - py2) < 12.0:
                    return p_id, "end"

            # 2. Segment Draggable Middle (Center 50% of the line)
            # Check if segment is in-plane enough to be draggable
            if abs(curr_z - v1[v_idx]) <= 1.0 and abs(curr_z - v2[v_idx]) <= 1.0:
                dx, dy = px2 - px1, py2 - py1
                seg_len_sq = dx * dx + dy * dy
                if seg_len_sq > 1e-5:
                    # Projection parameter t [0..1]
                    t = ((m_pos[0] - px1) * dx + (m_pos[1] - py1) * dy) / seg_len_sq

                    if 0.25 <= t <= 0.75:
                        # Perpendicular distance check
                        proj_x = px1 + t * dx
                        proj_y = py1 + t * dy
                        if math.hypot(m_pos[0] - proj_x, m_pos[1] - proj_y) < 10.0:
                            return p_id, "middle"

        return None, None

    def on_mouse_click(self, sender, app_data, user_data):
        self.active_tool.on_click(app_data)

    def on_mouse_move(self, sender, app_data, user_data):
        # Track mouse delta for Window/Level dragging
        if not hasattr(self, "last_mouse_pos"):
            self.last_mouse_pos = app_data
            return

        dx = app_data[0] - self.last_mouse_pos[0]
        dy = app_data[1] - self.last_mouse_pos[1]
        self.last_mouse_pos = app_data

        is_shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(
            dpg.mvKey_RShift
        )
        is_right = dpg.is_mouse_button_down(dpg.mvMouseButton_Right)

        # W/L Drag: Shift + Move/Drag or Right-Drag
        is_wl_drag = is_shift or is_right

        if is_wl_drag:
            # Use the locked drag target if available so it doesn't break if the mouse leaves the viewer
            viewer = (
                getattr(self.active_tool, "drag_viewer", None)
                or self.get_hovered_viewer()
            )
            if not viewer or not viewer.view_state:
                return

            viewer._mark_lazy_interaction()

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
        if hasattr(self.gui, "roi_ui"):
            for input_id in self.gui.roi_ui.roi_selectables.values():
                if dpg.does_item_exist(input_id) and dpg.is_item_focused(input_id):
                    return

            if dpg.does_item_exist("input_roi_filter") and dpg.is_item_focused(
                "input_roi_filter"
            ):
                return

        try:
            for alias in dpg.get_aliases():
                if any(
                    k in alias
                    for k in [
                        "settings_val_",
                        "fusion_info_",
                        "input_",
                        "dicom_",
                        "info_",
                    ]
                ):
                    if dpg.does_item_exist(alias) and dpg.is_item_focused(alias):
                        item_type = dpg.get_item_type(alias)
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
        if self.gui.context_viewer:
            if not is_dragging:
                show_xh = (
                    self.gui.context_viewer.view_state.camera.show_crosshair
                    if self.gui.context_viewer.view_state
                    else False
                )
                theme = "active_black_viewer_theme" if show_xh else "black_viewer_theme"
                dpg.bind_item_theme(f"win_{self.gui.context_viewer.tag}", theme)

            # High-frequency 60fps text updates MUST be done directly, not via the heavy UI refresh flag!
            self.gui.update_sidebar_crosshair(self.gui.context_viewer)
