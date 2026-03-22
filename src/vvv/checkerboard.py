import SimpleITK as sitk
import numpy as np
import click


@click.command()
@click.option('--output', '-o', default='auto', help='Output filename.')
@click.option('--grid_size', '-g', default=5, type=int, help='Number of checks per dimension (e.g. 3 for 3x3x3).')
@click.option('--block_size', '-b', default=1, type=int, help='Size of each block in pixels.')
@click.option('--fg', default=200, type=float, help='Foreground intensity value.')
@click.option('--bg', default=10, type=float, help='Background intensity value.')
@click.option('--spacing', default=3, type=float, help='Spacing between voxels in mm.')
def create_checkerboard(output, grid_size, block_size, fg, bg, spacing):
    """
    Creates a 3D checkerboard image for medical physics testing.
    """
    # 1. Define the total image size
    total_dim = grid_size * block_size
    shape = (total_dim, total_dim, total_dim)

    # 2. Create coordinates grid
    # np.indices gives us the (z, y, x) index for every voxel
    coords = np.indices(shape)

    # 3. Checkerboard logic:
    # Divide index by block_size, sum the results, and check if even/odd
    # (z//b + y//b + x//b) % 2
    checker = (coords[0] // block_size +
               coords[1] // block_size +
               coords[2] // block_size) % 2

    # 4. Map to intensity values
    data = np.where(checker == 0, fg, bg).astype(np.float32)

    # 5. Convert to SimpleITK Image
    # Note: numpy is (z, y, x), SITK is (x, y, z). SITK handles this via GetImageFromArray
    image = sitk.GetImageFromArray(data)
    image.SetSpacing((spacing, spacing, spacing))
    image.SetOrigin((0.0, 0.0, 0.0))

    # Output filename ?
    if output == 'auto':
        output = f'checkerboard_{grid_size}x{grid_size}x{grid_size}.mha'

    # 6. Write to disk
    sitk.WriteImage(image, output)

    click.echo(f"Successfully created {grid_size}^3 checkerboard:")
    click.echo(f"  File: {output}")
    click.echo(f"  Dimensions: {shape}")
    click.echo(f"  Values: FG={fg}, BG={bg}")


if __name__ == '__main__':
    create_checkerboard()