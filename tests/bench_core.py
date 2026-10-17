#!/usr/bin/env python3
"""
VVV core speed benchmark
========================
Times what a user actually waits for, in the default ("Auto") rendering mode:

  load.*      read a 512x512x300 CT from disk (VolumeData + ViewState)
  <cfg>.*     real frames of the running app (4 viewers, real DearPyGui, real
              tick + sidebar sync + texture upload + render) while an action is
              repeated every frame:
                idle, slice_scroll, crosshair_drag, wl_drag, pan, zoom

  configs:    ct          one CT in the 4 viewers
              fusion      CT + PET overlay (Alpha, Hot)
              fusion_roi  CT + PET overlay + ROI covering ~50% of the CT

Frame time = one full main-loop iteration with the FPS throttle sleep and vsync
disabled, i.e. pure work. Reported as median / p90 over N frames.

Each config runs in its own subprocess with HOME pointed to a temporary
directory, so the user's settings/history are neither used nor modified.
Results are written to bench_results/<host>/core_<date>_<commit>.json, for
comparison with earlier runs of the same machine only. <host> is the macOS
LocalHostName or the Linux hostname (override with VVV_BENCH_HOST).

Usage:
    python tests/bench_core.py               # full run, writes results
    python tests/bench_core.py --quick       # fewer frames, smoke test
    python tests/bench_core.py --no-save     # print only
Do not use the mouse/keyboard on the bench window while it runs.
"""

import argparse
import datetime
import json
import math
import os
import platform
import socket
import statistics
import subprocess
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

DATA_VERSION = 1  # bump when the generated data changes (invalidates the cache)
VIEWPORT = (1600, 1000)
CONFIGS = {
    "ct": ["idle", "slice_scroll", "crosshair_drag", "wl_drag", "pan", "zoom"],
    "fusion": ["idle", "slice_scroll", "crosshair_drag", "wl_drag"],
    "fusion_roi": ["idle", "slice_scroll", "crosshair_drag"],
}


# ──────────────────────────────────────────────────────────────────────────────
# Data
# ──────────────────────────────────────────────────────────────────────────────


def make_data(data_dir):
    """Create (once) a CT, a PET overlay and an ROI mask; return their paths."""
    import numpy as np
    import SimpleITK as sitk

    paths = {
        "ct": os.path.join(data_dir, "ct.nii"),
        "pet": os.path.join(data_dir, "pet.nii"),
        "roi": os.path.join(data_dir, "roi.nii"),
    }
    if all(os.path.exists(p) for p in paths.values()):
        return paths
    os.makedirs(data_dir, exist_ok=True)
    rng = np.random.default_rng(0)

    # CT 512x512x300, 0.98 x 0.98 x 1.5 mm, body-like ellipse + noise
    z, y, x = np.ogrid[:300, :512, :512]
    body = ((x - 256) / 220.0) ** 2 + ((y - 256) / 160.0) ** 2 < 1.0
    ct = np.where(body, 40, -1000).astype(np.int16) + rng.integers(
        -30, 30, (300, 512, 512), dtype=np.int16
    )
    img = sitk.GetImageFromArray(ct)
    img.SetSpacing((0.98, 0.98, 1.5))
    img.SetOrigin((-250.0, -250.0, -225.0))
    sitk.WriteImage(img, paths["ct"])

    # PET 128x128x110, 4 mm, covering the CT field of view, a few hot spots
    pz, py, px = np.ogrid[:110, :128, :128]
    pet = rng.random((110, 128, 128), dtype=np.float32)
    for cz, cy, cx in [(50, 60, 60), (70, 70, 80), (30, 50, 70)]:
        pet += 20.0 * np.exp(-((pz - cz) ** 2 + (py - cy) ** 2 + (px - cx) ** 2) / 40.0)
    pimg = sitk.GetImageFromArray(pet)
    pimg.SetSpacing((4.0, 4.0, 4.0))
    pimg.SetOrigin((-254.0, -254.0, -222.0))
    sitk.WriteImage(pimg, paths["pet"])

    # ROI on the CT grid: box covering ~50% of the volume
    roi = np.zeros((300, 512, 512), dtype=np.uint8)
    roi[40:260, 60:452, 60:452] = 1
    rimg = sitk.GetImageFromArray(roi)
    rimg.CopyInformation(img)
    sitk.WriteImage(rimg, paths["roi"])
    return paths


