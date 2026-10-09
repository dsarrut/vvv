from enum import Enum, auto
import numpy as np
import os
from pathlib import Path


class ViewMode(Enum):
    AXIAL = auto()
    SAGITTAL = auto()
    CORONAL = auto()


class ProfileInteractionMode(Enum):
    IDLE = auto()
    MANIPULATING = auto()


class RoiInteractionMode(Enum):
    IDLE = auto()
    MANIPULATING = auto()


class LandmarkInteractionMode(Enum):
    IDLE = auto()
    MANIPULATING = auto()



def fmt(values, precision=3):
    if isinstance(values, (int, float, np.number)):
        return f"{round(float(values), precision):g}"
    # If it's a 2D matrix (like the ITK direction matrix), flatten it first
    if isinstance(values, np.ndarray):
        items = values.flatten()
    else:
        items = values
    # Round to max precision, then convert to string to remove trailing zeros
    return " ".join([f"{round(float(x), precision):g}" for x in items])


def compute_adaptive_step_and_speed(ww, default_ww=1.0):
    """Computes (step_size, drag_speed, dpg_format) adapted to the intensity range (window width).

    Ensures that for large intensity ranges (e.g. CT: 400 HU), standard ranges (e.g. MRI: 1000),
    and very small ranges (e.g. Dose maps: 0.05 Gy or 2 Gy), the + / - buttons, drag speed,
    and number formatting scale seamlessly without coarse jumps or precision loss.
    """
    try:
        val = float(ww) if ww is not None else float(default_ww)
        if not np.isfinite(val) or val <= 0:
            safe_ww = float(default_ww)
        else:
            safe_ww = val
    except (TypeError, ValueError):
        safe_ww = float(default_ww)

    safe_ww = max(1e-12, safe_ww)
    step_size = safe_ww * 0.02
    drag_speed = safe_ww * 0.005

    if safe_ww >= 100.0:
        dpg_format = "%.1f"
    elif safe_ww >= 10.0:
        dpg_format = "%.2f"
    elif safe_ww >= 1.0:
        dpg_format = "%.3f"
    elif safe_ww >= 0.01:
        dpg_format = "%.4f"
    elif safe_ww >= 0.0001:
        dpg_format = "%.6f"
    else:
        dpg_format = "%.4e"

    return step_size, drag_speed, dpg_format


def format_pixel_value(val, vol, time_idx, dvf_precision=2):
    """Format a pixel/voxel value as a human-readable string.

    Handles scalar, RGB, and DVF volumes. Returns '-' for None values.
    """
    if val is None:
        return "-"
    if getattr(vol, "is_rgb", False):
        return f"{val[0]:g} {val[1]:g} {val[2]:g}"
    if getattr(vol, "is_dvf", False):
        mag = np.linalg.norm(val)
        comps = [
            f"*{v:.{dvf_precision}f}" if i == time_idx else f"{v:.{dvf_precision}f}"
            for i, v in enumerate(val)
        ]
        return f"[{' '.join(comps)}] L:{mag:.{dvf_precision}f}"
    return f"{val:g}"


def slice_to_voxel(slice_x, slice_y, slice_idx, orientation, shape):
    """Converts 2D screen coordinates [0, W] to 3D ITK continuous voxel array [-0.5, W-0.5]."""
    real_h, real_w = shape[0], shape[1]
    cx, cy = slice_x - 0.5, slice_y - 0.5

    if orientation == ViewMode.AXIAL:
        return np.array([cx, cy, float(slice_idx)])
    elif orientation == ViewMode.SAGITTAL:
        return np.array(
            [float(slice_idx), real_w - slice_x - 0.5, real_h - slice_y - 0.5]
        )
    elif orientation == ViewMode.CORONAL:
        return np.array([cx, float(slice_idx), real_h - slice_y - 0.5])
    return np.array([0.0, 0.0, 0.0])


def voxel_to_slice(vx, vy, vz, orientation, shape):
    """Converts 3D continuous voxel [-0.5, W-0.5] to 2D screen coordinates [0, W]."""
    real_h, real_w = shape[0], shape[1]
    if orientation == ViewMode.AXIAL:
        return vx + 0.5, vy + 0.5
    elif orientation == ViewMode.SAGITTAL:
        return real_w - vy - 0.5, real_h - vz - 0.5
    elif orientation == ViewMode.CORONAL:
        return vx + 0.5, real_h - vz - 0.5
    return 0.0, 0.0


