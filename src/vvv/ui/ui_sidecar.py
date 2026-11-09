"""Side-car badge: shows that an image (or a label map of ROIs) uses side-car
files (<name>.json: unit, labels; <name>.tfm / .mat: transform), with a small
popup to toggle the transform, open the files and read them again (issue 54).

The pure helpers (badge_state, image_sidecar_lines, json_summary,
roi_label_sidecars, label_sidecar_modified) hold no UI and are tested alone.
"""

import logging
import os
import subprocess
import sys

import dearpygui.dearpygui as dpg

from vvv.ui.ui_components import build_icon_button, build_tooltip

logger = logging.getLogger(__name__)

ICON_SIDECAR = "\uf0c6"  # Paperclip
SIDECAR_COLOR = [110, 180, 255]  # a side-car transform is applied

BADGE_NONE, BADGE_MUTED, BADGE_APPLIED = None, "muted", "applied"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def badge_state(vol, space):
    """None (no side-car), BADGE_MUTED (unit / labels, or a transform side-car
    not applied) or BADGE_APPLIED (a side-car transform is applied). No disk
    access: called every frame."""
    if space is not None and space.from_sidecar and space.is_active and space.transform is not None:
        return BADGE_APPLIED
    if getattr(vol, "sidecar_json_path", None) or (space is not None and space.sidecar_file):
        return BADGE_MUTED
    return BADGE_NONE


def json_summary(path):
    """'unit Bq, 3 labels' for a side-car json (reads the file)."""
    import json

    from vvv.ui.ui_sequences import _parse_label_map_json

    if not path or not os.path.isfile(path):
        return "missing"
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = json.load(f)
    except (OSError, ValueError) as e:
        return f"not read: {e}"
    parts = []
    if isinstance(content, dict) and content.get("unit") is not None:
        parts.append(f"unit {content['unit']}")
    labels, _ = _parse_label_map_json(content)
    if labels:
        parts.append(f"{len(labels)} label{'s' if len(labels) > 1 else ''}")
    return ", ".join(parts) or "no unit nor labels"


def image_sidecar_lines(vol, space):
    """The side-car files of an image, for the popup and the tooltip:
    [{"kind": "json" | "tfm", "path", "text", "applied" (tfm only)}]."""
    lines = []
    json_path = getattr(vol, "sidecar_json_path", None)
    if json_path:
        lines.append({"kind": "json", "path": json_path, "text": json_summary(json_path)})
    if space is not None and space.sidecar_file:
        applied = bool(space.from_sidecar and space.is_active and space.transform is not None)
        if space.from_sidecar and space.transform is not None:
            text = "transform, applied" if applied else "transform, off"
        elif space.transform is not None:
            text = f"transform, not used ({space.transform_file} is loaded)"
        else:
            text = "transform, unloaded"
        lines.append({"kind": "tfm", "path": space.sidecar_file, "text": text, "applied": applied})
    return lines


def tooltip_text(lines):
    body = "\n".join(f"{os.path.basename(l['path'])}: {l['text']}" for l in lines)
    return f"Side-car files\n{body}\nClick: toggle, view / edit or read them again"


def roi_label_sidecars(rois, volumes, source_filter=None):
    """{label map path: json path} for the label-map ROIs listed (all the
    sources, or the one of the source filter) whose file has a side-car json."""
    from vvv.plugins.roi.control_roi import roi_source

    found = {}
    for roi_id, roi in rois.items():
        if getattr(roi, "source_type", None) != "Label Map":
            continue
        vol = volumes.get(roi_id)
        key = roi_source(roi, vol)
        if not key or (source_filter is not None and key != source_filter) or key in found:
            continue
        jsons = [p for p in getattr(vol, "file_paths", None) or [] if str(p).endswith(".json")]
        if jsons and os.path.isfile(jsons[0]):
            found[key] = jsons[0]
    return found


def read_label_sidecar(label_map_path):
    """(names, colors) by label value from the label map's json (reads it)."""
    from vvv.core.sidecar import read_sidecar
    from vvv.ui.ui_sequences import _parse_label_map_json

    content, _, error = read_sidecar(label_map_path)
    if error:
        logger.warning(f"Side-car not read: {error}")
    return _parse_label_map_json(content)


