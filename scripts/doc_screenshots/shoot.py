"""Doc screenshot of one scene (macOS), run by run_all.sh:

    python shoot.py OUT.png [--tab TAG] [--size WxH] [--wait SEC]
        [--setup CODE|FILE.py] [--crop [win:]TAG:OUT.png ...] -- vvv arguments

Runs the real vvv main loop; a task injected after the boot runs the setup,
switches the tab, waits, and captures only the vvv window (screencapture -l
<window id>: the window's own pixels, never the rest of the screen).
A setup file may define during(), a generator run over frames (async work).
--crop TAG: an item; win:TAG: a window or child window (its empty bottom is
trimmed). The settings and history are not saved: run_all.sh also gives a
temporary HOME, since loading files updates the recent files list."""

import os
import subprocess
import sys
import tempfile
import time

import dearpygui.dearpygui as dpg
import numpy as np
from PIL import Image


def window_shot():
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    wins = [w for w in app.windows() if w.isVisible() and w.frame().size.width >= 600]
    if len(wins) != 1:
        raise RuntimeError(f"expected one vvv window, got {len(wins)}")
    w = wins[0]
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    subprocess.run(["screencapture", "-x", "-o", "-l", str(w.windowNumber()), tmp], check=True)
    im = Image.open(tmp)
    im.load()
    os.remove(tmp)
    frame = w.frame()
    content = w.contentRectForFrameRect_(frame)
    scale = im.size[0] / frame.size.width
    title_h = int(round((frame.size.height - content.size.height) * scale))
    return im.crop((0, title_h, im.size[0], im.size[1])), scale


def trim_bottom(im, margin=16):
    """Cut the empty bottom of a panel (rows of one color, the border apart)."""
    a = np.asarray(im.convert("RGB")).astype(int)[:, 10:-10]
    busy = np.nonzero((a.max(axis=(1, 2)) - a.min(axis=(1, 2))) > 30)[0]
    if len(busy) == 0:
        return im
    return im.crop((0, 0, im.width, min(im.height, busy.max() + margin)))


def main():
    argv = sys.argv[1:]
    sep = argv.index("--")
    opts, vvv_args = argv[:sep], argv[sep + 1:]
    out = opts.pop(0)
    tab, size, crops, setup, wait = None, (1280, 800), [], None, 3.0
    while opts:
        k = opts.pop(0)
        if k == "--tab":
            tab = opts.pop(0)
        elif k == "--size":
            size = tuple(int(v) for v in opts.pop(0).split("x"))
        elif k == "--crop":
            crops.append(opts.pop(0).rsplit(":", 1))
        elif k == "--setup":
            setup = opts.pop(0)
        elif k == "--wait":
            wait = float(opts.pop(0))

    from vvv import cli
    from vvv.app import build_app

    workspaces = [f for f in vvv_args if f.lower().endswith(".vvw")]
    images = cli.parse_cli_arguments([f for f in vvv_args if not f.lower().endswith(".vvw")])

    dpg.create_context()
    ctrl, gui = build_app(use_history=False)
    dpg.create_viewport(title="VVV", width=size[0], height=size[1], x_pos=40, y_pos=40)

    def capture_task():
        try:
            yield from _capture()
        except Exception:
            import traceback
            traceback.print_exc()
            os._exit(3)  # never leave the window open on an error

    def _capture():
        for _ in range(30):
            yield
        if setup:
            env = {"gui": gui, "ctrl": ctrl, "dpg": dpg}
            exec(open(setup).read() if setup.endswith(".py") else setup, env)
            if "during" in env:  # a generator run over frames (async work)
                yield from env["during"]()
        if tab:
            gui.on_nav_clicked(None, None, tab)
        t0 = time.time()
        while time.time() - t0 < wait:  # background resampling, plugin refresh
            ctrl.ui_needs_refresh = True
            yield
        ctrl.status_message = None
        if dpg.does_item_exist("global_status_text"):
            dpg.set_value("global_status_text", "")
        for _ in range(10):
            yield
        im, scale = window_shot()
        im.save(out)
        print(f"{out} {im.size} nav={[t for _, t in gui.nav_items]}")
        for item, path in crops:
            is_win = item.startswith("win:")
            if is_win:  # a window or child window: no rect_min
                item = item[4:]
                (x0, y0), (w, h) = dpg.get_item_pos(item), dpg.get_item_rect_size(item)
                x1, y1, p = x0 + w, y0 + h, 0
            else:
                (x0, y0), (x1, y1) = dpg.get_item_rect_min(item), dpg.get_item_rect_max(item)
                p = 6
            box = [int(round(v * scale)) for v in (x0 - p, y0 - p, x1 + p, y1 + p)]
            crop = im.crop(box)
            (trim_bottom(crop) if is_win else crop).save(path)
            print(f"{path} {item} {box}")
        dpg.stop_dearpygui()

    def boot():
        yield from cli.boot_sequence(gui, images, workspaces)
        gui.tasks.append(capture_task())

    from vvv.ui.ui_drop import cleanup_os_drop

    def shutdown():  # like gui._shutdown, without saving settings / history
        for plugin in gui.plugins:
            gui._call_plugin(plugin, "destroy")
        cleanup_os_drop()
        dpg.destroy_context()
        # Exit now: a background numba / OpenMP kernel (MIP precompute) still
        # running at interpreter teardown aborts the process (libomp).
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    gui._shutdown = shutdown
    gui.run(boot_generator=boot())


if __name__ == "__main__":
    main()
