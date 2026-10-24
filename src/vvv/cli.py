#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Any
import os
import re
import sys
import click
from vvv.ui.gui import MainGUI
import dearpygui.dearpygui as dpg
from vvv.ui.viewer import SliceViewer
from vvv.maths.image import VolumeData
from vvv.core.controller import Controller
from vvv.utils import get_resource_path
from vvv.config import COLORMAPS, DEFAULT_SETTINGS
from vvv.ui.ui_screen import main_screen_size, start_window_geometry
import logging

logger = logging.getLogger(__name__)


def setup_logging(debug=False):
    """Messages of the vvv modules go to stderr: warnings and errors, plus
    debug details with --debug. Other libraries (numba...) are not affected."""
    vvv_logger = logging.getLogger("vvv")
    if not vvv_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("vvv %(levelname)s: %(message)s"))
        vvv_logger.addHandler(handler)
    vvv_logger.setLevel(logging.DEBUG if debug else logging.WARNING)
    vvv_logger.propagate = False


def set_macos_dock_info(name, icon_path=None):
    """Promotes script, sets focus, icon, process name, and fixes Cmd+Q."""
    if sys.platform != "darwin":
        return

    try:
        import setproctitle

        setproctitle.setproctitle(name)
    except ImportError:
        pass

    try:
        from Cocoa import (  # type: ignore
            NSApplication,  # type: ignore
            NSImage,  # type: ignore
            NSApplicationActivationPolicyRegular,  # type: ignore
            NSMenu,  # type: ignore
            NSMenuItem,  # type: ignore
        )

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)

        main_menu = NSMenu.alloc().init()
        app.setMainMenu_(main_menu)

        app_menu_item = NSMenuItem.alloc().init()
        main_menu.addItem_(app_menu_item)

        app_menu = NSMenu.alloc().init()
        app_menu_item.setSubmenu_(app_menu)

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Quit {name}", "terminate:", "q"
        )
        app_menu.addItem_(quit_item)

        if icon_path and os.path.exists(icon_path):
            image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
            app.setApplicationIconImage_(image)

    except ImportError:
        pass


def _warn(msg):
    print(f"vvv: {msg}", file=sys.stderr)


def _parse_number(text, what, default, lo=None, hi=None):
    """A number field of an overlay argument; a bad value is reported and
    replaced by the default, a value out of [lo, hi] is clamped."""
    if text == "":
        return default
    try:
        v = float(text)
    except ValueError:
        _warn(f"invalid {what} '{text}', using {default}")
        return default
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        clamped = min(max(v, lo), hi)
        _warn(f"{what} {text} out of [{lo}, {hi}], using {clamped:g}")
        return clamped
    return v


def _parse_colormap(text, default):
    """Colormap name, any case; an unknown one is reported and gets the default."""
    by_lower = {name.lower(): name for name in COLORMAPS}
    name = by_lower.get(text.lower())
    if name is None:
        _warn(
            f"unknown colormap '{text}', using {default} "
            f"(known: {', '.join(n.lower() for n in COLORMAPS)})"
        )
        return default
    return name


# ',' and '+' inside an existing file name are not separators: they are
# replaced by these (never in a path) while parsing, then restored
_IN_NAME = {",": "\x00", "+": "\x01"}


def _protect_names(arg):
    """Hide the ',' / '+' of the existing files named in an argument: the
    longest run of pieces that is an existing path is one name."""
    sync = re.match(r"^\d+:", arg)
    prefix = sync.group(0) if sync else ""
    toks = re.split(r"([,+])", arg[len(prefix):])
    texts, seps = toks[0::2], toks[1::2]

    def join(i, k, protect=False):
        out = texts[i]
        for m in range(i, k - 1):
            out += (_IN_NAME[seps[m]] if protect else seps[m]) + texts[m + 1]
        return out

    out, i = prefix, 0
    while i < len(texts):
        j = next(
            (k for k in range(len(texts), i + 1, -1) if os.path.exists(join(i, k))),
            i + 1,
        )
        out += join(i, j, protect=True)
        if j - 1 < len(seps):
            out += seps[j - 1]
        i = j
    return out