def _label_rois(rois, volumes, label_map_path):
    """(roi id, roi, label value) of the ROIs read from this label map."""
    from vvv.plugins.roi.control_roi import roi_source

    for roi_id, roi in rois.items():
        if getattr(roi, "source_type", None) != "Label Map":
            continue
        if roi_source(roi, volumes.get(roi_id)) != label_map_path:
            continue
        try:
            yield roi_id, roi, int(roi.source_val)
        except (TypeError, ValueError):
            continue


def label_sidecar_modified(rois, volumes, label_map_path, names_colors=None):
    """True if a name or a color of the ROIs of this label map differs from its json."""
    names, colors = names_colors or read_label_sidecar(label_map_path)
    for _, roi, val in _label_rois(rois, volumes, label_map_path):
        if val in names and names[val] != roi.name:
            return True
        if val in colors and list(colors[val][:3]) != [int(c) for c in roi.color[:3]]:
            return True
    return False


def reload_label_names(rois, volumes, label_map_path):
    """Apply the names and colors of the label map's json to its ROIs (the
    masks are not read again). Returns the number of ROIs changed."""
    names, colors = read_label_sidecar(label_map_path)
    changed = 0
    for roi_id, roi, val in _label_rois(rois, volumes, label_map_path):
        before = (roi.name, list(roi.color[:3]))
        if val in names:
            roi.name = names[val]
            vol = volumes.get(roi_id)
            if vol is not None:
                vol.name = roi.name  # as a rename in the ROI list
        if val in colors:
            roi.color = list(colors[val][:3]) + list(roi.color[3:])
        changed += (roi.name, list(roi.color[:3])) != before
    return changed


