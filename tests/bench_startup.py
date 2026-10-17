#!/usr/bin/env python3
"""
VVV startup benchmark
=====================
Time from launching vvv to the first frame drawn with everything loaded:

  startup.empty        UI only
  startup.ct_large     one 128x512x512 image
  startup.four_images  four 64x256x256 images, one sync group
  startup.workspace    workspace: base + overlay (resampled) + 2 ROIs
  startup.python       interpreter start (spawn -> first line), all runs
  startup.imports      vvv + DearPyGui imports, all runs

Each boot is a fresh subprocess (cold start, like the command line) with HOME
pointed to a temporary directory: default settings, user config untouched.
"Ready" = boot finished, no task left, overlays resampled, one frame rendered.
Each scenario checks it loaded what it should, so a broken boot cannot report
a (fast) time.

Results go to bench_results/<host>/startup_<date>_<commit>.json and are
compared with the previous result of the same machine (see bench_core.py).

Usage:
    python tests/bench_startup.py              # 1 warm-up + 5 boots per scenario
    python tests/bench_startup.py --quick      # 1 + 2 boots
    python tests/bench_startup.py --ref 9f08fb5 / --no-save / --no-compare
"""

import time

_T_SCRIPT = time.time()  # before any heavy import: worker import cost is measured

import argparse  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DATA_VERSION = 1
VIEWPORT = (1280, 720)
SCENARIOS = {
    # name: expected (images, rois, overlays)
    "empty": (0, 0, 0),
    "ct_large": (1, 0, 0),
    "four_images": (4, 0, 0),
    "workspace": (2, 2, 1),
}


# ──────────────────────────────────────────────────────────────────────────────
# Worker: one cold boot
# ──────────────────────────────────────────────────────────────────────────────


def worker_main(scenario, data_dir):
    sys.path.insert(0, os.path.join(REPO, "src"))
    import dearpygui.dearpygui as dpg
    from vvv.core.controller import Controller
    from vvv.ui.gui import MainGUI
    from vvv.ui.viewer import SliceViewer

    t_imports = time.time()

    dpg.create_context()
    c = Controller()
    c.use_history = False
    for tag in ["V1", "V2", "V3", "V4"]:
        c.viewers[tag] = SliceViewer(tag, c)
    gui = MainGUI(c)
    c.gui = gui
    dpg.create_viewport(title="vvv bench startup", width=VIEWPORT[0], height=VIEWPORT[1])

    def task(path, sync_group=0):
        return {"base": path, "fusion": None, "sync_group": sync_group,
                "base_cmap": None, "labels": []}

    if scenario == "empty":
        boot = None
    elif scenario == "ct_large":
        boot = gui.create_boot_sequence([task(os.path.join(data_dir, "large.nii"))])
    elif scenario == "four_images":
        boot = gui.create_boot_sequence(
            [task(os.path.join(data_dir, f"img{i}.nii"), 1) for i in range(4)]
        )
    else:
        boot = gui.load_workspace_sequence(os.path.join(data_dir, "ws.vvw"))

    out = {}

    def ready_monitor():
        # boot_generator has finished when the first task runs; wait for the
        # rest (other tasks, background overlay resample), then one frame
        t_end = time.time() + 120
        while time.time() < t_end:
            overlays_pending = any(
                vs.display.overlay.image_id and vs.display.overlay_data is None
                for vs in c.view_states.values()
            )
            if len(gui.tasks) <= 1 and not overlays_pending:
                break
            yield
        yield  # this frame is rendered with everything in place
        out["ready"] = time.time()
        out["images"] = len(c.view_states)
        out["rois"] = sum(len(vs.rois) for vs in c.view_states.values())
        out["overlays"] = sum(
            1 for vs in c.view_states.values()
            if vs.display.overlay.image_id and vs.display.overlay_data is not None
        )
        dpg.stop_dearpygui()

    gui.tasks.append(ready_monitor())
    gui.run(boot_generator=boot)
    out.update({"script": _T_SCRIPT, "imports": t_imports})
    print("RESULT_JSON: " + json.dumps(out))


# ──────────────────────────────────────────────────────────────────────────────
# Master
# ──────────────────────────────────────────────────────────────────────────────


