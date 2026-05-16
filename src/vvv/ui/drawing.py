import numpy as np
from vvv.config import COLORMAPS
import dearpygui.dearpygui as dpg
from vvv.utils import voxel_to_slice, ViewMode, ProfileInteractionMode


class OverlayDrawer:
    """
    Handles all DearPyGui drawing node updates for the SliceViewer.
    Extracting this logic keeps the viewer class streamlined and focused on state management.
    """

    def __init__(self, viewer):
        self.viewer = viewer

    def draw_voxel_grid(self, h, w):
        viewer = self.viewer
        node_a, node_b = viewer.grid_a_tag, viewer.grid_b_tag
        back_node = node_b if viewer.active_grid_node == node_a else node_a

        if dpg.does_item_exist(back_node):
            dpg.delete_item(back_node, children_only=True)
        else:
            return

        pmin, pmax = viewer.current_pmin, viewer.current_pmax
        if h == 0 or w == 0:
            return

        vox_w, vox_h = (pmax[0] - pmin[0]) / w, (pmax[1] - pmin[1]) / h
        if vox_w <= 0 or vox_h <= 0:
            return

        win_w, win_h = viewer.quad_w, viewer.quad_h
        if not win_w or not win_h:
            return

        color = viewer.controller.settings.data["colors"]["grid"]

        # Only draw lines that are actually on screen
        start_x = max(0, int(-pmin[0] / vox_w))
        end_x = min(w, int((win_w - pmin[0]) / vox_w) + 1)
        start_y = max(0, int(-pmin[1] / vox_h))
        end_y = min(h, int((win_h - pmin[1]) / vox_h) + 1)

        for x in range(start_x, end_x + 1):
            lx = pmin[0] + x * vox_w
            dpg.draw_line(
                [lx, max(0, pmin[1])],
                [lx, min(win_h, pmax[1])],
                color=color,
                parent=back_node,
            )

        for y in range(start_y, end_y + 1):
            ly = pmin[1] + y * vox_h
            dpg.draw_line(
                [max(0, pmin[0]), ly],
                [min(win_w, pmax[0]), ly],
                color=color,
                parent=back_node,
            )

        dpg.configure_item(back_node, show=True)
        if dpg.does_item_exist(viewer.active_grid_node):
            dpg.configure_item(viewer.active_grid_node, show=False)
        viewer.active_grid_node = back_node

    def draw_crosshair(self):
        viewer = self.viewer
        if (
            not viewer.is_image_orientation()
            or not viewer.view_state
            or not viewer.volume
        ):
            return

        node_tag = viewer.crosshair_tag

        if (
            not viewer.view_state.camera.show_crosshair
            or viewer.view_state.camera.crosshair_voxel is None
        ):
            if dpg.does_item_exist(viewer.xh_line_h):
                dpg.configure_item(viewer.xh_line_h, show=False)
                dpg.configure_item(viewer.xh_line_v, show=False)
            return

        display_vox = viewer._get_crosshair_display_voxel()
        if display_vox is None:
            return

        vx, vy, vz = display_vox[:3]
        shape = viewer.get_slice_shape()  # This is now the display slice shape

        # Failsafe against zero-division from corrupted or 0-dimension images
        real_h, real_w = max(1, shape[0]), max(1, shape[1])

        tx, ty = voxel_to_slice(vx, vy, vz, viewer.orientation, shape)
        pmin, pmax = viewer.current_pmin, viewer.current_pmax

        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]
        screen_x = (tx / real_w) * disp_w + pmin[0]
        screen_y = (ty / real_h) * disp_h + pmin[1]

        color = viewer.controller.settings.data["colors"]["crosshair"]

        # Check both initialization state AND physical existence in case the UI context was wiped
        if not viewer.xh_initialized or not dpg.does_item_exist(viewer.xh_line_v):
            if dpg.does_item_exist(viewer.xh_line_v):
                dpg.delete_item(viewer.xh_line_v)
            if dpg.does_item_exist(viewer.xh_line_h):
                dpg.delete_item(viewer.xh_line_h)

            dpg.draw_line(
                [screen_x, pmin[1]],
                [screen_x, pmin[1] + disp_h],
                color=color,
                parent=node_tag,
                tag=viewer.xh_line_v,
            )
            dpg.draw_line(
                [pmin[0], screen_y],
                [pmin[0] + disp_w, screen_y],
                color=color,
                parent=node_tag,
                tag=viewer.xh_line_h,
            )
            viewer.xh_initialized = True
        else:
            dpg.configure_item(
                viewer.xh_line_v,
                p1=[screen_x, pmin[1]],
                p2=[screen_x, pmin[1] + disp_h],
                color=color,
                show=True,
            )
            dpg.configure_item(
                viewer.xh_line_h,
                p1=[pmin[0], screen_y],
                p2=[pmin[0] + disp_w, screen_y],
                color=color,
                show=True,
            )

    def draw_voxels_as_strips(self, rgba_flat, h, w):
        viewer = self.viewer
        node_a, node_b = viewer.strips_a_tag, viewer.strips_b_tag
        back_node = node_b if viewer.active_strips_node == node_a else node_a

        if dpg.does_item_exist(back_node):
            dpg.delete_item(back_node, children_only=True)
        else:
            return

        pmin, pmax = viewer.current_pmin, viewer.current_pmax
        if h == 0 or w == 0:
            return

        vox_w, vox_h = (pmax[0] - pmin[0]) / w, (pmax[1] - pmin[1]) / h
        if vox_w <= 0 or vox_h <= 0:
            return

        win_w, win_h = viewer.quad_w, viewer.quad_h
        if not win_w or not win_h:
            return

        start_x, end_x = max(0, int(-pmin[0] / vox_w)), min(
            w, int((win_w - pmin[0]) / vox_w) + 1
        )
        start_y, end_y = max(0, int(-pmin[1] / vox_h)), min(
            h, int((win_h - pmin[1]) / vox_h) + 1
        )
        pixels = rgba_flat.reshape(h, w, 4)

        for y in range(start_y, end_y):
            y_pos = pmin[1] + (y * vox_h) + (vox_h / 2)
            for x in range(start_x, end_x):
                x1 = pmin[0] + (x * vox_w)
                color = [int(c * 255) for c in pixels[y, x]]
                dpg.draw_line(
                    [x1, y_pos],
                    [x1 + vox_w, y_pos],
                    color=color,
                    thickness=vox_h + 1,
                    parent=back_node,
                )

        dpg.configure_item(back_node, show=True)
        if dpg.does_item_exist(viewer.active_strips_node):
            dpg.configure_item(viewer.active_strips_node, show=False)
        viewer.active_strips_node = back_node

    def draw_orientation_axes(self):
        viewer = self.viewer
        if not viewer.is_image_orientation():
            if viewer.axes_nodes:
                dpg.configure_item(viewer.axes_nodes[0], show=False)
                dpg.configure_item(viewer.axes_nodes[1], show=False)
            self._last_axes_state = None
            return

        current_state = viewer.orientation
        if getattr(self, "_last_axes_state", None) == current_state:
            dpg.configure_item(viewer.axes_nodes[viewer.active_axes_idx], show=True)
            dpg.configure_item(
                viewer.axes_nodes[1 - viewer.active_axes_idx], show=False
            )
            return
        self._last_axes_state = current_state

        back_idx = 1 - viewer.active_axes_idx
        back_node = viewer.axes_nodes[back_idx]
        front_node = viewer.axes_nodes[viewer.active_axes_idx]

        if dpg.does_item_exist(back_node):
            dpg.delete_item(back_node, children_only=True)
        else:
            return

        labels, directions = viewer.get_axis_labels()
        axis_colors = viewer.controller.settings.data["colors"]

        origin = [12.0, 12.0]
        length = 30
        if directions[0] == -1:
            origin[0] = 50
        if directions[1] == -1:
            origin[1] = 50

        color_h = axis_colors[labels[0]]
        color_v = axis_colors[labels[1]]
        end_h = [origin[0] + (length * directions[0]), origin[1]]
        end_v = [origin[0], origin[1] + (length * directions[1])]

        dpg.draw_arrow(
            end_h, origin, color=color_h, thickness=2, size=4, parent=back_node
        )
        h_text_off = 5 if directions[0] > 0 else -18
        dpg.draw_text(
            [end_h[0] + h_text_off, end_h[1] - 7],
            labels[0],
            color=color_h,
            size=14,
            parent=back_node,
        )

        dpg.draw_arrow(
            end_v, origin, color=color_v, thickness=2, size=4, parent=back_node
        )
        v_text_off = 5 if directions[1] > 0 else -18
        dpg.draw_text(
            [end_v[0] - 5, end_v[1] + v_text_off],
            labels[1],
            color=color_v,
            size=14,
            parent=back_node,
        )

        dpg.configure_item(back_node, show=True)
        dpg.configure_item(front_node, show=False)
        viewer.active_axes_idx = back_idx

    def draw_histogram_view(self):
        viewer = self.viewer
        if not viewer.view_state:
            return

        # Guard against tombstone memory drops mid-frame
        if getattr(viewer.volume, "data", None) is None:
            return

        plot_tag = f"plot_{viewer.tag}"

        if not dpg.does_item_exist(plot_tag):
            with dpg.plot(
                label=f"Histogram: {viewer.volume.name}",
                parent=f"win_{viewer.tag}",
                tag=plot_tag,
                width=-1,
                height=-1,
            ):
                dpg.add_plot_axis(
                    dpg.mvXAxis, label="Voxel Value", tag=f"x_axis_{viewer.tag}"
                )
                dpg.add_plot_axis(
                    dpg.mvYAxis, label="Count", tag=f"y_axis_{viewer.tag}"
                )
                dpg.add_line_series(
                    [],
                    [],
                    label="Freq",
                    parent=f"y_axis_{viewer.tag}",
                    tag=f"series_{viewer.tag}",
                )
            viewer.view_state.histogram_is_dirty = True

        dpg.configure_item(plot_tag, show=True)

        if viewer.view_state.histogram_is_dirty:
            viewer.view_state.update_histogram()
        else:
            return

        y_data = (
            np.log10(viewer.view_state.hist_data_y + 1)
            if viewer.view_state.use_log_y
            else viewer.view_state.hist_data_y
        )
        dpg.set_value(
            f"series_{viewer.tag}",
            [viewer.view_state.hist_data_x.tolist(), y_data.tolist()],
        )
        dpg.fit_axis_data(f"x_axis_{viewer.tag}")
        dpg.fit_axis_data(f"y_axis_{viewer.tag}")

    def draw_scale_bar(self):
        viewer = self.viewer

        if (
            not viewer.is_image_orientation()
            or not viewer.view_state
            or not viewer.view_state.camera.show_scalebar
        ):
            if dpg.does_item_exist(viewer.scale_bar_tag):
                dpg.delete_item(viewer.scale_bar_tag, children_only=True)
            self._last_sb_state = None
            return

        win_w, win_h = viewer.quad_w, viewer.quad_h
        if not win_w or not win_h:
            return

        ppm = viewer.get_pixels_per_mm()
        if ppm <= 0:
            return

        current_state = (win_w, win_h, ppm)
        if getattr(self, "_last_sb_state", None) == current_state:
            return
        self._last_sb_state = current_state

        if dpg.does_item_exist(viewer.scale_bar_tag):
            dpg.delete_item(viewer.scale_bar_tag, children_only=True)
        else:
            return

        target_px = win_w * 0.15
        target_mm = target_px / ppm
        magnitude = 10 ** np.floor(np.log10(target_mm))
        normalized = target_mm / magnitude

        if normalized < 1.5:
            factor = 1
        elif normalized < 3.5:
            factor = 2
        elif normalized < 7.5:
            factor = 5
        else:
            factor = 10

        bar_mm = factor * magnitude
        bar_px = bar_mm * ppm

        x2 = int(win_w - 20)
        x1 = int(x2 - bar_px)
        y = int(win_h - 20)

        color = viewer.controller.settings.data["colors"]["tracker_text"]

        dpg.draw_rectangle(
            [x1, y - 1],
            [x2, y + 1],
            color=color,
            fill=color,
            parent=viewer.scale_bar_tag,
        )
        dpg.draw_rectangle(
            [x1 - 1, y - 5],
            [x1 + 1, y + 5],
            color=color,
            fill=color,
            parent=viewer.scale_bar_tag,
        )
        dpg.draw_rectangle(
            [x2 - 1, y - 5],
            [x2 + 1, y + 5],
            color=color,
            fill=color,
            parent=viewer.scale_bar_tag,
        )

        text = f"{bar_mm:g} mm"
        text_x = int(x1 + (bar_px / 2) - ((len(text) * 7) / 2))
        dpg.draw_text(
            [text_x, int(y - 20)],
            text,
            color=color,
            size=14,
            parent=viewer.scale_bar_tag,
        )

    def draw_legend(self):
        viewer = self.viewer

        if (
            not viewer.is_image_orientation()
            or not viewer.view_state
            or not viewer.show_legend
        ):
            if dpg.does_item_exist(viewer.legend_tag):
                dpg.delete_item(viewer.legend_tag, children_only=True)
            self._last_leg_state = None
            return

        if getattr(viewer.volume, "is_rgb", False):
            if dpg.does_item_exist(viewer.legend_tag):
                dpg.delete_item(viewer.legend_tag, children_only=True)
            self._last_leg_state = None
            return

        win_w = viewer.quad_w
        win_h = viewer.quad_h
        if not win_w or not win_h:
            return

        cb_width = 15
        cb_height = int(win_h * 0.4)
        if cb_height < 50:
            return

        ww, wl = viewer.view_state.display.ww, viewer.view_state.display.wl
        cmap = viewer.view_state.display.colormap
        cv = viewer.view_state.crosshair_value

        current_state = (win_h, ww, wl, cmap, cv)
        if getattr(self, "_last_leg_state", None) == current_state:
            return
        self._last_leg_state = current_state

        if dpg.does_item_exist(viewer.legend_tag):
            dpg.delete_item(viewer.legend_tag, children_only=True)
        else:
            return

        x_start = win_w - cb_width - 55
        y_start = (win_h - cb_height) // 2

        bg_col = viewer.controller.settings.data["colors"]["legend_bg"]
        dpg.draw_rectangle(
            [x_start - 15, y_start - 20],
            [win_w - 5, y_start + cb_height + 20],
            color=bg_col,
            fill=bg_col,
            parent=viewer.legend_tag,
        )

        cmap = COLORMAPS.get(viewer.view_state.display.colormap, COLORMAPS["Grayscale"])

        for i in range(256):
            y = y_start + cb_height - (i / 255.0) * cb_height
            color = [int(c * 255) for c in cmap[i]]
            dpg.draw_line(
                [x_start, y],
                [x_start + cb_width, y],
                color=color,
                thickness=2,
                parent=viewer.legend_tag,
            )

        border_col = [255, 255, 255, 120]
        dpg.draw_rectangle(
            [x_start, y_start],
            [x_start + cb_width, y_start + cb_height],
            color=border_col,
            parent=viewer.legend_tag,
        )

        ww, wl = viewer.view_state.display.ww, viewer.view_state.display.wl
        val_min = wl - ww / 2.0
        val_max = wl + ww / 2.0
        text_col = viewer.controller.settings.data["colors"]["tracker_text"]

        dpg.draw_text(
            [x_start + cb_width + 8, y_start - 7],
            f"{val_max:g}",
            color=text_col,
            size=14,
            parent=viewer.legend_tag,
        )
        dpg.draw_text(
            [x_start + cb_width + 8, y_start + cb_height / 2 - 7],
            f"{wl:g}",
            color=text_col,
            size=14,
            parent=viewer.legend_tag,
        )
        dpg.draw_text(
            [x_start + cb_width + 8, y_start + cb_height - 7],
            f"{val_min:g}",
            color=text_col,
            size=14,
            parent=viewer.legend_tag,
        )

        val_to_mark = viewer.view_state.crosshair_value
        if val_to_mark is not None and isinstance(val_to_mark, (int, float, np.number)):
            norm = (val_to_mark - val_min) / max(1e-5, ww)
            norm = np.clip(norm, 0.0, 1.0)
            y_pos = y_start + cb_height - (norm * cb_height)

            dpg.draw_line(
                [x_start - 6, y_pos],
                [x_start + cb_width + 6, y_pos],
                color=[255, 255, 255, 255],
                thickness=1,
                parent=viewer.legend_tag,
            )
            dpg.draw_triangle(
                [x_start - 5, y_pos],
                [x_start - 11, y_pos - 4],
                [x_start - 11, y_pos + 4],
                color=[255, 255, 255, 255],
                fill=[255, 255, 255, 255],
                parent=viewer.legend_tag,
            )

    def draw_contours(self):
        viewer = self.viewer

        if (
            not viewer.is_image_orientation()
            or not viewer.view_state
            or not viewer.volume
        ):
            if dpg.does_item_exist(viewer.contour_node_tag):
                dpg.configure_item(viewer.contour_node_tag, show=False)
            return

        if not getattr(viewer.view_state.camera, "show_contour", True):
            if dpg.does_item_exist(viewer.contour_node_tag):
                dpg.configure_item(viewer.contour_node_tag, show=False)
            return

        ext = getattr(viewer.view_state, "extraction", None)

        node = viewer.contour_node_tag
        if not dpg.does_item_exist(node):
            return

        contour_dict = getattr(viewer.view_state, "contours", {})
        contour_rois = list(contour_dict.values())

        # Include ROIs in contour mode
        for r_id, r_state in viewer.view_state.rois.items():
            if r_state.visible and getattr(r_state, "is_contour", False):
                contour_rois.append(r_state)

        # ROBUST CACHE INVALIDATION
        # We must track colors, thickness, and exact math states so DPG knows when to redraw!
        total_polys = 0
        roi_visual_states = []

        for roi in contour_rois:
            if getattr(roi, "visible", True):
                poly_list = roi.polygons[viewer.orientation].get(viewer.slice_idx, [])
                total_polys += len(poly_list)

                # Track visual properties to break the cache if they change
                roi_visual_states.append(
                    (id(roi), tuple(roi.color), getattr(roi, "thickness", 1.0))
                )

        # Also track the mathematical state of the preview
        ext_math_state = (
            (ext.threshold_min, ext.threshold_max, ext.subpixel_accurate)
            if ext
            else None
        )

        current_state = (
            viewer.image_id,
            viewer.orientation,
            viewer.slice_idx,
            len(contour_rois),
            total_polys,
            tuple(roi_visual_states),  # Triggers redraw if ANY color changes
            ext_math_state,  # Triggers redraw if Subpixel changes
        )

        if getattr(self, "_last_contour_image", None) != current_state:
            dpg.delete_item(node, children_only=True)

            for roi in contour_rois:
                if not roi.visible:
                    continue
                polys = roi.polygons[viewer.orientation].get(viewer.slice_idx, [])
                for poly in polys:
                    dpg.draw_polyline(
                        poly,
                        color=roi.color,
                        thickness=roi.thickness,
                        parent=node,
                    )
            self._last_contour_image = current_state

        sw, sh = viewer.volume.get_physical_aspect_ratio(viewer.orientation)
        shape = viewer.get_slice_shape()
        mm_w, mm_h = max(1e-5, shape[1] * sw), max(1e-5, shape[0] * sh)
        pmin, pmax = viewer.current_pmin, viewer.current_pmax

        scale_x = (pmax[0] - pmin[0]) / mm_w
        scale_y = (pmax[1] - pmin[1]) / mm_h

        scale_mat = dpg.create_scale_matrix([scale_x, scale_y, 1.0])
        trans_mat = dpg.create_translation_matrix([pmin[0], pmin[1], 0.0])
        dpg.apply_transform(node, trans_mat * scale_mat)

        dpg.configure_item(node, show=True)

    def draw_profiles(self):
        def get_screen_pos(v_disp):
            if v_disp is None:
                return None
            tx, ty = voxel_to_slice(
                v_disp[0], v_disp[1], v_disp[2], viewer.orientation, shape
            )
            sx = (tx / real_w) * disp_w + pmin[0]
            sy = (ty / real_h) * disp_h + pmin[1]
            return [sx, sy]

        viewer = self.viewer

        if (
            not viewer.is_image_orientation()
            or not viewer.view_state
            or not viewer.volume
            or not getattr(viewer.view_state.camera, "show_profiles", True)
        ):
            if dpg.does_item_exist(viewer.profile_node_tag):
                dpg.configure_item(viewer.profile_node_tag, show=False)
            return

        node = viewer.profile_node_tag
        if not dpg.does_item_exist(node):
            return

        dpg.delete_item(node, children_only=True)
        shape = viewer.get_slice_shape()
        real_h, real_w = max(1, shape[0]), max(1, shape[1])
        pmin, pmax = viewer.current_pmin, viewer.current_pmax
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]

        # Load profile dimming preferences
        prof_cfg = viewer.controller.settings.data.get(
            "profiles", {"dim_opacity": 0.6, "dim_thickness": 1.5}
        )
        dim_base_alpha = int(prof_cfg["dim_opacity"] * 255)

        for p_id, profile in viewer.view_state.profiles.items():
            if (
                not profile
                or not profile.visible
                or profile.pt1_phys is None
                or profile.pt2_phys is None
            ):
                continue

            # Map points to the viewer's current display voxel space
            v1 = viewer.view_state.world_to_display(
                profile.pt1_phys, is_buffered=viewer._is_buffered()
            )
            v2 = viewer.view_state.world_to_display(
                profile.pt2_phys, is_buffered=viewer._is_buffered()
            )
            if v1 is None or v2 is None:
                continue

            # Find the depth axis for the current orientation
            v_idx, _, _, _ = viewer._ORIENTATION_MAP.get(
                viewer.orientation, (None, 0, None, None)
            )
            if v_idx is None:
                continue

            z1, z2 = v1[v_idx], v2[v_idx]
            curr_z = viewer.slice_idx
            depth_min, depth_max = min(z1, z2), max(z1, z2)

            # Case 1: The segment is (mostly) in-plane for the current orientation
            if profile.orientation == viewer.orientation and abs(z1 - z2) < 0.5:
                depth_diff = abs(curr_z - z1)
                # Draw on current slice (0.5 tol) and extended adjacent range (6.5 tol)
                if depth_diff > 6.5:
                    continue

                is_adjacent = depth_diff > 0.5
                s1 = get_screen_pos(v1)
                s2 = get_screen_pos(v2)

                if s1 and s2:
                    col = list(profile.color)
                    if is_adjacent:
                        # Gradual dimming over ±6 slices relative to the settings base
                        alpha = int(
                            max(
                                20,
                                dim_base_alpha - (depth_diff * (dim_base_alpha / 7.5)),
                            )
                        )
                        col[3] = alpha
                        dpg.draw_line(
                            s1,
                            s2,
                            color=col,
                            thickness=prof_cfg["dim_thickness"],
                            parent=node,
                        )
                    else:
                        dpg.draw_line(s1, s2, color=col, thickness=2.0, parent=node)
                        dpg.draw_circle(
                            s1, 4, color=[255, 255, 255], fill=col, parent=node
                        )
                        dpg.draw_circle(
                            s2, 4, color=[255, 255, 255], fill=col, parent=node
                        )

            # Case 2: The segment is cross-plane (Show clue ring)
            else:
                # Only show clue if within 5 slices of the segment's depth range
                if depth_min - 5 <= curr_z <= depth_max + 5:
                    mid_phys = (profile.pt1_phys + profile.pt2_phys) / 2.0
                    v_mid = viewer.view_state.world_to_display(
                        mid_phys, is_buffered=viewer._is_buffered()
                    )
                    smid = get_screen_pos(v_mid)
                    if smid:
                        dim_col = list(profile.color)
                        dim_col[3] = 120
                        dpg.draw_circle(
                            smid, 7, color=dim_col, thickness=1.0, parent=node
                        )
                        dpg.draw_circle(
                            smid, 2, color=dim_col, fill=dim_col, parent=node
                        )

        dpg.configure_item(node, show=True)

    def draw_vector_field(self):
        viewer = self.viewer
        vs = viewer.view_state
        vol = viewer.volume

        node_tag = getattr(viewer, "vector_field_node_tag", None)
        if not node_tag or not dpg.does_item_exist(node_tag):
            return

        if not viewer.is_image_orientation() or not vs or not vol:
            dpg.configure_item(node_tag, show=False)
            return

        dpg.delete_item(node_tag, children_only=True)

        is_base_dvf = getattr(vol, "is_dvf", False)
        draw_base = is_base_dvf and vs.dvf.display_mode == "Vector Field"

        ov_id = vs.display.overlay_id
        ov_vs = viewer.controller.view_states.get(ov_id) if ov_id else None
        is_ov_dvf = getattr(ov_vs.volume, "is_dvf", False) if ov_vs else False
        draw_ov = is_ov_dvf and vs.display.overlay_mode == "DVF"

        if not draw_base and not draw_ov:
            dpg.configure_item(node_tag, show=False)
            return

        targets = []
        if draw_base:
            targets.append(
                (
                    vs,
                    (
                        vs.base_display_data
                        if vs.base_display_data is not None
                        else vol.data
                    ),
                    False,
                )
            )
        if draw_ov:
            targets.append((ov_vs, vs.display.overlay_data, True))

        ori = viewer.orientation

        pmin, pmax = viewer.current_pmin, viewer.current_pmax
        shape = viewer.get_slice_shape()
        real_h, real_w = shape[0], shape[1]

        if real_w == 0 or real_h == 0:
            return

        vox_w = (pmax[0] - pmin[0]) / real_w
        vox_h = (pmax[1] - pmin[1]) / real_h

        win_w, win_h = viewer.quad_w, viewer.quad_h

        start_x = max(0, int(-pmin[0] / vox_w))
        end_x = min(real_w, int((win_w - pmin[0]) / vox_w) + 1)
        start_y = max(0, int(-pmin[1] / vox_h))
        end_y = min(real_h, int((win_h - pmin[1]) / vox_h) + 1)

        ppm = viewer.get_pixels_per_mm()
        from vvv.maths.image import SliceRenderer

        for target_vs, display_data, is_overlay in targets:
            if display_data is None:
                continue

            if is_overlay:
                layer = viewer._package_overlay_layer()
                if not layer:
                    continue
                s_idx = viewer.slice_idx - layer.offset_slice
                disp_w = pmax[0] - pmin[0]
                disp_h = pmax[1] - pmin[1]
                shift_x = (
                    viewer.active_overlay_shift_x * (disp_w / real_w)
                    if real_w > 0
                    else 0.0
                )
                shift_y = (
                    viewer.active_overlay_shift_y * (disp_h / real_h)
                    if real_h > 0
                    else 0.0
                )
            else:
                s_idx = viewer.slice_idx
                shift_x, shift_y = 0.0, 0.0

            vx_slice = SliceRenderer.get_raw_slice(display_data, False, 0, s_idx, ori)
            vy_slice = SliceRenderer.get_raw_slice(display_data, False, 1, s_idx, ori)
            vz_slice = SliceRenderer.get_raw_slice(display_data, False, 2, s_idx, ori)

            if vx_slice.shape != (real_h, real_w) or vy_slice.shape != (real_h, real_w):
                continue

            if ori == ViewMode.AXIAL:
                h_comp, v_comp, d_comp = vx_slice, vy_slice, vz_slice
            elif ori == ViewMode.SAGITTAL:
                h_comp, v_comp, d_comp = -vy_slice, -vz_slice, vx_slice
            else:  # CORONAL
                h_comp, v_comp, d_comp = vx_slice, -vz_slice, vy_slice

            stride_x = max(1, int(target_vs.dvf.vector_sampling))
            stride_y = stride_x

            scale = target_vs.dvf.vector_scale

            c_min = np.array(target_vs.dvf.vector_color_min, dtype=np.float32)
            c_max = np.array(target_vs.dvf.vector_color_max, dtype=np.float32)
            t_min = target_vs.dvf.vector_min_length_draw
            t_max = max(t_min + 1e-5, target_vs.dvf.vector_color_max_mag)
            thickness = int(max(1.0, target_vs.dvf.vector_thickness))

            # Prevent GPU lag by increasing stride if zoomed out way too far
            num_x = max(0, (end_x - start_x)) // stride_x
            num_y = max(0, (end_y - start_y)) // stride_y
            if num_x * num_y > 8000:
                scale_factor = np.sqrt((num_x * num_y) / 8000)
                stride_x = max(stride_x, int(stride_x * scale_factor))
                stride_y = max(stride_y, int(stride_y * scale_factor))

            # Execute massive drawing batch
            for y in range(start_y, end_y, stride_y):
                for x in range(start_x, end_x, stride_x):
                    h_val, v_val, d_val = h_comp[y, x], v_comp[y, x], d_comp[y, x]

                    if h_val == 0 and v_val == 0 and d_val == 0:
                        continue

                    # Compute true 3D Physical Magnitude to compare against threshold
                    mag_3d = np.sqrt(h_val**2 + v_val**2 + d_val**2)
                    if mag_3d < target_vs.dvf.vector_min_length_draw:
                        continue

                    # Interpolate color based on magnitude
                    t_col = min(1.0, max(0.0, (mag_3d - t_min) / (t_max - t_min)))
                    c_interp = c_min + t_col * (c_max - c_min)
                    color = [
                        int(c_interp[0]),
                        int(c_interp[1]),
                        int(c_interp[2]),
                        int(c_interp[3]),
                    ]

                    # Anchor to the center of the voxel's bounding box and apply shift
                    screen_x = pmin[0] + shift_x + (x + 0.5) * vox_w
                    screen_y = pmin[1] + shift_y + (y + 0.5) * vox_h

                    # Exact physical mapping with scale (value in mm * pixels per mm * scale)
                    end_x_px = screen_x + (h_val * ppm * scale)
                    end_y_px = screen_y + (v_val * ppm * scale)

                    # Dynamically scale arrowhead size
                    arrow_size = int(
                        max(
                            1.0,
                            min(
                                4.0,
                                np.hypot(h_val * ppm * scale, v_val * ppm * scale)
                                * 0.3,
                            ),
                        )
                    )

                    if mag_3d < target_vs.dvf.vector_min_length_arrow:
                        dpg.draw_line(
                            [screen_x, screen_y],
                            [end_x_px, end_y_px],
                            color=color,
                            thickness=thickness,
                            parent=node_tag,
                        )
                    else:
                        dpg.draw_arrow(
                            [end_x_px, end_y_px],
                            [screen_x, screen_y],
                            color=color,
                            thickness=thickness,
                            size=arrow_size,
                            parent=node_tag,
                        )

        dpg.configure_item(node_tag, show=True)
