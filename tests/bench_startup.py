#!/usr/bin/env python3
"""
VVV Startup Performance Benchmark
=================================
Measures the initialization and data loading time from command-line boot 
to the first fully rendered frame of the UI.

Usage:
    cd /path/to/vvv
    python tests/bench_startup.py              # default iterations
    python tests/bench_startup.py --quick      # fewer iterations

Scenarios:
  1. Empty Boot (UI Only)
  2. Single Large Image (128MB)
  3. Four Images + Sync Groups
  4. Complex Workspace (Base, Overlay, 2 ROIs)
"""

import sys
import os
import json
import time
import tempfile
import argparse
import datetime
import platform
import subprocess
import numpy as np
import SimpleITK as sitk

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

N_ITER = 3
N_WARMUP = 1


def make_image(path, shape, val=100.0, is_roi=False):
    """Helper to generate physical NIfTI files on disk for the test to load."""
    dtype = np.uint8 if is_roi else np.float32
    data = np.full(shape, val, dtype=dtype)
    if is_roi:
        # Add a localized block of 1s to ensure bounding-box extraction logic runs
        data[10:30, 10:30, 10:30] = 1
    img = sitk.GetImageFromArray(data)
    sitk.WriteImage(img, path)
    return path


# ──────────────────────────────────────────────────────────────────────────────
# The Worker Process (Simulates the Command Line Boot)
# ──────────────────────────────────────────────────────────────────────────────

def worker_main(scenario_id, tmpdir):
    """
    Runs inside an isolated subprocess.
    Timer starts immediately to capture Python import overhead.
    """
    t0 = time.perf_counter()

    # Insert project src into path for imports
    src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    sys.path.insert(0, src_path)

    import dearpygui.dearpygui as dpg
    from vvv.core.controller import Controller
    from vvv.ui.gui import MainGUI
    from vvv.ui.viewer import SliceViewer

    image_tasks = []
    ws_path = None

    # Route the scenario
    if scenario_id == 1:
        pass  # Empty Boot
    elif scenario_id == 2:
        image_tasks = [{"base": os.path.join(tmpdir, "large.nii"), "fusion": None, "sync_group": 0}]
    elif scenario_id == 3:
        for i in range(4):
            image_tasks.append({"base": os.path.join(tmpdir, f"img{i}.nii"), "fusion": None, "sync_group": 1})
    elif scenario_id == 4:
        ws_path = os.path.join(tmpdir, "ws.vvw")

    # Standard CLI Boot Sequence
    dpg.create_context()
    controller = Controller()
    controller.use_history = False  # Prevent polluting the developer's actual history file

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui

    dpg.create_viewport(title="VVV Bench", width=1280, height=720)

    if ws_path:
        boot_gen = gui.load_workspace_sequence(ws_path)
    else:
        boot_gen = gui.create_boot_sequence(image_tasks, sync=False, link_all=False) if image_tasks else None

    # --- Elegant Auto-Shutdown ---
    # We append a native generator task that just waits until it is the
    # ONLY task left in the queue, waits 5 frames, and cleanly shuts down DPG.
    def exit_monitor():
        while True:
            if len(gui.tasks) <= 1:
                for _ in range(5):
                    yield
                dpg.stop_dearpygui()
                return
            yield
            
    gui.tasks.append(exit_monitor())

    # Go!
    gui.run(boot_generator=boot_gen)

    t1 = time.perf_counter()
    
    # Output the captured time to stdout so the Master can read it
    print(f"TIME_MS: {(t1 - t0) * 1000.0}")
    sys.exit(0)


# ──────────────────────────────────────────────────────────────────────────────
# The Master Process (Generates files & aggregates results)
# ──────────────────────────────────────────────────────────────────────────────

