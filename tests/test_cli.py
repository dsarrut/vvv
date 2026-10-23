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
    assert tasks[2 - 1]["base"] == f3


def test_cli_label_rois(dummy_images):
    """Test that '+' syntax correctly parses label map ROIs for base images."""
    f1 = dummy_images("ct.nii.gz", size=(5, 5, 5))
    lbl1 = dummy_images("labels1.nii.gz", size=(5, 5, 5))
    lbl2 = dummy_images("labels2.nii.gz", size=(5, 5, 5))
    f2 = dummy_images("mri.nii.gz", size=(5, 5, 5))

    # Scenario A: Space-separated '+'
    args_a = [f1, "+", lbl1]
    tasks_a = parse_cli_arguments(args_a)
    assert len(tasks_a) == 1
    assert tasks_a[0]["base"] == f1
    assert tasks_a[0]["labels"] == [lbl1]

    # Scenario B: Attached '+' (no spaces)
    args_b = [f"{f1}+{lbl1}"]
    tasks_b = parse_cli_arguments(args_b)
    assert len(tasks_b) == 1
    assert tasks_b[0]["base"] == f1
    assert tasks_b[0]["labels"] == [lbl1]

    # Scenario C: Multiple labels attached to base
    args_c = [f1, "+", lbl1, "+", lbl2, f2]
    tasks_c = parse_cli_arguments(args_c)
    assert len(tasks_c) == 2
    
    assert tasks_c[0]["base"] == f1
    assert tasks_c[0]["labels"] == [lbl1, lbl2]
    
    assert tasks_c[1]["base"] == f2
    assert tasks_c[1]["labels"] == []




def test_cannot_open_reason(dummy_images, tmp_path):
    """Cheap openability check used to avoid starting the UI with nothing to show."""
    import os
    from vvv.cli import cannot_open_reason

    ok = dummy_images("ok.mhd", size=(5, 5, 5))
    assert cannot_open_reason(ok) is None
    assert "no such file" in cannot_open_reason(str(tmp_path / "missing.nii"))

    junk = tmp_path / "junk.nii"
    junk.write_text("not an image")
    assert "not a readable image" in cannot_open_reason(str(junk))

    # Formats vvv reads itself: not rejected because SimpleITK cannot read them
    xdr = tmp_path / "field.xdr"
    xdr.write_bytes(b"# AVS field file\nndim=3\n\x0c\x0c" + b"\x00" * 16)
    assert cannot_open_reason(str(xdr)) is None
    edf = tmp_path / "frame.edf"
    edf.write_bytes(b"{ header }")
    assert cannot_open_reason(str(edf)) is None
    assert cannot_open_reason(str(tmp_path)) is None  # folder (DICOM series)

    # 4D sequence: openable if at least one frame is
    missing = str(tmp_path / "missing.nii")
    assert cannot_open_reason(f"4D: {ok} {missing}") is None
    assert cannot_open_reason(f"4D: {missing} {missing}") is not None

    if os.name != "nt" and os.geteuid() != 0:
        locked = dummy_images("locked.mhd", size=(5, 5, 5))
        os.chmod(locked, 0)
        try:
            assert "permission denied" in cannot_open_reason(locked)
        finally:
            os.chmod(locked, 0o644)


def test_check_inputs_start_only_if_something_opens(dummy_images, tmp_path):
    from vvv.cli import check_inputs

    ok = dummy_images("ok.mhd", size=(5, 5, 5))
    missing = str(tmp_path / "missing.nii")
    assert check_inputs(parse_cli_arguments([ok, missing]), None) is True
    assert check_inputs(parse_cli_arguments([missing]), None) is False
    assert check_inputs(parse_cli_arguments([f"{ok},{missing},hot"]), None) is True
    assert check_inputs([], None) is True  # no argument: empty viewer
    assert check_inputs([], str(tmp_path / "s.vvw")) is False


def test_cli_4d_after_plain_image(dummy_images):
    """A 4D tag after a plain image closes that image first (it was swallowed)."""
    ct = dummy_images("ct.mhd", size=(8, 8, 8))
    f1 = dummy_images("f1.mhd", size=(5, 5, 5))
    f2 = dummy_images("f2.mhd", size=(5, 5, 5))
    tasks = parse_cli_arguments([ct, "4D", f1, f2])
    assert [t["base"] for t in tasks] == [ct, f"4D {f1} {f2}"]


def test_cli_labels_stay_with_their_image(dummy_images):
    """Labels go to the image before the '+', not to any name containing it."""
    ct = dummy_images("ct.mhd", size=(5, 5, 5))
    my_ct = dummy_images("my_ct.mhd", size=(5, 5, 5))
    lab = dummy_images("lab.mhd", size=(5, 5, 5))
    tasks = parse_cli_arguments([ct, "+", lab, my_ct])
    assert [t["labels"] for t in tasks] == [[lab], []]
    # labels after an image of a 4D sequence or an overlay argument
    tasks = parse_cli_arguments([my_ct, f"{ct},{my_ct}", "+", lab])
    assert [t["labels"] for t in tasks] == [[], [lab]]


def test_cli_plus_in_an_existing_file_name(dummy_images):
    a_b = dummy_images("a+b.mhd", size=(5, 5, 5))
    tasks = parse_cli_arguments([a_b])
    assert len(tasks) == 1 and tasks[0]["base"] == a_b and tasks[0]["labels"] == []


def test_cli_bad_fields_warn_and_use_defaults(dummy_images, capsys):
    ct = dummy_images("ct.mhd", size=(5, 5, 5))
    pet = dummy_images("pet.mhd", size=(5, 5, 5))

    (t,) = parse_cli_arguments([f"{ct},{pet},jet,abc,xyz"])  # no crash
    assert t["fusion"]["opacity"] == 0.5 and t["fusion"]["threshold"] is None
    (t,) = parse_cli_arguments([f"{ct},{pet},jet,7"])
    assert t["fusion"]["opacity"] == 1.0  # clamped
    (t,) = parse_cli_arguments([f"{ct},{pet},viridis"])
    assert t["fusion"]["cmap"] == "Jet"  # unknown: default
    (t,) = parse_cli_arguments([f"{ct},{pet},HOT"])
    assert t["fusion"]["cmap"] == "Hot"
    (t,) = parse_cli_arguments([f"{ct},,,,5"])  # base threshold, no colormap
    assert t["base_cmap"] is None and t["min_threshold"] == 5.0
    parse_cli_arguments([f"{ct},,hot,0.3"])  # opacity without an overlay
    parse_cli_arguments([ct, "+"])
    parse_cli_arguments(["+", pet, ct])
    err = capsys.readouterr().err
    for msg in (
        "invalid opacity 'abc'",
        "invalid threshold 'xyz'",
        "opacity 7 out of [0.0, 1.0]",
        "unknown colormap 'viridis'",
        "opacity ignored, there is no overlay",
        "'+' at the end",
        "given before any image",
    ):
        assert msg in err


def test_check_inputs_with_workspaces(dummy_images, tmp_path):
    from vvv.cli import check_inputs

    ct = dummy_images("ct.mhd", size=(5, 5, 5))
    ws = tmp_path / "a.vvw"
    ws.write_text("{}")
    missing_ws = str(tmp_path / "missing.vvw")
    assert check_inputs(parse_cli_arguments([ct]), [missing_ws]) is True  # ct opens
    assert check_inputs([], [missing_ws, str(ws)]) is True
    assert check_inputs([], [missing_ws]) is False
