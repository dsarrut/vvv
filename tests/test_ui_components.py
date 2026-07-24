import pytest
from vvv.ui.ui_components import normalize_rgba_to_int


def test_normalize_rgba_to_int_floats():
    assert normalize_rgba_to_int([1.0, 0.5, 0.0, 1.0]) == [255, 127, 0, 255]
    assert normalize_rgba_to_int([0.0, 0.0, 0.0, 1.0]) == [0, 0, 0, 255]


def test_normalize_rgba_to_int_integers():
    assert normalize_rgba_to_int([255, 128, 0, 255]) == [255, 128, 0, 255]
    assert normalize_rgba_to_int([0, 1, 0, 1]) == [0, 1, 0, 1]


def test_normalize_rgba_to_int_rgb_3_channels():
    assert normalize_rgba_to_int([255, 100, 50]) == [255, 100, 50, 255]
    assert normalize_rgba_to_int([1.0, 0.0, 0.0]) == [255, 0, 0, 255]


def test_normalize_rgba_to_int_empty_fallback():
    assert normalize_rgba_to_int([]) == [0, 0, 0, 255]