def open_in_system_editor(path):
    """Open a file with the default application of the system."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        logger.warning("Cannot open %s", path, exc_info=True)
        return False


def load_json_text(path):
    """(text, error): the file's content, pretty-printed when it is valid JSON
    (else as it is, with the reason)."""
    import json

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        return "", str(e)
    try:
        return pretty_json(json.loads(raw)), None
    except ValueError as e:
        return raw, f"not valid JSON: {e}"


def pretty_json(data):
    """Indented JSON, with the lists of numbers (colors) on one line."""
    import json
    import re

    text = json.dumps(data, indent=4, ensure_ascii=False)
    return re.sub(
        r"\[\s*(-?[\d.eE+-]+(?:\s*,\s*-?[\d.eE+-]+)*)\s*\]",
        lambda m: "[" + ", ".join(v.strip() for v in m.group(1).split(",")) + "]",
        text,
    )


def save_json_text(path, text):
    """Write the text if it is valid JSON (atomically: the file is never left
    half-written). Returns None, or the reason it was not written."""
    import json

    import tempfile

    try:
        json.loads(text)
    except ValueError as e:
        return f"not saved, not valid JSON: {e}"
    # The text as typed, written atomically (a temporary file, then replaced)
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".tmp_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else text + "\n")
        os.replace(tmp, path)
    except OSError as e:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        return f"not saved: {e}"
    return None


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def ensure_badge_themes():
    if not dpg.does_item_exist("sidecar_badge_muted_theme"):
        with dpg.theme(tag="sidecar_badge_muted_theme"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [60, 60, 60])
                dpg.add_theme_color(dpg.mvThemeCol_Text, [150, 150, 150])
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)
    if not dpg.does_item_exist("sidecar_badge_applied_theme"):
        with dpg.theme(tag="sidecar_badge_applied_theme"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [60, 60, 60])
                dpg.add_theme_color(dpg.mvThemeCol_Text, SIDECAR_COLOR)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)


JSON_WINDOW = "sidecar_json_window"


def open_json_window(gui, path, on_saved=None):
    """A small JSON viewer / editor in vvv: the file's text, Save (checked to be
    valid JSON first), Reload, and the system editor. on_saved() runs after a
    save (e.g. to read the unit or the label names again)."""
    if dpg.does_item_exist(JSON_WINDOW):
        dpg.delete_item(JSON_WINDOW)
    text, error = load_json_text(path)
    try:
        vw, vh = dpg.get_viewport_client_width(), dpg.get_viewport_client_height()
    except Exception:
        vw, vh = 1280, 800
    w, h = 520, min(520, max(300, vh - 120))
    status, box = f"{JSON_WINDOW}_status", f"{JSON_WINDOW}_text"

    def set_status(msg, ok):
        dpg.set_value(status, msg)
        dpg.configure_item(status, color=[150, 255, 150] if ok else [255, 100, 100])

    def on_save():
        err = save_json_text(path, dpg.get_value(box))
        if err:
            set_status(err, False)
            return
        set_status("Saved", True)
        if on_saved:
            on_saved()

    def on_reload():
        t, e = load_json_text(path)
        dpg.set_value(box, t)
        set_status(e or "Read again", e is None)

    with dpg.window(
        tag=JSON_WINDOW,
        label=os.path.basename(path),
        width=w,
        height=h,
        pos=[max(0, (vw - w) // 2), max(0, (vh - h) // 2)],
        no_collapse=True,
        on_close=lambda: dpg.delete_item(JSON_WINDOW),
    ):
        dpg.add_text(path, color=[140, 140, 140], wrap=w - 20)
        dpg.add_input_text(tag=box, default_value=text, multiline=True, tab_input=True, width=-1, height=-34)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Save", callback=on_save)
            dpg.add_button(label="Reload", callback=on_reload)
            build_icon_button(
                icon="\uf35d",  # up-right from square: open outside
                callback=lambda: open_in_system_editor(path),
                tooltip="Open in the system editor",
                gui=gui,
            )
            dpg.add_text("", tag=status)
    if error:
        set_status(error, False)


def _theme_for(state):
    return "sidecar_badge_applied_theme" if state == BADGE_APPLIED else "sidecar_badge_muted_theme"


def build_image_badge(gui, vs_id):
    """The badge of an image in the image list (hidden without side-car);
    sync_image_badge keeps it up to date every frame."""
    ensure_badge_themes()
    tag = f"btn_sidecar_{vs_id}"
    build_icon_button(
        icon=ICON_SIDECAR,
        tag=tag,
        callback=lambda s, a, u: open_image_popup(gui, u),
        user_data=vs_id,
        theme=None,
        show=False,
    )
    with dpg.tooltip(tag):
        dpg.add_text("", tag=f"text_sidecar_tip_{vs_id}")
    _badge_keys(gui).pop(vs_id, None)
    sync_image_badge(gui, vs_id)


def _badge_keys(gui):
    """Last shown state of each badge (the badge is updated on a change only)."""
    if not hasattr(gui, "_sidecar_badge_keys"):
        gui._sidecar_badge_keys = {}
    return gui._sidecar_badge_keys


def _badge_key(vol, space):
    return (
        getattr(vol, "sidecar_json_path", None),
        getattr(vol, "unit", None),
        space.sidecar_file,
        space.from_sidecar,
        bool(space.is_active),
        space.transform is not None,
        space.transform_file,
    )


def sync_image_badge(gui, vs_id):
    """Every frame: show / color the badge when the image's side-car state changed."""
    tag = f"btn_sidecar_{vs_id}"
    vs = gui.controller.view_states.get(vs_id)
    if vs is None or not dpg.does_item_exist(tag):
        return
    key = _badge_key(vs.volume, vs.space)
    keys = _badge_keys(gui)
    if keys.get(vs_id) == key:
        return
    keys[vs_id] = key
    state = badge_state(vs.volume, vs.space)
    dpg.configure_item(tag, show=state is not None)
    if state is not None:
        dpg.bind_item_theme(tag, _theme_for(state))
        tip = f"text_sidecar_tip_{vs_id}"
        if dpg.does_item_exist(tip):
            dpg.set_value(tip, tooltip_text(image_sidecar_lines(vs.volume, vs.space)))