def _restore_names(text):
    for sep, mark in _IN_NAME.items():
        text = text.replace(mark, sep)
    return text


def parse_cli_arguments(datasets):
    """
    Parses raw command line arguments into structured image tasks.
    Handles shell-expanded 4D sequences, sync groups, and comma-separated fusion parameters.
    Automatically breaks 4D sequences if image size/spacing changes.
    Supports '+' prefix or separator to attach label map ROIs to base images.
    """
    import numpy as np

    # 1. Normalize datasets by splitting any tokens containing '+'
    #    (not the '+' / ',' inside an existing file name)
    normalized_datasets = []
    for item in map(_protect_names, datasets):
        if item == "+":
            normalized_datasets.append("+")
        elif "+" in item:
            parts = item.split("+")
            for i, part in enumerate(parts):
                if i > 0:
                    normalized_datasets.append("+")
                if part:
                    normalized_datasets.append(part)
        else:
            normalized_datasets.append(item)

    # 2. Extract label maps: they belong to the argument just before the '+'
    clean_datasets = []  # [item, its label paths]
    expect_label = False

    for item in normalized_datasets:
        if item == "+":
            expect_label = True
            continue

        if expect_label:
            if clean_datasets:
                clean_datasets[-1][1].append(item)
            else:
                _warn(f"labels {_restore_names(item)} given before any image, ignored")
            expect_label = False
        else:
            clean_datasets.append([item, []])
    if expect_label:
        _warn("'+' at the end with no label file after it, ignored")

    def get_info(path):
        """Ultra-fast header peek without loading pixel data."""
        import SimpleITK as sitk  # lazy: an empty start does not need it

        try:
            reader = sitk.ImageFileReader()
            reader.SetFileName(path)
            reader.ReadImageInformation()
            return reader.GetSize(), reader.GetSpacing()
        except Exception:
            return None, None

    grouped_datasets = []  # (composite string, label paths)
    buf = []
    buf_labels = []
    in_4d = False
    ref_size = None
    ref_spacing = None

    def flush():
        nonlocal buf, buf_labels, in_4d, ref_size, ref_spacing
        if buf:
            grouped_datasets.append((" ".join(buf), buf_labels))
            buf = []
            buf_labels = []
        in_4d = False
        ref_size = None
        ref_spacing = None

    def add(item, item_labels):
        buf.append(item)
        buf_labels.extend(item_labels)

    # 3. Re-group shell-split arguments dynamically
    seq_prefixes = VolumeData.SEQUENCE_PREFIXES
    for item, item_labels in clean_datasets:
        is_4d_tag = item.upper() in seq_prefixes
        clean_item = _restore_names(item.rstrip(",:"))

        expecting_more = len(buf) > 0 and (
            buf[-1].endswith(",")
            or (buf[-1].endswith(":") and not buf[-1].upper().startswith(seq_prefixes))
        )

        if item.lower() in ("//", "::", "stop:", "end:"):
            flush()
            continue

        if is_4d_tag:
            if buf and not expecting_more:
                flush()  # also a plain image before the tag
            in_4d = True
            add(item, item_labels)
            continue

        if in_4d and not expecting_more:
            if os.path.isfile(clean_item):
                size, spacing = get_info(clean_item)
                if size is not None:
                    if ref_size is None:
                        ref_size = size
                        ref_spacing = spacing
                        add(item, item_labels)
                    else:
                        if size == ref_size and spacing is not None and ref_spacing is not None and np.allclose(
                            spacing, ref_spacing, atol=1e-3
                        ):
                            add(item, item_labels)
                        else:
                            flush()
                            add(item, item_labels)
                else:
                    add(item, item_labels)
            else:
                add(item, item_labels)
        else:
            if not expecting_more and len(buf) > 0:
                flush()
            add(item, item_labels)

    flush()

    # 4. Parse the composite strings into tasks
    image_tasks = []

    for ds, ds_labels in grouped_datasets:
        parts = [p.strip() for p in ds.split(",")]
        base_part = parts[0]
        sync_group = 0

        match = re.match(r"^(\d+):\s*(.*)$", base_part)
        if match:
            sync_group = int(match.group(1))
            base_part = match.group(2)

        task: dict[str, Any] = {
            "base": _restore_names(base_part),
            "fusion": None,
            "sync_group": sync_group,
            "base_cmap": None,
            "labels": [_restore_names(lbl) for lbl in ds_labels],
        }
        ds = _restore_names(ds)  # for the messages

        if len(parts) > 1:
            overlay_path = parts[1].strip()
            cmap_input = parts[2].strip() if len(parts) > 2 else ""
            mode = "Alpha"

            if cmap_input.lower() in ["reg", "registration"]:
                cmap = "Grayscale"
                mode = "Registration"
            elif cmap_input:
                cmap = _parse_colormap(cmap_input, "Jet" if overlay_path else None)
            else:
                cmap = "Jet" if overlay_path else None
            opacity_text = parts[3] if len(parts) > 3 else ""
            threshold_text = parts[4] if len(parts) > 4 else ""
            if len(parts) > 5:
                _warn(f"{ds}: extra fields after the threshold ignored")

            if overlay_path:
                task["fusion"] = {
                    "path": _restore_names(overlay_path),
                    "cmap": cmap,
                    "mode": mode,
                    "opacity": _parse_number(opacity_text, "opacity", 0.5, 0.0, 1.0),
                    "threshold": _parse_number(threshold_text, "threshold", None),
                }
            else:
                task["base_cmap"] = cmap
                if opacity_text:
                    _warn(f"{ds}: opacity ignored, there is no overlay")
                thr = _parse_number(threshold_text, "threshold", None)
                if thr is not None:
                    task["min_threshold"] = thr

        image_tasks.append(task)

    return image_tasks


