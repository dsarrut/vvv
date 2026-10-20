"""Settings/history/workspace JSON is written atomically."""

import json
import os

import numpy as np
import pytest

from vvv.utils import write_json_atomic


def test_writes_and_replaces(tmp_path):
    p = tmp_path / "s.json"
    write_json_atomic(p, {"a": 1})
    write_json_atomic(p, {"a": 2})
    assert json.loads(p.read_text()) == {"a": 2}
    assert os.listdir(tmp_path) == ["s.json"]


def test_failed_write_keeps_previous_file(tmp_path):
    p = tmp_path / "s.json"
    write_json_atomic(p, {"layout": {"window_width": 1600}})
    bad = {"layout": {"window_width": 1800}, "z": np.float32(1.5)}  # not JSON-serialisable
    with pytest.raises(TypeError):
        write_json_atomic(p, bad)
    assert json.loads(p.read_text()) == {"layout": {"window_width": 1600}}
    assert os.listdir(tmp_path) == ["s.json"]  # no temporary file left
