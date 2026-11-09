"""Dose-rate and time-integrated activity units of a side-car .json, as
radot and OpenGATE write them (issue 53)."""

import json

import numpy as np
import pytest
import SimpleITK as sitk

from vvv.maths.image import VolumeData


@pytest.mark.parametrize(
    "raw, unit",
    [("gy/h", "Gy/h"), ("Gy/s", "Gy/s"), ("mgy/h", "mGy/h"),
     ("bqs", "Bq·s"), ("bqsml", "Bq·s/mL"), ("BqS/mL", "Bq·s/mL")],
)
def test_dose_rate_and_tia_units(tmp_path, raw, unit):
    path = str(tmp_path / "map.nii.gz")
    sitk.WriteImage(sitk.GetImageFromArray(np.zeros((4, 4, 4), np.float32)), path)
    with open(tmp_path / "map.json", "w") as f:
        json.dump({"unit": raw}, f)
    vol = VolumeData(path)
    assert vol.unit == unit
    assert vol.unit_source == "map.json"