# Formats vvv reads itself (no SimpleITK header to probe)
_OWN_READER_EXTS = (".edf", ".hst", ".cbf", ".his")


def _input_files(spec):
    """Files/folders an image argument refers to (4D sequences may list several)."""
    s = spec.strip()
    if s.upper().startswith(VolumeData.SEQUENCE_PREFIXES):
        rest = s[3:].strip()  # same prefix stripping as VolumeData
        if os.path.isdir(rest):
            return [rest]
        if "*" in rest or "?" in rest:
            import glob

            return sorted(glob.glob(rest))
        import shlex

        return shlex.split(rest.replace("\\", "\\\\") if os.name == "nt" else rest)
    return [s]


def cannot_open_reason(spec):
    """Why an image argument cannot be opened, or None if it looks openable.

    Cheap (never reads pixel data) and mirrors VolumeData's reader routing: a
    SimpleITK-readable header, a format vvv reads itself, an AVS/XDR file, or a
    folder (DICOM series). A sequence is openable if one of its files is.
    """
    import SimpleITK as sitk

    reasons = []
    for path in _input_files(spec) or [spec]:
        if not os.path.exists(path):
            reasons.append(f"{path}: no such file or directory")
            continue
        if not os.access(path, os.R_OK):
            reasons.append(f"{path}: permission denied")
            continue
        if os.path.isdir(path) or path.lower().endswith(_OWN_READER_EXTS):
            return None
        try:
            reader = sitk.ImageFileReader()
            reader.SetFileName(path)
            reader.ReadImageInformation()
            return None
        except Exception:
            pass
        try:
            with open(path, "rb") as f:
                if b"\x0c\x0c" in f.read(4096):  # AVS/XDR header delimiter
                    return None
        except OSError:
            pass
        reasons.append(f"{path}: not a readable image")
    return "; ".join(reasons)


def check_inputs(image_tasks, workspace_files=()):
    """Print what cannot be opened; return False if nothing given can be opened."""
    workspace_files = list(workspace_files or [])
    n_ok = 0
    for ws in workspace_files:
        if os.path.isfile(ws):
            n_ok += 1
        else:
            print(f"vvv: cannot open workspace {ws}", file=sys.stderr)
    for task in image_tasks:
        reason = cannot_open_reason(task["base"])
        if reason:
            print(f"vvv: cannot open {reason}", file=sys.stderr)
        else:
            n_ok += 1
        extra = ([task["fusion"]["path"]] if task.get("fusion") else []) + task.get("labels", [])
        for path in extra:
            reason = cannot_open_reason(path)
            if reason:
                print(f"vvv: cannot open {reason}", file=sys.stderr)
    return n_ok > 0 or not (image_tasks or workspace_files)


