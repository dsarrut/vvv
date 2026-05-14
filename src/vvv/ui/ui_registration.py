import os
import math
import threading
import queue
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog
from vvv.utils import ViewMode, voxel_to_slice
from vvv.ui.ui_components import build_stepped_slider, build_section_title
from vvv.ui.render_strategy import compute_preview_2d_affine, compute_overlay_preview_2d_affine


class RegistrationUI:
    """
    Delegated UI handler for the Registration tab.

    ARCHITECTURE MANDATES (UI Components):
    1. REACTIVE REFRESH ONLY: Never call 'refresh_reg_ui' imperatively from
       within this class. Always set 'self.controller.ui_needs_refresh = True'
       and let the MainGUI tick loop handle the rebuild.

    2. STATE-DRIVEN BUILDING: Sliders and input fields must pull their
       'default_value' from the underlying 'SpatialEngine' transform during
       the refresh cycle.

    3. ONE-WAY DATA FLOW: Callbacks should exclusively update the transform
       parameters in the 'Controller'. Do not manually set values of other
       widgets within a callback.

    4. THREAD SAFETY: Registration resampling often happens in background
       threads. Ensure those threads NEVER call UI functions. Use
       'controller.status_message' for asynchronous reporting.
    """

    # Define slider tags once to avoid copy-pasting lists of strings
    SLIDER_TAGS = [
        "drag_reg_rx",
        "drag_reg_ry",
        "drag_reg_rz",
        "drag_reg_tx",
        "drag_reg_ty",
        "drag_reg_tz",
    ]

    _AUTO_RESAMPLE_DELAY = 0.7  # seconds of inactivity before auto-resample fires

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller
        self._preview_version = 0
        self._preview_lock = threading.Lock()
        self._preview_queue = queue.Queue()
        threading.Thread(target=self._preview_worker_loop, daemon=True).start()
        self._auto_timer: "threading.Timer | None" = None
        self._auto_timer_lock = threading.Lock()
        self._auto_timer_vs_id: str | None = None

    def _preview_worker_loop(self):
        while True:
            req = self._preview_queue.get()
            if req is None:
                break
            # Drain: skip all but the latest queued request
            while not self._preview_queue.empty():
                try:
                    req = self._preview_queue.get_nowait()
                except queue.Empty:
                    break
            vs_id, version, R, center, viewer_slices = req
            self._trigger_fast_preview(vs_id, version, R, center, viewer_slices)

    @staticmethod
    def build_tab_reg(gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.group(tag="tab_reg", show=False):

            build_section_title("Registration", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag="text_reg_active_title",
                color=cfg_c["text_active"],
            )

            dpg.add_text(
                "Registration disabled: DVF active",
                tag="text_reg_dvf_warning",
                color=cfg_c.get("outdated", [255, 200, 50]),
                show=False,
            )


            with dpg.group(tag="group_registration_controls"):
                # --- TOP: File Management ---
                dpg.add_spacer(height=10)
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Load Matrix",
                        tag="btn_reg_load",
                        callback=gui.reg_ui.on_reg_load_clicked,
                    )
                    dpg.add_button(
                        label="Save Matrix",
                        tag="btn_reg_save",
                        callback=gui.reg_ui.on_reg_save_clicked,
                    )
                    dpg.add_button(
                        label="Save As",
                        tag="btn_reg_save_as",
                        callback=gui.reg_ui.on_reg_save_as_clicked,
                    )

                    btn_reload = dpg.add_button(
                        label="\uf01e",
                        width=20,
                        tag="btn_reg_reload",
                        callback=gui.reg_ui.on_reg_reload_clicked,
                    )
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_reload, "icon_font_tag")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_reload, "icon_button_theme")

                with dpg.group(horizontal=True):
                    dpg.add_text("Transform File: ")
                    dpg.add_text("None", tag="text_reg_filename", color=cfg_c["text_dim"])

                # --- CoR Goto and Set ---
                dpg.add_spacer(height=10)
                with dpg.group(horizontal=True):
                    dpg.add_text("CoR:")
                    dpg.add_input_text(tag="input_reg_cor", width=-1, readonly=True)
                with dpg.group(horizontal=True):
                    b = dpg.add_button(
                        label="\uf05b ", callback=gui.reg_ui.on_reg_center_cor_clicked
                    )
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(b, "icon_font_tag")
                    dpg.add_button(
                        label="Snap to Crosshair", width=-1, callback=gui.reg_ui.on_reg_cor_to_crosshair_clicked
                    )

                # --- Rigid Adjustment ---
                dpg.add_spacer(height=10)
                build_section_title(
                    "Rigid Adjustment (Euler R = Rz Ry Rx)", cfg_c["text_header"]
                )
                with dpg.group(horizontal=True):
                    dpg.add_text("Step:")
                    dpg.add_radio_button(
                        items=["Coarse", "Fine"],
                        default_value="Coarse",
                        horizontal=True,
                        tag="radio_reg_step",
                        callback=gui.reg_ui.on_reg_step_changed,
                    )

                dpg.add_spacer(height=5)

                # Translation Drag Floats
                build_stepped_slider(
                    "Tx ",
                    "drag_reg_tx",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-5000.0,
                    max_val=5000.0,
                    format="%.2f mm",
                )
                build_stepped_slider(
                    "Ty ",
                    "drag_reg_ty",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-5000.0,
                    max_val=5000.0,
                    format="%.2f mm",
                )
                build_stepped_slider(
                    "Tz ",
                    "drag_reg_tz",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-5000.0,
                    max_val=5000.0,
                    format="%.2f mm",
                )

                dpg.add_spacer(height=5)

                # Rotation Drag Floats (Euler)
                build_stepped_slider(
                    "Rx ",
                    "drag_reg_rx",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-360.0,
                    max_val=360.0,
                    format="%.2f \u00b0",
                )
                build_stepped_slider(
                    "Ry ",
                    "drag_reg_ry",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-360.0,
                    max_val=360.0,
                    format="%.2f \u00b0",
                )
                build_stepped_slider(
                    "Rz ",
                    "drag_reg_rz",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-360.0,
                    max_val=360.0,
                    format="%.2f \u00b0",
                )

                dpg.add_spacer(height=5)
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Reset to Identity",
                        callback=gui.reg_ui.on_reg_reset_clicked,
                    )
                    dpg.add_button(
                        label="Invert Transform", width=-1, callback=gui.reg_ui.on_reg_invert_clicked
                    )
                dpg.add_spacer(height=5)
                
                # --- Resample & Bake ---
                dpg.add_checkbox(
                    label="Auto-Update Display",
                    tag="check_reg_auto_resample",
                    default_value=False,
                    callback=gui.reg_ui.on_reg_auto_resample_toggled,
                )
                dpg.add_button(
                    label="Update Display", width=-1, tag="btn_reg_resample", callback=gui.reg_ui.on_reg_resample_clicked
                )
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Commit to Volume",
                        tag="btn_reg_bake",
                        callback=gui.reg_ui.on_reg_bake_clicked,
                        width=-28,
                    )
                    btn_help_bake = dpg.add_button(label="\uf059", width=20)
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_help_bake, "icon_font_tag")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_help_bake, "icon_button_theme")
                    with dpg.tooltip(btn_help_bake):
                        dpg.add_text(
                            "Permanently applies the active spatial transform to the\n"
                            "underlying 3D pixel grid and resets the sliders to zero.\n"
                            "You can then 'Save' the resulting aligned image to disk.",
                            color=cfg_c.get("text_dim", [150, 150, 150])
                        )

                # --- Affine Matrix ---
                dpg.add_spacer(height=10)
                dpg.add_separator()
                dpg.add_spacer(height=10)
                build_section_title("Affine Matrix", cfg_c["text_header"])
                with dpg.group(tag="group_reg_matrix"):
                    with dpg.table(
                        header_row=False, borders_innerV=True, borders_innerH=True, resizable=False,
                    ):
                        for _ in range(4): dpg.add_table_column()
                        for r in range(4):
                            with dpg.table_row():
                                for c in range(4):
                                    dpg.add_text("0.000", tag=f"txt_reg_m_{r}_{c}", color=cfg_c["text_dim"])

    def pull_reg_sliders_from_transform(self):
        """ONLY call this when loading a file, switching images, or resetting. NOT during drag!"""
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        vs = viewer.view_state
        if vs and vs.space.transform:
            params = vs.space.get_parameters()
            vals = [
                math.degrees(params[0]),
                math.degrees(params[1]),
                math.degrees(params[2]),
                params[3],
                params[4],
                params[5],
            ]

            for tag, val in zip(self.SLIDER_TAGS, vals):
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, val)
        else:
            for tag in self.SLIDER_TAGS:
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, 0.0)

    def refresh_reg_ui(self):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        vol = self.controller.volumes.get(viewer.image_id)

        is_dvf = getattr(vol, "is_dvf", False) if vol else False
        if dpg.does_item_exist("text_reg_dvf_warning"):
            dpg.configure_item("text_reg_dvf_warning", show=is_dvf)
        if dpg.does_item_exist("group_registration_controls"):
            dpg.configure_item("group_registration_controls", show=not is_dvf)

        if dpg.does_item_exist("text_reg_active_title") and vol:
            name_str, is_outdated = self.controller.get_image_display_name(
                viewer.image_id
            )
            dpg.set_value("text_reg_active_title", name_str)

            # Apply orange if modified, default active color if not
            col = (
                self.gui.ui_cfg["colors"]["outdated"]
                if is_outdated
                else self.gui.ui_cfg["colors"]["text_active"]
            )
            dpg.configure_item("text_reg_active_title", color=col)

        if is_dvf:
            return

        if dpg.does_item_exist("btn_reg_resample"):
            theme = "orange_button_theme" if vs.needs_resample else 0
            dpg.bind_item_theme("btn_reg_resample", theme)

        if dpg.does_item_exist("text_reg_filename"):
            dpg.set_value("text_reg_filename", vs.space.transform_file)

        if vol:
            is_2d = min(vol.shape3d) == 1
            out_of_plane_tags = ["drag_reg_rx", "drag_reg_ry", "drag_reg_tz"]
            for tag in out_of_plane_tags:
                if dpg.does_item_exist(tag):
                    dpg.configure_item(tag, enabled=not is_2d)
                if dpg.does_item_exist(f"btn_{tag}_minus"):
                    dpg.configure_item(f"btn_{tag}_minus", enabled=not is_2d)
                if dpg.does_item_exist(f"btn_{tag}_plus"):
                    dpg.configure_item(f"btn_{tag}_plus", enabled=not is_2d)

        if vs.space.transform:
            matrix = np.array(vs.space.transform.GetMatrix()).reshape(3, 3)
            center = vs.space.transform.GetCenter()
            params = vs.space.get_parameters()

            for r in range(3):
                for c in range(3):
                    if dpg.does_item_exist(f"txt_reg_m_{r}_{c}"):
                        dpg.set_value(f"txt_reg_m_{r}_{c}", f"{matrix[r, c]:.4f}")
                if dpg.does_item_exist(f"txt_reg_m_{r}_3"):
                    dpg.set_value(f"txt_reg_m_{r}_3", f"{params[r+3]:.2f}")

            for c, val in enumerate(["0.000", "0.000", "0.000", "1.000"]):
                if dpg.does_item_exist(f"txt_reg_m_3_{c}"):
                    dpg.set_value(f"txt_reg_m_3_{c}", val)

            if dpg.does_item_exist("input_reg_cor"):
                dpg.set_value(
                    "input_reg_cor",
                    f"{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}",
                )
        else:
            for r in range(4):
                for c in range(4):
                    if dpg.does_item_exist(f"txt_reg_m_{r}_{c}"):
                        dpg.set_value(
                            f"txt_reg_m_{r}_{c}", "1.000" if r == c else "0.000"
                        )
            if vol and dpg.does_item_exist("input_reg_cor"):
                center = self.controller.get_volume_physical_center(vol)
                dpg.set_value(
                    "input_reg_cor",
                    f"{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}",
                )

    def _is_live_preview_enabled(self):
        return True

    def _is_auto_resample_enabled(self):
        return dpg.does_item_exist("check_reg_auto_resample") and dpg.get_value("check_reg_auto_resample")

    def on_reg_auto_resample_toggled(self, _sender, app_data, _user_data):
        if not app_data:
            self._cancel_auto_timer()
            return
        # Just enabled — fire immediately if a resample is already pending
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs = self.controller.view_states.get(viewer.image_id)
        if vs and vs.needs_resample:
            self.trigger_resample(viewer.image_id)

    def _cancel_auto_timer(self):
        with self._auto_timer_lock:
            if self._auto_timer is not None:
                self._auto_timer.cancel()
                self._auto_timer = None

    def _schedule_auto_resample(self, vs_id):
        """Debounce: cancel any pending auto-resample and restart the countdown."""
        with self._auto_timer_lock:
            if self._auto_timer is not None:
                self._auto_timer.cancel()
            self._auto_timer_vs_id = vs_id
            t = threading.Timer(self._AUTO_RESAMPLE_DELAY, self._fire_auto_resample)
            t.daemon = True
            self._auto_timer = t
        t.start()

    def _fire_auto_resample(self):
        with self._auto_timer_lock:
            self._auto_timer = None
            vs_id = self._auto_timer_vs_id
        if vs_id:
            self.trigger_resample(vs_id)

    def _trigger_fast_preview(self, image_id, version, R, center, viewer_slices):
        """Background worker: compute per-slice 2D previews using pre-extracted numpy data.

        R, center, and viewer_slices are all captured on the main thread before this is
        called — this function never touches SimpleITK objects and is safe off-thread.
        viewer_slices: dict mapping id(viewer) → (orientation, slice_idx).

        Builds results locally, then atomically replaces _preview_slices only if no
        newer request has arrived (version check). This prevents two bugs:
        - The old preview disappearing mid-compute (causes a jump to unrotated view)
        - A slow earlier request overwriting the result of a faster later one
        """
        vs = self.controller.view_states.get(image_id)
        if not vs:
            return

        # Build previews locally — old previews stay visible during computation
        new_previews = {}
        new_overlay_previews = {}
        overlay_vol = vs.volume  # the moving image volume (B)

        for viewer in self.controller.viewers.values():
            ctx = viewer_slices.get(id(viewer))
            if ctx is None:
                continue
            kind, orientation, slice_idx = ctx

            if kind == "base":
                vol = viewer.volume
                if getattr(vol, "is_dvf", False):
                    continue
                preview = compute_preview_2d_affine(
                    vol, orientation, slice_idx, R, center, vs.camera.time_idx
                )
                if preview is not None:
                    new_previews[(orientation, slice_idx)] = preview

            elif kind == "overlay":
                base_vol = viewer.volume  # A's volume
                if base_vol is None or getattr(base_vol, "is_dvf", False):
                    continue
                t_idx = min(vs.camera.time_idx, overlay_vol.num_timepoints - 1)
                ov_preview = compute_overlay_preview_2d_affine(
                    base_vol, overlay_vol, orientation, slice_idx, R, center, t_idx
                )
                if ov_preview is not None:
                    new_overlay_previews[(orientation, slice_idx)] = ov_preview

        # Atomic: update shared rotation state on ViewState under the lock.
        # Viewer-local slice dicts are assigned after — dict replacement is GIL-atomic
        # and the worker is single-threaded (queue drain), so no concurrent writer exists.
        with self._preview_lock:
            if self._preview_version != version:
                return
            vs._preview_R = R
            vs._preview_center = center

        for viewer in self.controller.viewers.values():
            if viewer.image_id == image_id:
                viewer._preview_slices = new_previews
            elif viewer.view_state and viewer.view_state.display.overlay_id == image_id:
                viewer._overlay_preview_slices = new_overlay_previews

        self.controller.update_all_viewers_of_image(image_id)

    def trigger_resample(self, image_id):
        """Show a status message then delegate all resampling work to the Controller."""
        self.gui.show_status_message("Resampling display...", color=self.gui.ui_cfg["colors"]["working"])
        self.controller.resample_image(image_id)

    # --- Callbacks ---
    def on_reg_load_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        file_path = open_file_dialog(
            "Load Transform", multiple=False, extensions=[".tfm", ".txt", ".mat", ".xfm"]
        )
        if isinstance(file_path, str):
            vs = viewer.view_state
            # Capture the current world position of the crosshair BEFORE loading the new transform
            world_pos = vs.camera.crosshair_phys_coord

            if self.controller.load_transform(viewer.image_id, file_path):
                # Dynamically remember the exact file path for "Save"
                vs.space._full_transform_path = file_path
                self.gui.show_status_message(f"Loaded {os.path.basename(file_path)}")
                
                # Automatically enable the transform so the user sees it immediately
                vs.space.is_active = True

                if world_pos is not None:
                    vs.update_crosshair_from_phys(world_pos)

                self.controller.update_all_viewers_of_image(viewer.image_id)
                self.gui.update_sidebar_crosshair(viewer)
                self.pull_reg_sliders_from_transform()

                # Instantly trigger resample for loaded file
                self.trigger_resample(viewer.image_id)
                if dpg.does_item_exist("btn_reg_resample"):
                    dpg.bind_item_theme("btn_reg_resample", 0)
                self.controller.ui_needs_refresh = True
            else:
                self.gui.show_message("Error", "Failed to parse transform file.")

    def on_reg_save_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        if not vs.space.transform:
            self.gui.show_status_message(
                "No transform to save!", color=self.gui.ui_cfg["colors"]["warning"]
            )
            return

        # If we already have a loaded path, overwrite it seamlessly
        full_path = getattr(vs.space, "_full_transform_path", None)
        if full_path and os.path.exists(os.path.dirname(full_path)):
            self.controller.save_transform(viewer.image_id, full_path)
            self.gui.show_status_message(f"Saved: {os.path.basename(full_path)}")
            self.controller.ui_needs_refresh = True
        else:
            # Fallback to Save As
            self.on_reg_save_as_clicked(sender, app_data, user_data)

    def on_reg_save_as_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        if not vs.space.transform:
            self.gui.show_status_message(
                "No transform to save!", color=self.gui.ui_cfg["colors"]["warning"]
            )
            return

        default_name = (
            vs.space.transform_file
            if vs.space.transform_file != "None"
            else "matrix.tfm"
        )
        file_path = save_file_dialog("Save Transform As", default_name=default_name)
        if file_path:
            self.controller.save_transform(viewer.image_id, file_path)
            # Update the tracked path so future "Save" clicks overwrite this new file!
            vs.space._full_transform_path = file_path
            self.gui.show_status_message(f"Saved: {os.path.basename(file_path)}")
            self.controller.ui_needs_refresh = True

    def on_reg_reload_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        full_path = getattr(viewer.view_state.space, "_full_transform_path", None)
        if full_path and os.path.exists(full_path):
            if self.controller.load_transform(viewer.image_id, full_path):
                self.controller.ui_needs_refresh = True
                self.pull_reg_sliders_from_transform()
                if dpg.does_item_exist("btn_reg_resample"):
                    dpg.bind_item_theme("btn_reg_resample", 0)
                self.trigger_resample(viewer.image_id)
                self.gui.show_status_message(f"Reloaded: {os.path.basename(full_path)}")
        else:
            self.on_reg_load_clicked(sender, app_data, user_data)

    def on_reg_step_button_clicked(self, sender, app_data, user_data):
        """Handles the + and - buttons next to the manual registration sliders."""
        target_tag = user_data["tag"]
        direction = user_data["dir"]

        # Respect the Coarse (1.0) or Fine (0.1) radio button selection
        step_str = dpg.get_value("radio_reg_step")
        step_size = 1.0 if step_str == "Coarse" else 0.1
        current_val = dpg.get_value(target_tag)
        dpg.set_value(target_tag, current_val + (step_size * direction))

        # Immediately trigger the transform update
        self.on_reg_manual_changed(sender, app_data, user_data)

    def on_reg_bake_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs = viewer.view_state
        if not vs or not vs.space.transform or not vs.space.is_active:
            self.gui.show_status_message(
                "No active transform to bake.", color=self.gui.ui_cfg["colors"]["warning"]
            )
            return
        self.gui.show_status_message(
            "Baking transform...", color=self.gui.ui_cfg["colors"]["working"]
        )
        self.controller.bake_transform_to_volume(viewer.image_id)
        self.pull_reg_sliders_from_transform()
        self.controller.ui_needs_refresh = True


    def on_reg_step_changed(self, sender, app_data, user_data):
        speed = 1.0 if app_data == "Coarse" else 0.1
        for tag in self.SLIDER_TAGS:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, speed=speed)
                
    def on_reg_resample_clicked(self, sender, app_data, user_data):
        self._cancel_auto_timer()
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id

        if dpg.does_item_exist("btn_reg_resample"):
            dpg.bind_item_theme("btn_reg_resample", 0)
            
        self.trigger_resample(vs_id)

    def on_reg_manual_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id
        
        vs = self.controller.view_states.get(vs_id)
        if vs:
            vs.space.is_active = True
            
        vals = [dpg.get_value(t) for t in self.SLIDER_TAGS]
        self.controller.update_transform_manual(
            vs_id, vals[3], vals[4], vals[5], vals[0], vals[1], vals[2]
        )
        if dpg.does_item_exist("btn_reg_resample"):
            dpg.bind_item_theme("btn_reg_resample", "orange_button_theme")
        if vs:
            vs.needs_resample = True

        has_rotation = vs is not None and vs.space.has_rotation()

        with self._preview_lock:
            self._preview_version += 1
            version = self._preview_version

        if vs:
            if has_rotation:
                # Keep vs._preview_R alive: the on-demand path in _package_base_layer
                # uses it to render a "ghost" preview at the previous rotation angle
                # while the new worker result is computing, preventing a flicker frame
                # that would show base_display_data (old full-resample data) instead.
                # Clear viewer slice caches so stale entries don't survive into the
                # new rotation angle — they'll be repopulated on-demand via _preview_R.
                for v in self.controller.viewers.values():
                    if v.image_id == vs_id:
                        v._preview_slices.clear()
                    elif v.view_state and v.view_state.display.overlay_id == vs_id:
                        v._overlay_preview_slices.clear()
            else:
                # Translation-only: disable the on-demand preview path entirely so
                # stale rotation previews from a prior session are never rendered.
                vs.reset_preview_rotation()

        preview_thread_spawned = False
        if self._is_live_preview_enabled() and has_rotation:
            # Extract ITK transform data as numpy on the main thread — ITK objects
            # must never be read/written from background threads (not thread-safe).
            rot_transform = vs.space.get_rotation_only_transform()
            R = np.array(rot_transform.GetMatrix(), dtype=np.float64).reshape(3, 3)
            center = np.array(rot_transform.GetCenter(), dtype=np.float64)
            # Also snapshot viewer slice indices on the main thread: viewer.slice_idx
            # calls world_to_display → SpatialEngine → transform.GetInverse() — ITK,
            # so it must not be called from the worker thread.
            viewer_slices = {}
            for v in self.controller.viewers.values():
                if v.image_id == vs_id:
                    viewer_slices[id(v)] = ("base", v.orientation, v.slice_idx)
                elif v.view_state and v.view_state.display.overlay_id == vs_id:
                    # Fusion viewer: capture slice_idx on main thread (ITK-safe here)
                    viewer_slices[id(v)] = ("overlay", v.orientation, v.slice_idx)
            self._preview_queue.put((vs_id, version, R, center, viewer_slices))
            preview_thread_spawned = True

        if not preview_thread_spawned:
            # Translation-only (or preview disabled): mark viewers dirty immediately so
            # the render loop re-extracts the slice at the new slice_idx.
            # For rotation with live preview, the background thread calls
            # update_all_viewers_of_image when the preview is ready — calling it here
            # too would cause a flicker frame showing raw/old data before the preview arrives.
            self.controller.update_all_viewers_of_image(vs_id)

        if self._is_auto_resample_enabled() and vs and vs.needs_resample:
            self._schedule_auto_resample(vs_id)

        self.controller.ui_needs_refresh = True

    def on_reg_reset_clicked(self, sender, app_data, user_data):
        self._cancel_auto_timer()
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        for tag in self.SLIDER_TAGS:
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, 0.0)
        self.controller.update_transform_manual(viewer.image_id, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        # Invalidate any in-flight preview and clear state immediately on the main thread
        # so the viewer doesn't briefly show a stale rotation preview after reset.
        with self._preview_lock:
            self._preview_version += 1
        vs = self.controller.view_states.get(viewer.image_id)
        if vs:
            vs.reset_preview_rotation()
        # Immediately resample: for identity, update_base_display_data just clears the
        # stale rotated buffer (no ITK resampling), so this returns almost instantly.
        if dpg.does_item_exist("btn_reg_resample"):
            dpg.bind_item_theme("btn_reg_resample", 0)
        self.trigger_resample(viewer.image_id)
        self.controller.ui_needs_refresh = True

    def on_reg_invert_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs = viewer.view_state
        if not vs.space.transform:
            return
        params = vs.space.transform.GetInverse().GetParameters()
        vals = [
            math.degrees(params[0]),
            math.degrees(params[1]),
            math.degrees(params[2]),
            params[3],
            params[4],
            params[5],
        ]
        for tag, val in zip(self.SLIDER_TAGS, vals):
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, val)
        # Delegate to on_reg_manual_changed so preview, dirty flags, and button theme
        # are all handled identically to a slider drag (same pattern as step buttons).
        self.on_reg_manual_changed(sender, app_data, user_data)

    def on_reg_center_cor_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs = viewer.view_state
        vol = self.controller.volumes.get(viewer.image_id)
        center = (
            vs.space.transform.GetCenter()
            if vs.space.transform
            else self.controller.get_volume_physical_center(vol)
        )
        if center is not None:
            vs.update_crosshair_from_phys(center)
        # State-Only Camera Snapping
        target_ids = self.controller.sync.get_sync_group_vs_ids(
            viewer.image_id, active_only=True
        )
        for tid in target_ids:
            self.controller.view_states[tid].camera.target_center = center

        self.controller.update_all_viewers_of_image(viewer.image_id)
        self.controller.sync.propagate_sync(viewer.image_id)
        self.controller.ui_needs_refresh = True

    def on_reg_cor_to_crosshair_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        vs = viewer.view_state
        if not vs.space.transform:
            import SimpleITK as sitk

            vs.space.transform = sitk.Euler3DTransform()

        new_center = vs.camera.crosshair_phys_coord
        if new_center is None:
            return

        new_center_tuple = (
            float(new_center[0]),
            float(new_center[1]),
            float(new_center[2]),
        )

        mapped_center = vs.space.transform.TransformPoint(new_center_tuple)
        new_translation = (
            mapped_center[0] - new_center_tuple[0],
            mapped_center[1] - new_center_tuple[1],
            mapped_center[2] - new_center_tuple[2],
        )

        vs.space.transform.SetCenter(new_center_tuple)
        vs.space.transform.SetTranslation(new_translation)
        vs.space.is_active = True

        self.pull_reg_sliders_from_transform()
        if dpg.does_item_exist("btn_reg_resample"):
            dpg.bind_item_theme("btn_reg_resample", "orange_button_theme")
        vs = viewer.view_state
        if vs:
            vs.needs_resample = True
        self.controller.ui_needs_refresh = True

        self.gui.show_status_message("CoR snapped to Crosshair")