def master_main(quick=False):
    n_iter = 2 if quick else N_ITER
    n_warmup = 1 if quick else N_WARMUP

    lines = []
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines += [
        "=" * 90,
        "  VVV STARTUP PERFORMANCE BENCHMARK",
        "=" * 90,
        f"  Date      : {now}",
        f"  Platform  : {platform.system()} {platform.release()} ({platform.machine()})",
        f"  Python    : {platform.python_version()}",
        f"  n_warmup  : {n_warmup}   n_iter : {n_iter}",
        "",
        "  Columns: mean ms/boot   (min–max)",
        "  Note: Measures exact time from subprocess spawn to the 5th fully rendered GUI frame.",
    ]

    print("\n".join(lines))

    with tempfile.TemporaryDirectory() as tmpdir:
        print("  [Generating synthetic data for benchmarks. Please wait...]")
        
        # Generate files once to save time across iterations
        make_image(os.path.join(tmpdir, "large.nii"), shape=(128, 512, 512))
        for i in range(4):
            make_image(os.path.join(tmpdir, f"img{i}.nii"), shape=(64, 256, 256))
        make_image(os.path.join(tmpdir, "overlay.nii"), shape=(64, 256, 256))
        roi1 = make_image(os.path.join(tmpdir, "roi1.nii"), shape=(64, 256, 256), is_roi=True)
        roi2 = make_image(os.path.join(tmpdir, "roi2.nii"), shape=(64, 256, 256), is_roi=True)

        # Generate Complex Workspace JSON
        ws = {
            "version": 1.0,
            "viewers": {"V1": {"image_id": "0", "orientation": "AXIAL", "zoom": 1.0, "pan_offset": [0,0]}},
            "images": {
                "0": {
                    "path": os.path.join(tmpdir, "img0.nii"),
                    "sync_group": 1,
                    "display": {"ww": 400.0, "wl": 50.0},
                    "camera": {"zoom": {"AXIAL": 1.0}, "pan": {"AXIAL": [0.0, 0.0]}, "slices": {"AXIAL": 32}, "time_idx": 0, "show_axis": True},
                    "overlay": {"path": os.path.join(tmpdir, "overlay.nii"), "mode": "Registration", "opacity": 0.5, "colormap": "Hot"},
                    "rois": [
                        {"path": roi1, "state": {"name": "ROI1", "color": [255, 0, 0], "opacity": 0.5, "visible": True, "source_mode": "Target FG (val)", "source_val": 1.0}},
                        {"path": roi2, "state": {"name": "ROI2", "color": [0, 255, 0], "opacity": 0.5, "visible": True, "source_mode": "Target FG (val)", "source_val": 1.0, "is_contour": True}}
                    ]
                }
            }
        }
        with open(os.path.join(tmpdir, "ws.vvw"), "w") as f:
            json.dump(ws, f)

        scenarios = [
            (1, "1. Empty Boot (UI Only)"),
            (2, "2. Single Large Image (128x512x512)"),
            (3, "3. Four Images + Sync (64x256x256)"),
            (4, "4. Complex Workspace (Base, Overlay, 2 ROIs)"),
        ]

        print(f"\n  {'Scenario':<46s}  {'mean ms':>8s}   {'(min–max)':>14s}")
        print("  " + "-" * 75)

        for sid, sname in scenarios:
            times = []
            for _ in range(n_warmup + n_iter):
                res = subprocess.run(
                    [sys.executable, __file__, "--worker", "--scenario", str(sid), "--tmpdir", tmpdir],
                    capture_output=True, text=True
                )
                
                if res.returncode != 0:
                    print(f"  [ERROR] Subprocess crashed!\n{res.stderr}")
                    continue
                
                for line in res.stdout.splitlines():
                    if line.startswith("TIME_MS:"):
                        times.append(float(line.split(":")[1].strip()))
                        break
            
            # Exclude warmup
            valid_times = times[n_warmup:]
            if valid_times:
                mean_t, min_t, max_t = np.mean(valid_times), np.min(valid_times), np.max(valid_times)
                print(f"  {sname:<46s}  {mean_t:7.1f} ms   ({min_t:.1f}–{max_t:.1f})")

    print("\n" + "=" * 90)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true", help="Internal flag to run the subprocess scenario")
    parser.add_argument("--scenario", type=int, default=1)
    parser.add_argument("--tmpdir", type=str, default="")
    parser.add_argument("--quick", action="store_true", help="Fewer iterations for a fast sanity check")
    args = parser.parse_args()

    if args.worker:
        worker_main(args.scenario, args.tmpdir)
    else:
        master_main(quick=args.quick)