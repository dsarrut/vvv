import pytest
import numpy as np
import SimpleITK as sitk
from vvv.cli import parse_cli_arguments


@pytest.fixture
def dummy_images(tmp_path):
    """Helper to generate tiny fake medical images on disk for the parser to inspect."""

    def _make_img(name, size, spacing=(1.0, 1.0, 1.0)):
        path = str(tmp_path / name)
        # Size format for numpy is (Z, Y, X)
        img = sitk.GetImageFromArray(
            np.zeros((size[2], size[1], size[0]), dtype=np.uint8)
        )
        img.SetSpacing(spacing)
        sitk.WriteImage(img, path)
        return path

    return _make_img


def test_cli_4d_case_insensitivity(dummy_images):
    """Test that '4D:' and '4d:' both successfully initiate a sequence."""
    f1 = dummy_images("1.mhd", size=(5, 5, 5))
    f2 = dummy_images("2.mhd", size=(5, 5, 5))

    # Test lowercase '4d:'
    tasks_lower = parse_cli_arguments(["4d:", f1, f2])
    assert len(tasks_lower) == 1
    assert tasks_lower[0]["base"] == f"4d: {f1} {f2}"

    # Test uppercase '4D:'
    tasks_upper = parse_cli_arguments(["4D:", f1, f2])
    assert len(tasks_upper) == 1
    assert tasks_upper[0]["base"] == f"4D: {f1} {f2}"


def test_cli_4d_size_mismatch_breaker(dummy_images):
    """
    Test that the parser automatically stops grouping a 4D sequence
    if a file with a different physical size or spacing is encountered.
    """
    # 1. Create two identical images for the 4D sequence
    f1 = dummy_images("t1.mhd", size=(5, 5, 5))
    f2 = dummy_images("t2.mhd", size=(5, 5, 5))

    # 2. Create an image with a completely different size (The Breaker)
    f_diff = dummy_images("ct.mha", size=(10, 10, 10))

    # 3. Create another standard image that comes after
    f_spect = dummy_images("spect.mhd", size=(5, 5, 5))

    # Simulate: vvv 4D: t1.mhd t2.mhd ct.mha spect.mhd
    args = ["4D:", f1, f2, f_diff, f_spect]
    tasks = parse_cli_arguments(args)

    # It should have broken them into 3 distinct loading tasks!
    assert len(tasks) == 3

    # Task 1: The successful 4D group
    assert tasks[0]["base"] == f"4D: {f1} {f2}"

    # Task 2: The mismatched file gets isolated
    assert tasks[1]["base"] == f_diff

    # Task 3: The following file gets isolated
    assert tasks[2]["base"] == f_spect


def test_cli_explicit_4d_splits(dummy_images):
    """Test that placing a second 4D tag forces the first sequence to close."""
    f1 = dummy_images("a1.mhd", size=(5, 5, 5))
    f2 = dummy_images("a2.mhd", size=(5, 5, 5))
    f3 = dummy_images("b1.mhd", size=(5, 5, 5))

    # Simulate: vvv 4D: a1.mhd a2.mhd 4d: b1.mhd
    args = ["4D:", f1, f2, "4d:", f3]
    tasks = parse_cli_arguments(args)

    assert len(tasks) == 2
    assert tasks[0]["base"] == f"4D: {f1} {f2}"
    assert tasks[1]["base"] == f"4d: {f3}"


def test_cli_overlays_and_sync_groups(dummy_images):
    """Test that commas (overlays) and colons (sync groups) are parsed perfectly."""
    base_file = dummy_images("base.mhd", size=(5, 5, 5))
    overlay_file = dummy_images("overlay.mhd", size=(5, 5, 5))

    # Simulate: vvv "1: base.mhd," "overlay.mhd," "Hot," "0.6"
    args = ["1:", f"{base_file},", f"{overlay_file},", "Hot,", "0.6"]
    tasks = parse_cli_arguments(args)

    assert len(tasks) == 1
    task = tasks[0]

    assert task["sync_group"] == 1
    assert task["base"] == base_file
    assert task["fusion"] is not None
    assert task["fusion"]["path"] == overlay_file
    assert task["fusion"]["cmap"] == "Hot"
    assert task["fusion"]["opacity"] == 0.6


def test_cli_explicit_sequence_breaker(dummy_images):
    """Test that explicit symbols like '//' or 'stop:' break a sequence even if sizes match."""
    f1 = dummy_images("1.mhd", size=(5, 5, 5))
    f2 = dummy_images("2.mhd", size=(5, 5, 5))
    f3 = dummy_images("3.mhd", size=(5, 5, 5))  # Same size, but we want it separate

    # Simulate: vvv 4D: 1.mhd 2.mhd // 3.mhd
    args = ["4D:", f1, f2, "//", f3]
    tasks = parse_cli_arguments(args)

    assert len(tasks) == 2
    assert tasks[0]["base"] == f"4D: {f1} {f2}"
    assert tasks[1]["base"] == f3
