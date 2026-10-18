"""Window capture, clipboard copy and screenshot files (global screenshot)."""

from pathlib import Path


def save_screenshot_to_file(image) -> Path:
    """Saves a screenshot PIL Image to ~/Pictures or ~/vvv_screenshot_<timestamp>.png."""
    import time
    from pathlib import Path
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    pictures_dir = Path.home() / "Pictures"
    if pictures_dir.is_dir():
        save_path = pictures_dir / f"vvv_screenshot_{timestamp}.png"
    else:
        save_path = Path.home() / f"vvv_screenshot_{timestamp}.png"
    image.save(save_path, format="PNG")
    return save_path


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
            # Note: xclip requires -i (or -in) to read from stdin into selection.
            # wl-copy reads from stdin by default.
            for cmd in [
                ["wl-copy", "--type", "image/png"],
                ["wl-copy", "-t", "image/png"],
                ["xclip", "-selection", "clipboard", "-target", "image/png", "-i"],
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
            ]:
                try:
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
