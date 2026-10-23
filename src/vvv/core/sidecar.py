"""Side-car files: small files next to an image that vvv reads and writes with it.

<name>.json next to <name>.<ext> holds the voxel unit ({"unit": "Gy"}) and,
for a label map, the label names and colors ({"1": {"name": ..., "color": ...}});
<name>.tfm (or <name>.mat) holds its registration transform.
"""

import json
import os

from vvv.utils import write_json_atomic

TRANSFORM_EXTENSIONS = (".tfm", ".mat")  # in this order of preference


class SidecarError(Exception):
    """An existing side-car that cannot be read (it is never overwritten)."""


def _stem(image_path):
    """The image path without its extension (.nii.gz, .mha.gz, .mhd...)."""
    p = os.fspath(image_path)
    if p.lower().endswith(".gz"):
        p = p[:-3]
    return os.path.splitext(p)[0]


def sidecar_path(image_path, ext=".json"):
    return _stem(image_path) + ext


def read_sidecar(image_path):
    """(content, path, error): content is None when there is no side-car or it
    cannot be read; error is then the reason (None when there is no file)."""
    path = sidecar_path(image_path)
    if not os.path.isfile(path):
        return None, path, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path, None
    except (OSError, ValueError) as e:
        return None, path, f"{os.path.basename(path)}: {e}"


def update_sidecar(image_path, changes, drop=None):
    """Merge `changes` into the image's json side-car (a None value removes
    the key; `drop(key)` removes more keys first) and write it atomically.
    The other keys are kept. Nothing is created for an empty result.
    Returns the side-car path, or None if no file was written. Raises
    SidecarError if an existing side-car cannot be read (not overwritten)."""
    content, path, error = read_sidecar(image_path)
    if error:
        raise SidecarError(error)
    data = content if isinstance(content, dict) else {}
    if drop:
        data = {k: v for k, v in data.items() if not drop(k)}
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    if not data and not os.path.isfile(path):
        return None
    write_json_atomic(path, data)
    return path


def transform_sidecar_path(image_path):
    """The transform side-car of an image (<name>.tfm, else <name>.mat), or None."""
    stem = _stem(image_path)
    for ext in TRANSFORM_EXTENSIONS:
        if os.path.isfile(stem + ext):
            return stem + ext
    return None