def _popup_window(tag):
    if dpg.does_item_exist(tag):
        dpg.delete_item(tag)
    x, y = dpg.get_mouse_pos(local=False)
    return dpg.window(
        tag=tag, popup=True, autosize=True, no_title_bar=True, pos=[int(x), int(y)]
    )


def _file_label(path, line_text, width_chars=18):
    name = os.path.basename(path)
    t = dpg.add_text(name.ljust(width_chars))
    build_tooltip_text(t, path)
    dpg.add_text(line_text, color=[150, 150, 150])


def build_tooltip_text(item, text):
    with dpg.tooltip(item):
        dpg.add_text(text)


def open_image_popup(gui, vs_id):
    """The side-car files of the image: toggle the transform, open the file in
    the system editor, read it again."""
    c = gui.controller
    vs = c.view_states.get(vs_id)
    if vs is None:
        return
    lines = image_sidecar_lines(vs.volume, vs.space)
    tag = "sidecar_popup"
    with _popup_window(tag):
        for line in lines:
            with dpg.group(horizontal=True):
                if line["kind"] == "tfm":
                    cb = dpg.add_checkbox(
                        default_value=line["applied"],
                        callback=lambda s, a, u: _on_toggle_transform(gui, u, a),
                        user_data=vs_id,
                    )
                    build_tooltip_text(
                        cb,
                        "Apply the side-car transform (off: the image as read from disk;\n"
                        "the transform is kept)",
                    )
                else:
                    dpg.add_spacer(width=19)  # aligned with the checkbox of the transform
                _file_label(line["path"], line["text"])
                if line["kind"] == "tfm":
                    build_icon_button(
                        icon="\uf044",  # pen to square: edit
                        callback=lambda s, a, u: _on_edit_transform(gui, u),
                        user_data=vs_id,
                        tooltip="Edit in the Transform panel",
                        gui=gui,
                    )
                else:
                    build_icon_button(
                        icon="\uf044",  # pen to square: view / edit
                        callback=lambda s, a, u: _on_open_json(gui, *u),
                        user_data=(vs_id, line["path"]),
                        tooltip="View / edit the file",
                        gui=gui,
                    )
                build_icon_button(
                    icon="\uf01e",
                    callback=lambda s, a, u: _on_reread(gui, *u),
                    user_data=(vs_id, line["kind"]),
                    tooltip="Read the file again (after an edit outside vvv)",
                    gui=gui,
                )


def _close_popup():
    if dpg.does_item_exist("sidecar_popup"):
        dpg.configure_item("sidecar_popup", show=False)


def _on_toggle_transform(gui, vs_id, active):
    gui.controller.set_transform_active(vs_id, bool(active))
    _close_popup()


def _on_open_json(gui, vs_id, path):
    """The image's json in the JSON window; a save reads the unit again."""
    _close_popup()
    open_json_window(gui, path, on_saved=lambda: _on_reread(gui, vs_id, "json"))


def _on_edit_transform(gui, vs_id):
    """The Transform (registration) panel, on this image."""
    _close_popup()
    c = gui.controller
    viewer = next((v for v in c.viewers.values() if v.image_id == vs_id), None)
    if viewer is not None:
        gui.set_context_viewer(viewer)
    tab = "registration_plugin"
    if dpg.does_item_exist(tab):
        gui.on_nav_clicked(f"nav_btn_{tab}", None, tab)


def _on_reread(gui, vs_id, kind):
    """Read a side-car again: the unit (and labels) of the json, the transform."""
    c = gui.controller
    vol, vs = c.volumes.get(vs_id), c.view_states.get(vs_id)
    if vol is None or vs is None:
        return
    _close_popup()
    if kind == "tfm":
        was_active = vs.space.is_active or not vs.space.from_sidecar
        if c.apply_transform_sidecar(vs_id) and not was_active:
            c.set_transform_active(vs_id, False)  # read again, kept off
    else:
        vol._detect_unit_and_source()
        c.ui_needs_refresh = True
        for v in c.viewers.values():
            if v.image_id == vs_id:
                v.is_geometry_dirty = True
        c._set_status(f"Read again: {os.path.basename(vol.sidecar_json_path or '')} (unit {vol.unit or '?'})")