def make_data(data_dir):
    """Create (once) the images and a workspace saved by vvv itself."""
    import numpy as np
    import SimpleITK as sitk

    ws_path = os.path.join(data_dir, "ws.vvw")
    if os.path.exists(ws_path):
        return
    os.makedirs(data_dir, exist_ok=True)
    rng = np.random.default_rng(0)

    def write(name, shape, roi=False):
        if roi:
            data = np.zeros(shape, np.uint8)
            z, y, x = (s // 4 for s in shape)
            data[z:3 * z, y:3 * y, x:2 * x if name == "roi1.nii" else 3 * x] = 1
        else:
            data = (rng.random(shape, dtype=np.float32) * 1000).astype(np.float32)
        img = sitk.GetImageFromArray(data)
        path = os.path.join(data_dir, name)
        sitk.WriteImage(img, path)
        return path

    write("large.nii", (128, 512, 512))
    for i in range(4):
        write(f"img{i}.nii", (64, 256, 256))
    write("overlay.nii", (64, 256, 256))
    write("roi1.nii", (64, 256, 256), roi=True)
    write("roi2.nii", (64, 256, 256), roi=True)

    # Build the workspace with vvv's own loader/saver so its format stays current
    sys.path.insert(0, os.path.join(REPO, "src"))
    from vvv.core.controller import Controller

    old_home = os.environ.get("HOME")
    os.environ["HOME"] = tempfile.mkdtemp(prefix="vvv_bench_home_")  # user config untouched
    try:
        c = Controller()
        c.use_history = False
        _build_workspace(c, data_dir, ws_path)
    finally:
        os.environ["HOME"] = old_home


def _build_workspace(c, data_dir, ws_path):
    base = c.file.load_image(os.path.join(data_dir, "img0.nii"))
    ov = c.file.load_image(os.path.join(data_dir, "overlay.nii"))
    base_vs, ov_vs = c.view_states[base], c.view_states[ov]
    base_vs.set_overlay(ov, ov_vs.volume)
    c._apply_overlay_resample(base_vs, ov_vs)
    for name in ("roi1.nii", "roi2.nii"):
        c.roi.load_binary_mask(base, os.path.join(data_dir, name))
    c.layout = {"V1": base, "V2": base, "V3": base, "V4": base}
    c.file.save_workspace(ws_path)


def run_boot(scenario, data_dir):
    env = dict(os.environ)
    env["HOME"] = tempfile.mkdtemp(prefix="vvv_bench_home_")
    env.pop("APPDATA", None)
    cmd = [sys.executable, os.path.abspath(__file__), "--worker", scenario, "--data", data_dir]
    t_spawn = time.time()
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"startup worker '{scenario}' timed out")
    res = {}
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT_JSON: "):
            res = json.loads(line[len("RESULT_JSON: "):])
    expected = SCENARIOS[scenario]
    got = (res.get("images"), res.get("rois"), res.get("overlays"))
    if "ready" not in res or got != expected:
        sys.stderr.write(proc.stdout[-3000:] + proc.stderr[-3000:])
        raise RuntimeError(
            f"startup '{scenario}': loaded (images, rois, overlays)={got}, expected {expected}"
        )
    return {
        "total": res["ready"] - t_spawn,
        "python": res["script"] - t_spawn,
        "imports": res["imports"] - res["script"],
    }


def print_table(results):
    print(f"\n  {'scenario':28s} {'median':>10s} {'p90':>10s}")
    print("  " + "-" * 50)
    for key, r in results.items():
        print(f"  {key:28s} {r['median_ms']:8.0f}ms {r['p90_ms']:8.0f}ms")


def master_main(args):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import bench_common as bc

    env = bc.environment()
    n_warmup, n_iter = (1, 2) if args.quick else (1, 5)
    data_dir = os.path.join(tempfile.gettempdir(), f"vvv_bench_startup_data_v{DATA_VERSION}")

    print(f"vvv bench_startup — host {env['host']} · {env['platform']} · commit {env['commit']}"
          f"{' (dirty)' if env['dirty'] else ''}")
    la = bc.loadavg()
    print("  preparing data ...", flush=True)
    make_data(data_dir)

    results, python_t, imports_t = {}, [], []
    for scenario in SCENARIOS:
        print(f"  boots: {scenario} ...", flush=True)
        totals = []
        for i in range(n_warmup + n_iter):
            r = run_boot(scenario, data_dir)
            if i >= n_warmup:
                totals.append(r["total"])
                python_t.append(r["python"])
                imports_t.append(r["imports"])
        results[f"startup.{scenario}"] = bc.stats_ms(totals)
    results["startup.python"] = bc.stats_ms(python_t)
    results["startup.imports"] = bc.stats_ms(imports_t)

    report = {
        "schema": 1,
        "bench": "startup",
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "env": env,
        "params": {"warmup": n_warmup, "boots": n_iter, "viewport": list(VIEWPORT),
                   "data_version": DATA_VERSION, "quick": args.quick},
        "loadavg": {"start": la, "end": bc.loadavg()},
        "results": results,
    }
    print_table(results)
    saved = None
    if not args.no_save:
        saved = bc.save_report(report)
        print(f"\n  saved {os.path.relpath(saved, REPO)}")
    if not args.no_compare:
        ref = bc.resolve_ref(args.ref, "startup", env["host"], before=saved)
        if ref is None:
            print("\n  no earlier result on this machine to compare with")
        else:
            bc.compare(bc.load_report(ref), report)


def main():
    p = argparse.ArgumentParser(description="vvv startup benchmark")
    p.add_argument("--quick", action="store_true", help="2 boots per scenario")
    p.add_argument("--no-save", action="store_true", help="do not write bench_results/")
    p.add_argument("--ref", help="result to compare with: commit prefix or json path")
    p.add_argument("--no-compare", action="store_true", help="skip the comparison")
    p.add_argument("--worker", help=argparse.SUPPRESS)
    p.add_argument("--data", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.worker:
        worker_main(args.worker, args.data)
    else:
        master_main(args)


if __name__ == "__main__":
    main()