def run_screenshots(workspace_files, image_tasks, shots_path):
    """vvv session.vvw --screenshots shots.json: the exit status (0: all saved)."""
    if len(workspace_files) != 1 or image_tasks:
        _warn("--screenshots needs exactly one workspace (.vvw) and no other file")
        return 2
    for path, what in ((workspace_files[0], "workspace"), (shots_path, "screenshot list")):
        if not os.path.isfile(path):
            _warn(f"cannot open {what} {path}")
            return 2
    from vvv.screenshot import vvv_screenshot

    try:
        failures = vvv_screenshot(workspace_files[0], shots_path)
    except (ValueError, OSError) as e:  # an invalid screenshot list
        _warn(f"{shots_path}: {e}")
        return 2
    if failures:
        _warn(f"{failures} screenshot(s) not saved")
    return 1 if failures else 0


def boot_sequence(gui, image_tasks, workspace_files, sync=False, link_wl=False):
    """Images first, then each workspace in order: the last one takes precedence
    (layout, active viewer, Save / Reload target), the others keep their images."""
    if image_tasks:
        yield from gui.create_boot_sequence(image_tasks, sync, False, link_wl)
    for ws in workspace_files:
        yield from gui.load_workspace_sequence(ws)


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.argument("datasets", nargs=-1)
# --linkall is kept as a legacy alias from the old `vv` application; --sync is the preferred form.
@click.option("--linkall", "-l", is_flag=True, help="Enable spatial sync for all images (legacy alias for --sync)")
@click.option("--sync", "-s", is_flag=True, help="Enable spatial sync for all images at startup")
@click.option("--linkall-wl", "-lw", is_flag=True, help="Enable Window/Level sync for all images at startup")
@click.option(
    "--no-history",
    "-nh",
    is_flag=True,
    help="Ignore saved history and load with defaults.",
)
@click.option("--debug", is_flag=True, help="Show FPS debug overlay with graph, print debug messages, raise on internal errors.")
@click.option("--fast-gl/--no-fast-gl", default=True, help="Enable/disable fast GL nearest-neighbor (Linux/Windows).")
@click.option(
    "--screenshots",
    "screenshots",
    metavar="SHOTS.json",
    default=None,
    help="With one workspace: save the PNG screenshots listed in SHOTS.json, then exit.",
)
def main(no_history, datasets, linkall, sync, linkall_wl, debug, fast_gl, screenshots):
    """VVV — multi-image medical viewer.

    \b
    BASIC USAGE
      vvv image.mhd
      vvv ct.mhd spect.nii dose.nii        load multiple images side by side

    \b
    OVERLAY SYNTAX  (comma-separated fields, attached to the base image)
      vvv base.nii,overlay.nii             alpha overlay, Jet colormap, opacity 0.5
      vvv base.nii,overlay.nii,hot         colormaps: grayscale hot cold jet dosimetry segmentation
      vvv base.nii,overlay.nii,jet,0.7     custom opacity (0.0–1.0)
      vvv base.nii,overlay.nii,jet,0.5,100 minimum display threshold on the overlay
      vvv base.nii,overlay.nii,reg         registration mode: linked W/L, grayscale colormaps
      vvv base.nii,,hot                    apply colormap to base image only (empty overlay slot)

    \b
    SYNC GROUPS
      vvv 1:ct.mhd 1:spect.nii            assign images to spatial sync group 1 (pan/zoom/slice)
      vvv 1:ct.mhd 2:mri.nii              two separate sync groups
      vvv ct.mhd spect.nii --sync          link all images spatially at startup
      vvv ct.mhd spect.nii --linkall-wl    link all images by Window/Level at startup
      vvv ct.mhd spect.nii -s -lw          link both spatial and W/L at startup

    \b
    4D SEQUENCES
      vvv 4D frame1.nii frame2.nii ...    explicit 4D stack (use // to end the sequence)
      vvv 4D frame*.nii                    shell glob: the sequence stops at a size/spacing change

    \b
    LABEL MAPS / ROIs
      vvv ct.nii.gz + labels.nii.gz        load labels.nii.gz as ROIs on ct.nii.gz

    \b
    WORKSPACE
      vvv session.vvw --screenshots shots.json
                                           save the PNG screenshots of shots.json, then exit
      vvv session.vvw                      restore a previously saved workspace
      vvv ct.nii a.vvw b.vvw               images first, then each workspace in order;
                                           the last one sets the layout (and is the one
                                           Save / Reload act on)
    """

    setup_logging(debug)

    # Check dearpygui version compatibility
    try:
        import dearpygui
        dpg_ver = dearpygui.__version__
        parts = [int(p) for p in dpg_ver.split(".") if p.isdigit()]
        if parts and (parts[0] < 2 or (parts[0] == 2 and len(parts) > 1 and parts[1] < 3)):
            logger.warning(
                f"dearpygui version {dpg_ver} is detected. Version >= 2.3.1 is highly recommended "
                f"to prevent segmentation faults/crashes, particularly under Python 3.14+ or in headless environments.",
            )
    except Exception:
        pass

    # Parse the tasks cleanly: workspaces apart, the images are parsed together
    datasets = [ds for ds in datasets if ds.strip()]
    workspace_files = [f for f in datasets if f.lower().endswith(".vvw")]
    image_tasks = parse_cli_arguments(
        [f for f in datasets if not f.lower().endswith(".vvw")]
    )

    if screenshots:
        sys.exit(run_screenshots(workspace_files, image_tasks, screenshots))

    # Do not open a window if none of the given images can be opened
    if not check_inputs(image_tasks, workspace_files):
        print("vvv: nothing to open, not starting the viewer.", file=sys.stderr)
        sys.exit(1)

    import vvv.ui.render_strategy as rs_mod
    if fast_gl:
        import platform as _platform
        rs_mod.GL_NEAREST_SUPPORTED = _platform.system() in ("Linux", "Windows")
    else:
        rs_mod.GL_NEAREST_SUPPORTED = False

    # Warn if numba isn't available. On platforms without HW GL_NEAREST
    # (macOS, or --no-fast-gl), fusion overlay rendering depends on numba's
    # JIT kernel for reasonable performance — the pure-NumPy fallback measured
    # ~40-50x slower in profiling, and silently falling back to it is easy to
    # miss (it produces correct but very slow results, not an error).
    # find_spec only checks it is installed: importing numba costs ~150 ms at
    # every start, it is imported on first use (fusion / MIP render).
    if not rs_mod.GL_NEAREST_SUPPORTED:
        import importlib.util

        if importlib.util.find_spec("numba") is None:
            logger.warning(
                "numba is not installed/importable in this environment. "
                "Fusion overlay rendering will fall back to a much slower pure-NumPy "
                "path (~40-50x slower). Install numba for smooth fusion rendering.",
            )

    # --- Setup Application ---
    icon_png = get_resource_path(os.path.join("icons", "py_vv.png"))
    icon_ico = get_resource_path(os.path.join("icons", "py_vv.ico"))
    set_macos_dock_info("VVV", icon_path=icon_png)

    dpg.create_context()
    controller = Controller()

    controller.use_history = not no_history

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui
    layout = controller.settings.data["layout"]
    default = DEFAULT_SETTINGS["layout"]
    win_w, win_h, win_x, win_y = start_window_geometry(
        layout["window_width"],
        layout["window_height"],
        (default["window_width"], default["window_height"]),
        main_screen_size(),
    )
    pos = {"x_pos": win_x, "y_pos": win_y} if win_x is not None else {}
    dpg.create_viewport(title="VVV", width=win_w, height=win_h, **pos)

    active_icon = icon_ico if sys.platform == "win32" else icon_png
    dpg.set_viewport_small_icon(active_icon)
    dpg.set_viewport_large_icon(active_icon)

    workspace_files = [f for f in workspace_files if os.path.isfile(f)]
    boot_gen = boot_sequence(
        gui, image_tasks, workspace_files, sync or linkall, linkall_wl
    )
    gui.run(boot_generator=boot_gen, debug=debug)


if __name__ == "__main__":
    main()
