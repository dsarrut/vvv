import collections
import platform

import dearpygui.dearpygui as dpg

from vvv.ui.render_strategy import GL_NEAREST_SUPPORTED, NNMode
import vvv.ui.render_strategy as _rs_mod  # module ref: _NUMBA_AVAILABLE changes at runtime

_NN_LABELS = {
    NNMode.HW_GL_NEAREST: "HW GL_NEAREST",
    NNMode.SW_DUAL_NATIVE: "SW Dual-Native",
    NNMode.SW_DUAL_RESAMPLED: "SW Dual-Resampled",
    NNMode.SW_SINGLE_MERGED: "SW Single-Merged",
    NNMode.SW_SINGLE_NATIVE: "SW Single-Native",
}


class DebugOverlay:
    """Debug window (vvv --debug): FPS plot and the render route of each viewer."""

    def __init__(self, controller):
        self.controller = controller
        self.fps_data = collections.deque(maxlen=600)
        self.time_data = collections.deque(maxlen=600)
        with dpg.window(
            label="Debug",
            tag="fps_debug_window",
            width=480,
            height=370,
            pos=[10, 30],
        ):
            self.fps_label = dpg.add_text("FPS: --   Avg: --   Min: --")
            # Multiline readonly input_text → user can select & copy the text
            self.render_input = dpg.add_input_text(
                default_value="...",
                multiline=True,
                readonly=True,
                width=-1,
                height=120,
                tag="debug_render_info",
            )
            with dpg.plot(
                label="",
                height=180,
                width=-1,
                no_menus=True,
                no_title=True,
            ):
                self.x_axis = dpg.add_plot_axis(
                    dpg.mvXAxis, label="Time (s)", no_gridlines=True
                )
                y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="FPS")
                dpg.set_axis_limits(y_axis, 0, 125)
                self.fps_series = dpg.add_line_series([], [], label="FPS", parent=y_axis)

    def update(self):
        """Called once per frame."""
        self._update_fps()
        dpg.set_value(self.render_input, "\n".join(self._render_route_lines()))

    def _update_fps(self):
        delta = dpg.get_delta_time()
        t_now = dpg.get_total_time()
        if not 0.0001 < delta < 5.0:
            return
        fps = 1.0 / delta
        self.fps_data.append(fps)
        self.time_data.append(t_now)
        avg = sum(self.fps_data) / len(self.fps_data)
        mn = min(self.fps_data)
        dpg.set_value(self.fps_label, f"FPS: {fps:.1f}   Avg: {avg:.1f}   Min: {mn:.1f}")
        dpg.set_value(self.fps_series, [list(self.time_data), list(self.fps_data)])
        dpg.set_axis_limits(self.x_axis, max(0.0, t_now - 10.0), t_now + 0.2)

    def _render_route_lines(self):
        viewers = self.controller.viewers

        # Summarise lazy state across all viewers for a quick top-level read
        def _lazy_summary(attr):
            a = all(getattr(v, attr, False) for v in viewers.values())
            n = any(getattr(v, attr, False) for v in viewers.values())
            return "ALL ON" if a else ("SOME ON" if n else "OFF")

        _rs_mod._init_numba()
        lines = [
            f"Platform: {platform.system()}   GL: {'ON' if GL_NEAREST_SUPPORTED else 'OFF'}   "
            f"Numba: {'ON' if _rs_mod._NUMBA_AVAILABLE else 'OFF (slow fusion!)'}   "
            f"debug: {getattr(self.controller, 'debug_mode', False)}",
            f"Lazy-Lin: {_lazy_summary('lazy_lin')}",
        ]
        for vtag, viewer in viewers.items():
            vs = viewer.view_state
            pix = bool(vs and vs.display.pixelated_zoom) if vs else False
            nn_mode = getattr(viewer, "nn_mode", None)
            lazy_tag = ""
            if getattr(viewer, "lazy_lin", False):
                live_s = "" if getattr(viewer, "_nn_settle_done", True) else " LIVE"
                lazy_tag = f"  [lazy-lin{live_s}]"
            if pix and nn_mode is not None:
                mode = _NN_LABELS.get(nn_mode, f"mode-{nn_mode}") + lazy_tag
            elif pix:
                mode = "NN" + lazy_tag
            else:
                mode = "Bilinear"
            lines.append(f"  {vtag}: {mode}")
        return lines
