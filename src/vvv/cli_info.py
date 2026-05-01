#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import click
import numpy as np
import SimpleITK as sitk


@click.command()
@click.argument("filepaths", nargs=-1, required=True)
def main(filepaths):
    """Prints metadata information for the provided medical image(s) using only headers."""
    for path in filepaths:
        print(f"--- {path} ---")
        if not os.path.exists(path):
            print("  Error: File not found.\n")
            continue

        try:
            # Read only the header to prevent loading massive arrays into RAM
            reader = sitk.ImageFileReader()
            reader.SetFileName(path)
            reader.ReadImageInformation()

            name = os.path.basename(path)
            pixel_type = sitk.GetPixelIDValueAsString(reader.GetPixelID())
            size = reader.GetSize()
            spacing = reader.GetSpacing()
            origin = reader.GetOrigin()
            direction = reader.GetDirection()
            components = reader.GetNumberOfComponents()

            print(f"  Name:       {name}")
            print(f"  Pixel Type: {pixel_type}")

            size_str = " x ".join(str(x) for x in size)
            if len(size) == 4:
                size_str += " (4D)"
            print(f"  Size:       {size_str}")

            spacing_str = " ".join(f"{x:.4f}" for x in spacing)
            print(f"  Spacing:    {spacing_str}")

            origin_str = " ".join(f"{x:.4f}" for x in origin)
            print(f"  Origin:     {origin_str}")

            if len(direction) >= 9:
                m = np.array(direction[:9]).reshape(3, 3)
                rows = [" ".join(f"{x: .4f}" for x in row) for row in m]
                matrix_str = " ; ".join(rows)
            else:
                matrix_str = " ".join(f"{x: .4f}" for x in direction)
            print(f"  Matrix:     {matrix_str}")

            comp_str = f"{components} component(s)"
            if (
                components in [3, 4]
                and "float" not in pixel_type.lower()
                and "double" not in pixel_type.lower()
            ):
                comp_str += " (RGB/RGBA)"
            elif components > 1:
                comp_str += " (Vector Field / DVF)"
            print(f"  Components: {comp_str}")

            # Calculate memory without loading the image
            dummy_img = sitk.Image(1, 1, reader.GetPixelID())
            bytes_per_pixel = dummy_img.GetSizeOfPixelComponent() * components
            memory_mb = (np.prod(size) * bytes_per_pixel) / (1024 * 1024)
            print(f"  Memory:     {memory_mb:.2f} MB")
            print()
        except Exception as e:
            print(f"  Error reading image header: {e}\n")


if __name__ == "__main__":
    main()
