#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import click
import SimpleITK as sitk


@click.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.argument('output_path', type=click.Path())
@click.option('--size', '-sz', type=float, nargs=3, help='Target size in pixels (x y z)')
@click.option('--spacing', '-sp', type=float, nargs=3, help='Target spacing in mm (x y z)')
@click.option('--interpolator', '-i', type=click.Choice(['linear', 'nearest', 'bspline']),
              default='linear', help='Interpolation method (default: linear)')
def resample(input_path, output_path, size, spacing, interpolator):
    """Resample a 3D image to a specific size or spacing."""

    # Enforce mutual exclusivity
    if size and spacing:
        raise click.UsageError("Please provide either --size or --spacing, not both.")
    if not size and not spacing:
        raise click.UsageError("You must provide either --size or --spacing.")

    # Load image and extract spatial metadata
    image = sitk.ReadImage(input_path)
    original_size = image.GetSize()
    original_spacing = image.GetSpacing()

    # Calculate new geometry to preserve the physical bounding box
    if size:
        new_size = [int(s) for s in size]
        new_spacing = [
            (orig_sz * orig_spc) / n_sz
            for orig_sz, orig_spc, n_sz in zip(original_size, original_spacing, new_size)
        ]
    else:
        new_spacing = spacing
        new_size = [
            int(round((orig_sz * orig_spc) / n_spc))
            for orig_sz, orig_spc, n_spc in zip(original_size, original_spacing, new_spacing)
        ]

    # Map CLI choice to SimpleITK enumerator
    interp_map = {
        'linear': sitk.sitkLinear,
        'nearest': sitk.sitkNearestNeighbor,
        'bspline': sitk.sitkBSpline
    }

    # Configure the Resampler
    resampler = sitk.ResampleImageFilter()
    resampler.SetSize(new_size)
    resampler.SetOutputSpacing(new_spacing)
    resampler.SetOutputOrigin(image.GetOrigin())
    resampler.SetOutputDirection(image.GetDirection())
    resampler.SetInterpolator(interp_map[interpolator])
    resampler.SetDefaultPixelValue(0)

    # Ensure the output maintains the same data type as the input
    resampler.SetOutputPixelType(image.GetPixelID())

    click.echo(f"Resampling: {input_path}")
    click.echo(f"  Old -> Size: {original_size} | Spacing: {[round(s, 3) for s in original_spacing]}")
    click.echo(f"  New -> Size: {tuple(new_size)} | Spacing: {[round(s, 3) for s in new_spacing]}")

    # Execute and save
    resampled_image = resampler.Execute(image)
    sitk.WriteImage(resampled_image, output_path)
    click.echo(f"Saved to: {output_path}")


if __name__ == '__main__':
    resample()