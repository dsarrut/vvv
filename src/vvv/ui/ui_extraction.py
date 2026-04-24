import numpy as np
import threading
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_stepped_slider
from vvv.utils import ViewMode
from vvv.math.contours import ContourROI, extract_2d_contours_from_slice
from vvv.math.image import SliceRenderer


class ExtractionUI:
    """Handles the Interactive Thresholding and Extraction workflow."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller
        # Dictionary mapping image_id to a single ContourROI object
        self._preview_rois = {}

    def build_tab_extraction(self, gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.tab(label="Extract", tag="tab_extraction"):
            dpg.add_spacer(height=5)
            build_section_title("Interactive Threshold", cfg_c["text_header"])

            # -- Single Threshold Slider --
            build_stepped_slider(
                "Threshold:",
                "drag_ext_threshold",
                callback=self.on_threshold_drag,
                step_callback=self.on_step_button_clicked,
                min_val=-100000.0,
                max_val=100000.0,
            )

            dpg.add_spacer(height=5)

            # -- Live Preview Controls --
            with dpg.group(horizontal=True):
                dpg.add_checkbox(
                    label="Live Preview",
                    tag="check_ext_preview",
                    default_value=False,
                    callback=self.on_threshold_drag,
                )

                dpg.add_color_edit(
                    (255, 255, 0, 255),  # Default Yellow
                    tag="color_ext_preview",
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=20,
                    height=20,
                    callback=self.on_threshold_drag,
                )

            dpg.add_spacer(height=15)
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # -- Action --
            dpg.add_button(
                label="Extract to ROI",
                tag="btn_ext_extract",
                width=-1,
                height=30,
                callback=self.on_extract_clicked,
            )

            # -- Progress --
            dpg.add_spacer(height=5)
            dpg.add_progress_bar(
                tag="prog_ext", default_value=0.0, width=-1, show=False
            )
            dpg.add_text("", tag="text_prog_ext", color=cfg_c["text_dim"], show=False)

    def refresh_extraction_ui(self):
        viewer = self.gui.context_viewer
        has_image = (
            viewer is not None
            and getattr(viewer, "view_state", None) is not None
            and viewer.volume is not None
        )

        tags_to_toggle = [
            "drag_ext_threshold",
            "btn_ext_extract",
            "btn_drag_ext_threshold_minus",
            "btn_drag_ext_threshold_plus",
        ]

        for tag in tags_to_toggle:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=has_image)

        if has_image:
            vol = viewer.volume

            # Lazy min/max computation
            current_data_id = id(vol.data)
            if (
                not hasattr(vol, "_cached_min_val")
                or getattr(vol, "_cached_data_id", None) != current_data_id
            ):
                vol._cached_min_val = float(np.min(vol.data))
                vol._cached_max_val = float(np.max(vol.data))
                vol._cached_data_id = current_data_id

            min_v = vol._cached_min_val
            max_v = vol._cached_max_val

            dpg.configure_item("drag_ext_threshold", min_value=min_v, max_value=max_v)

            speed = max(0.1, viewer.view_state.display.ww * 0.005)
            dpg.configure_item("drag_ext_threshold", speed=speed)

            # Initialize slider to the minimum value so it doesn't default to 0 for weird image types
            if dpg.get_value("drag_ext_threshold") == 0.0:
                dpg.set_value("drag_ext_threshold", min_v)

    def on_step_button_clicked(self, sender, app_data, user_data):
        target_tag = user_data["tag"]
        direction = user_data["dir"]
        current_val = dpg.get_value(target_tag)

        viewer = self.gui.context_viewer
        step_size = (
            max(0.1, viewer.view_state.display.ww * 0.02)
            if (viewer and viewer.view_state)
            else 1.0
        )

        new_val = current_val + (step_size * direction)

        if viewer and hasattr(viewer.volume, "_cached_min_val"):
            new_val = np.clip(
                new_val, viewer.volume._cached_min_val, viewer.volume._cached_max_val
            )

        dpg.set_value(target_tag, new_val)
        self.on_threshold_drag(sender, new_val, user_data)

    def _get_or_create_preview_roi(self, image_id, vs):
        if image_id not in self._preview_rois:
            color = [int(c) for c in dpg.get_value("color_ext_preview")[:3]]
            roi = ContourROI(name="Live Preview", color=color, thickness=2.0)
            self._preview_rois[image_id] = roi
            vs.contour_rois.append(roi)
        else:
            color = [int(c) for c in dpg.get_value("color_ext_preview")[:3]]
            self._preview_rois[image_id].color = color

        return self._preview_rois[image_id]

    def on_threshold_drag(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.volume:
            return

        vs = viewer.view_state
        vol = viewer.volume
        img_id = viewer.image_id

        roi = self._get_or_create_preview_roi(img_id, vs)

        # 1. ALWAYS clear previous polygons entirely
        for ori in roi.polygons:
            roi.polygons[ori].clear()

        # 2. Force ALL viewers of this image to redraw to clear old geometry
        for v in self.controller.viewers.values():
            if v.image_id == img_id:
                v.is_geometry_dirty = True

        if not dpg.get_value("check_ext_preview"):
            self.controller.ui_needs_refresh = True
            return

        threshold_val = dpg.get_value("drag_ext_threshold")

        visible_targets = []
        for v in self.controller.viewers.values():
            if v.image_id == img_id and v.is_image_orientation():
                visible_targets.append((v, v.orientation, v.slice_idx))

        for v, ori, s_idx in visible_targets:
            sw, sh = vol.get_physical_aspect_ratio(ori)
            slice_data = SliceRenderer.get_raw_slice(vol.data, False, 0, s_idx, ori)

            mask_2d = (slice_data >= threshold_val).astype(np.uint8)
            if np.any(mask_2d):
                polys = extract_2d_contours_from_slice(mask_2d, sw, sh)
                roi.polygons[ori][s_idx] = polys

        self.controller.ui_needs_refresh = True

    def on_extract_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.volume:
            return

        vs = viewer.view_state
        vol = viewer.volume
        threshold_val = dpg.get_value("drag_ext_threshold")

        # Hide live preview instances before starting heavy math
        if viewer.image_id in self._preview_rois:
            roi = self._preview_rois[viewer.image_id]
            roi.polygons = {
                ViewMode.AXIAL: {},
                ViewMode.SAGITTAL: {},
                ViewMode.CORONAL: {},
            }
            for v in self.controller.viewers.values():
                if v.image_id == viewer.image_id:
                    v.is_geometry_dirty = True

        dpg.configure_item("prog_ext", show=True, default_value=0.0)
        dpg.configure_item(
            "text_prog_ext", show=True, default_value="Binarizing 3D Volume..."
        )

        def _background_extract():
            mask_3d = (vol.data >= threshold_val).astype(np.uint8)
            name_str = f"Iso [>= {threshold_val:g}]"

            if not np.any(mask_3d):
                self.controller.status_message = (
                    "Extraction Failed: Threshold resulted in empty mask."
                )
                self.controller.ui_needs_refresh = True
                dpg.configure_item("prog_ext", show=False)
                dpg.configure_item("text_prog_ext", show=False)
                return

            color = [int(c) for c in dpg.get_value("color_ext_preview")[:3]]
            baked_roi = ContourROI(name=name_str, color=color)

            for ori in [ViewMode.AXIAL, ViewMode.CORONAL, ViewMode.SAGITTAL]:
                baked_roi.polygons[ori] = {}

            shape = vol.shape3d
            ori_map = {
                ViewMode.AXIAL: shape[0],
                ViewMode.CORONAL: shape[1],
                ViewMode.SAGITTAL: shape[2],
            }
            total_slices = sum(ori_map.values())
            slices_processed = 0

            for ori, max_slices in ori_map.items():
                sw, sh = vol.get_physical_aspect_ratio(ori)

                for s_idx in range(max_slices):
                    slice_mask = SliceRenderer.get_raw_slice(
                        mask_3d, False, 0, s_idx, ori
                    )

                    if np.any(slice_mask):
                        polys = extract_2d_contours_from_slice(slice_mask, sw, sh)
                        baked_roi.polygons[ori][s_idx] = polys

                    slices_processed += 1

                    if slices_processed % 10 == 0:
                        dpg.set_value("prog_ext", slices_processed / total_slices)
                        dpg.set_value(
                            "text_prog_ext",
                            f"Extracting: {slices_processed} / {total_slices}",
                        )
                        for v in self.controller.viewers.values():
                            if v.image_id == viewer.image_id:
                                v.is_geometry_dirty = True

            vs.contour_rois.append(baked_roi)

            for v in self.controller.viewers.values():
                if v.image_id == viewer.image_id:
                    v.is_geometry_dirty = True

            dpg.configure_item("prog_ext", show=False)
            dpg.configure_item("text_prog_ext", show=False)
            self.controller.status_message = f"Extracted Contour ROI: {baked_roi.name}"
            self.controller.ui_needs_refresh = True

        threading.Thread(target=_background_extract, daemon=True).start()