def get_history_path_key(file_path):
    """Converts absolute path to ~/ path if it's inside the user's home directory."""
    abs_path = Path(file_path).resolve()
    home = Path.home().resolve()
    try:
        rel_path = abs_path.relative_to(home)
        return "~/" + str(rel_path.as_posix())
    except ValueError:
        return str(abs_path.as_posix())


def resolve_history_path_key(key):
    """Expands ~/ back to absolute path."""
    if key.startswith("~/"):
        return str((Path.home() / key[2:]).resolve())
    return str(Path(key).resolve())


def get_relative_path(target_path, base_dir):
    """Converts an absolute path to a relative path based on the workspace directory."""
    try:
        return os.path.relpath(os.path.abspath(target_path), os.path.abspath(base_dir))
    except ValueError:
        # Fallback for Windows if files are on different drives
        return os.path.abspath(target_path)


def resolve_relative_path(rel_path, base_dir):
    """Converts a relative path back to an absolute path."""
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.normpath(os.path.join(os.path.abspath(base_dir), rel_path))


def get_config_dir() -> Path:
    """Gets the user configuration directory in a cross-platform way."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        workspace_test_config = Path(__file__).resolve().parent.parent.parent / ".pytest_config"
        workspace_test_config.mkdir(exist_ok=True)
        return workspace_test_config

    appdata = os.getenv("APPDATA")
    if os.name == "nt" and appdata:
        return Path(appdata) / "VVV"
    return Path.home() / ".config" / "vvv"


def copy_image_to_clipboard(image) -> bool:
    """Copies a PIL Image to the system clipboard (macOS, Windows, Linux)."""
    import sys
    if sys.platform == "darwin":
        try:
            from Cocoa import NSPasteboard, NSPasteboardTypePNG, NSData
            import io
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            ns_data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
            return bool(pb.setData_forType_(ns_data, NSPasteboardTypePNG))
        except Exception:
            return False
    elif sys.platform == "win32":
        try:
            import io
            import win32clipboard
            buf = io.BytesIO()
            image.convert("RGB").save(buf, "BMP")
            data = buf.getvalue()[14:]  # BMP header offset
            buf.close()
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()
            return True
        except Exception:
            return False
    else:
        # Linux (wl-copy or xclip)
        try:
            import io
            import subprocess
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            for cmd in [["wl-copy", "-t", "image/png"], ["xclip", "-selection", "clipboard", "-t", "image/png"]]:
                try:
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                    proc.communicate(input=png_bytes)
                    if proc.returncode == 0:
                        return True
                except FileNotFoundError:
                    continue
        except Exception:
            pass
        return False


def capture_whole_window():
    """Captures the entire active VVV application window contents."""
    import sys
    import dearpygui.dearpygui as dpg
    from PIL import Image

    if sys.platform == "darwin":
        try:
            import subprocess
            import AppKit
            app = AppKit.NSApplication.sharedApplication()
            target_w = app.keyWindow() or app.mainWindow()
            if target_w is None or not target_w.isVisible():
                for w in app.windows():
                    if w.isVisible() and w.frame().size.width >= 600:
                        target_w = w
                        break
            if target_w:
                wid = target_w.windowNumber()
                tmp_out = f"/tmp/vvw_clip_{wid}_{os.getpid()}.png"
                subprocess.run(["screencapture", "-l", str(wid), "-o", tmp_out])
                if os.path.exists(tmp_out):
                    im = Image.open(tmp_out)
                    frame_rect = target_w.frame()
                    content_rect = target_w.contentRectForFrameRect_(frame_rect)
                    scale = im.size[0] / frame_rect.size.width
                    titlebar_h = int((frame_rect.size.height - content_rect.size.height) * scale)
                    cropped = im.crop((0, titlebar_h, im.size[0], im.size[1]))
                    try:
                        os.remove(tmp_out)
                    except Exception:
                        pass
                    return cropped
        except Exception:
            pass

    # Cross-platform fallback via ImageGrab
    try:
        from PIL import ImageGrab
        vx, vy = dpg.get_viewport_pos()
        vw = dpg.get_viewport_client_width()
        vh = dpg.get_viewport_client_height()
        return ImageGrab.grab(bbox=(vx, vy, vx + vw, vy + vh))
    except Exception:
        return None