def stats_ms(seconds):
    ms = sorted(s * 1000.0 for s in seconds)
    p90 = ms[min(len(ms) - 1, int(round(0.9 * (len(ms) - 1))))]
    med = statistics.median(ms)
    return {
        "median_ms": round(med, 3),
        "p90_ms": round(p90, 3),
        "mean_ms": round(statistics.fmean(ms), 3),
        "n": len(ms),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Load benchmark (headless)
# ──────────────────────────────────────────────────────────────────────────────


def bench_load(paths, repeats):
    from vvv.maths.image import VolumeData
    from vvv.core.view_state import ViewState

    VolumeData(paths["ct"])  # warm the OS file cache: measure vvv, not the disk
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        ViewState(VolumeData(paths["ct"]))
        times.append(time.perf_counter() - t0)
    return {"load.ct": stats_ms(times)}


# ──────────────────────────────────────────────────────────────────────────────
# Frame benchmark (worker subprocess, real GUI)
# ──────────────────────────────────────────────────────────────────────────────


class _NoSleepTime:
    """Stand-in for the `time` module inside gui.py: disables the FPS throttle sleep."""

    def __getattr__(self, name):
        return getattr(time, name)

    def sleep(self, seconds):
        pass


def _make_actions(c, v1):
    """Per-frame actions, using the same viewer entry points as the UI handlers."""

    def idle(i):
        pass

    def slice_scroll(i):  # mouse wheel over V1, bouncing every 20 frames
        v1.on_scroll(1 if (i // 20) % 2 == 0 else -1)

    def crosshair_drag(i):  # left-drag in V1: crosshair moves, other viewers re-slice
        h, w = v1.get_slice_shape()
        px = w / 2 + 0.3 * w * math.sin(i / 15.0)
        py = h / 2 + 0.3 * h * math.cos(i / 15.0)
        now = time.time()
        for v in c.viewers.values():  # same lazy marking as SliceViewer.on_drag
            if v.orientation != v1.orientation and v.lazy_lin and v.image_id == v1.image_id:
                v._last_move_time = now
                v._nn_settle_done = False
                v._lazy_live_flag = True
        v1.update_crosshair_data(px, py)
        c.sync.propagate_sync(v1.image_id)

    def wl_drag(i):  # right-drag in V1 (as InteractionManager W/L drag)
        vs = v1.view_state
        v1._mark_lazy_interaction()
        f = 1.03 if (i // 20) % 2 == 0 else 1 / 1.03
        v1.update_window_level(vs.display.ww * f, vs.display.wl)

    def pan(i):  # pan drag in V1 (as SliceViewer.on_drag pan branch)
        d = 4.0 if (i // 20) % 2 == 0 else -4.0
        v1.pan_offset[0] += d
        v1.pan_offset[1] += d / 2
        v1.is_geometry_dirty = True
        v1._mark_lazy_interaction()
        c.sync.propagate_camera(v1)

    def zoom(i):  # ctrl+wheel in V1
        v1.on_zoom("in" if (i // 10) % 2 == 0 else "out")

    return {f.__name__: f for f in (idle, slice_scroll, crosshair_drag, wl_drag, pan, zoom)}


def worker_main(config, data_dir, n_frames, n_warmup):
    import dearpygui.dearpygui as dpg
    import vvv.ui.gui as G
    from vvv.cli import parse_cli_arguments
    from vvv.core.controller import Controller
    from vvv.ui.viewer import SliceViewer

    paths = make_data(data_dir)
    G.time = _NoSleepTime()

    dpg.create_context()
    c = Controller()
    c.use_history = False
    for tag in ["V1", "V2", "V3", "V4"]:
        c.viewers[tag] = SliceViewer(tag, c)
    gui = G.MainGUI(c)
    c.gui = gui
    dpg.create_viewport(title="vvv bench", width=VIEWPORT[0], height=VIEWPORT[1], vsync=False)

    ds = paths["ct"] if config == "ct" else f"{paths['ct']},{paths['pet']},hot"
    boot = gui.create_boot_sequence(parse_cli_arguments([ds]), None, False, False)
    out = {"results": {}, "complete": False}

    def driver():
        for _ in range(10):
            yield
        base_id = c.layout["V1"]  # not the first loaded: images load in parallel
        base_vs = c.view_states[base_id]
        if config != "ct":  # wait for the background overlay resample
            t_end = time.time() + 120
            while base_vs.display.overlay_data is None and time.time() < t_end:
                yield
            if base_vs.display.overlay_data is None:
                raise RuntimeError("overlay was never resampled")
        if config == "fusion_roi":
            c.roi.load_binary_mask(base_id, paths["roi"])
            c.ui_needs_refresh = True
        for _ in range(10):
            yield
        out["nn_modes"] = {t: v.nn_mode.name for t, v in c.viewers.items()}
        out["lazy_lin"] = {t: v.lazy_lin for t, v in c.viewers.items()}

        actions = _make_actions(c, c.viewers["V1"])
        for name in CONFIGS[config]:
            act = actions[name]
            for i in range(n_warmup):
                act(i)
                yield
            times = []
            t = time.perf_counter()
            for i in range(n_frames):
                act(n_warmup + i)
                yield
                now = time.perf_counter()
                times.append(now - t)
                t = now
            out["results"][f"{config}.{name}"] = stats_ms(times)
        out["complete"] = True
        dpg.stop_dearpygui()

    def guarded_driver():
        # A failing task no longer stops the app (gui._step_task): stop it here
        try:
            yield from driver()
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"
            dpg.stop_dearpygui()

    def start():
        gui.tasks.append(guarded_driver())

    dpg.set_frame_callback(5, callback=start)
    gui.run(boot_generator=boot)
    print("RESULT_JSON: " + json.dumps(out))


def run_worker(config, data_dir, n_frames, n_warmup):
    env = dict(os.environ)
    home = tempfile.mkdtemp(prefix="vvv_bench_home_")
    env["HOME"] = home  # default settings, user's config untouched
    env.pop("APPDATA", None)
    cmd = [
        sys.executable, os.path.abspath(__file__), "--worker", config,
        "--data", data_dir, "--frames", str(n_frames), "--warmup", str(n_warmup),
    ]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"bench worker '{config}' timed out")
    res = {}
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT_JSON: "):
            res = json.loads(line[len("RESULT_JSON: "):])
    if res.get("complete"):
        return res
    sys.stderr.write(proc.stdout[-3000:] + proc.stderr[-3000:])
    raise RuntimeError(
        f"bench worker '{config}' failed (exit {proc.returncode}): {res.get('error', '')}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Master
# ──────────────────────────────────────────────────────────────────────────────


def _git(*args):
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def machine_name():
    """Stable machine name: the network hostname of a laptop changes (DHCP)."""
    if os.environ.get("VVV_BENCH_HOST"):
        return os.environ["VVV_BENCH_HOST"]
    if sys.platform == "darwin":
        name = subprocess.run(
            ["scutil", "--get", "LocalHostName"], capture_output=True, text=True
        ).stdout.strip()
        if name:
            return name.lower()
    return socket.gethostname().split(".")[0].lower()


def environment():
    import numpy
    import SimpleITK
    import dearpygui

    try:
        import numba
        numba_v = numba.__version__
    except Exception:
        numba_v = None
    dirty = [
        l for l in _git("status", "--porcelain").splitlines()
        if not l[3:].startswith("bench_results/")
    ]
    return {
        "host": machine_name(),
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "simpleitk": SimpleITK.Version_VersionString(),
        "dearpygui": dearpygui.__version__,
        "numba": numba_v,
        "commit": _git("rev-parse", "--short", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(dirty),
    }


def _loadavg():
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        return None


def print_table(results):
    print(f"\n  {'scenario':28s} {'median':>9s} {'p90':>9s} {'fps':>7s}")
    print("  " + "-" * 56)
    for key, r in results.items():
        fps = 1000.0 / r["median_ms"] if r["median_ms"] > 0 else float("inf")
        fps_s = "" if key.startswith("load.") else f"{fps:7.1f}"
        print(f"  {key:28s} {r['median_ms']:7.1f}ms {r['p90_ms']:7.1f}ms {fps_s}")


def master_main(args):
    env = environment()
    n_frames, n_warmup, load_rep = (30, 15, 2) if args.quick else (120, 15, 5)
    data_dir = os.path.join(tempfile.gettempdir(), f"vvv_bench_data_v{DATA_VERSION}")

    print(f"vvv bench_core — host {env['host']} · {env['platform']} · commit {env['commit']}"
          f"{' (dirty)' if env['dirty'] else ''}")
    la = _loadavg()
    if la and env["cpu_count"] and la[0] > 0.5 * env["cpu_count"]:
        print(f"  WARNING: machine looks busy (load average {la}) — results may be slower")

    print("  preparing data ...", flush=True)
    paths = make_data(data_dir)

    results, run_info = {}, {}
    print("  load ...", flush=True)
    results.update(bench_load(paths, load_rep))
    for config in CONFIGS:
        print(f"  frames: {config} ...", flush=True)
        res = run_worker(config, data_dir, n_frames, n_warmup)
        results.update(res["results"])
        run_info[config] = {"nn_modes": res.get("nn_modes"), "lazy_lin": res.get("lazy_lin")}

    report = {
        "schema": 1,
        "bench": "core",
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "env": env,
        "params": {"frames": n_frames, "warmup": n_warmup, "load_repeats": load_rep,
                   "viewport": list(VIEWPORT), "data_version": DATA_VERSION, "quick": args.quick},
        "loadavg": {"start": la, "end": _loadavg()},
        "render_modes": run_info,
        "results": results,
    }
    print_table(results)
    if not args.no_save:
        out_dir = os.path.join(REPO, "bench_results", env["host"])
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = os.path.join(out_dir, f"core_{stamp}_{env['commit'] or 'nogit'}.json")
        with open(out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  saved {os.path.relpath(out, REPO)}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--quick", action="store_true", help="fewer frames (smoke test)")
    p.add_argument("--no-save", action="store_true", help="do not write bench_results/")
    p.add_argument("--worker", help=argparse.SUPPRESS)
    p.add_argument("--data", help=argparse.SUPPRESS)
    p.add_argument("--frames", type=int, default=120, help=argparse.SUPPRESS)
    p.add_argument("--warmup", type=int, default=15, help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.worker:
        worker_main(args.worker, args.data, args.frames, args.warmup)
    else:
        master_main(args)


if __name__ == "__main__":
    main()
