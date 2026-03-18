#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import click
import SimpleITK as sitk
import numpy as np
from pathlib import Path
import json


@click.command()
@click.argument(
    "input_folder", type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
@click.argument("output_file", type=click.Path())
@click.option(
    "--ext",
    default=".nii.gz",
    help="Extension of the mask files to look for (default: .nii.gz)",
)
@click.option(
    "--tol",
    default=1e-4,
    help="Tolerance for float comparisons like spacing/origin (default: 1e-4)",
)
def merge_masks(input_folder, output_file, ext, tol):
    """
    Merges all binary masks in INPUT_FOLDER into a single label map and saves to OUTPUT_FILE.
    Overlapping pixels are overwritten by the last processed mask.
    """
    input_dir = Path(input_folder)

    # Gather and sort files to ensure deterministic label assignment
    mask_files = sorted(
        [f for f in input_dir.iterdir() if f.is_file() and f.name.endswith(ext)]
    )

    if not mask_files:
        click.secho(f"No files ending with '{ext}' found in {input_folder}.", fg="red")
        return

    click.echo(f"Found {len(mask_files)} masks. Starting merge...")

    # Initialize reference geometry from the first image
    ref_img = sitk.ReadImage(str(mask_files[0]))
    ref_size = ref_img.GetSize()
    ref_spacing = np.array(ref_img.GetSpacing())
    ref_origin = np.array(ref_img.GetOrigin())
    ref_direction = np.array(ref_img.GetDirection())

    # Create an empty numpy array for the final label map (uint16 supports up to 65535 labels)
    # Note: SimpleITK sizes are (x, y, z) but numpy arrays are (z, y, x)
    label_map_np = np.zeros(ref_size[::-1], dtype=np.uint16)

    label_mapping = {}

    for idx, mask_path in enumerate(mask_files):
        current_label = idx + 1
        label_mapping[current_label] = mask_path.name

        mask_img = sitk.ReadImage(str(mask_path))

        # 1. Strict Geometry Validation
        if mask_img.GetSize() != ref_size:
            click.secho(
                f"Abort: Size mismatch in {mask_path.name}. Expected {ref_size}, got {mask_img.GetSize()}",
                fg="red",
            )
            return
        if not np.allclose(mask_img.GetSpacing(), ref_spacing, atol=tol):
            click.secho(f"Abort: Spacing mismatch in {mask_path.name}.", fg="red")
            return
        if not np.allclose(mask_img.GetOrigin(), ref_origin, atol=tol):
            click.secho(f"Abort: Origin mismatch in {mask_path.name}.", fg="red")
            return
        if not np.allclose(mask_img.GetDirection(), ref_direction, atol=tol):
            click.secho(
                f"Abort: Direction matrix mismatch in {mask_path.name}.", fg="red"
            )
            return

        # 2. Extract Data and Check Overlaps
        mask_np = sitk.GetArrayFromImage(mask_img)
        mask_bool = mask_np > 0  # Treat any non-zero value as part of the mask

        overlap_mask = (label_map_np > 0) & mask_bool
        overlap_count = np.count_nonzero(overlap_mask)

        if overlap_count > 0:
            overwritten_labels = np.unique(label_map_np[overlap_mask])
            click.secho(
                f"Warning: '{mask_path.name}' (Label {current_label}) overlaps with existing labels {overwritten_labels.tolist()} "
                f"on {overlap_count} pixels. Overwriting with Label {current_label}.",
                fg="yellow",
            )

        # 3. Apply Label (This inherently overwrites previous values at these coordinates)
        label_map_np[mask_bool] = current_label

    # 4. Save the Output Image
    out_img = sitk.GetImageFromArray(label_map_np)
    out_img.SetSpacing(ref_spacing.tolist())
    out_img.SetOrigin(ref_origin.tolist())
    out_img.SetDirection(ref_direction.tolist())

    sitk.WriteImage(out_img, output_file)
    click.secho(f"\nSuccessfully saved merged label map to {output_file}", fg="green")

    # 5. Save the dictionary map as a sidecar JSON so you know which label is which
    json_path = Path(output_file).with_suffix(".json")
    with open(json_path, "w") as f:
        json.dump(label_mapping, f, indent=4)
    click.secho(f"Saved label mapping dictionary to {json_path}", fg="green")


if __name__ == "__main__":
    merge_masks()
