import SimpleITK as sitk
import vtk
from vtk.util.numpy_support import numpy_to_vtk


def create_dummy_image():
    """Create a dummy image if no file is loaded"""
    # Create a simple box
    source = vtk.vtkRTAnalyticSource()
    source.SetWholeExtent(0, 50, 0, 50, 0, 50)
    source.Update()
    return source.GetOutput()


def sitk_to_vtk(sitk_image):

    # 1. Handle 4D images (extract first time point)
    if sitk_image.GetDimension() == 4:
        print("Detected 4D image. Extracting first volume (t=0)...")
        print("NO IMPLEMENTED YET")
        exit(0)
        # Slicing in SITK is (x, y, z, t), so we take all x,y,z at t=0
        size = sitk_image.GetSize()
        sitk_image = sitk.RegionOfInterest(sitk_image,
                                           size=[size[0], size[1], size[2], 1],
                                           index=[0, 0, 0, 0])
        # Collapse the 4th dimension
        sitk_image = sitk.CollapseView(sitk_image)

    # 2. Get Raw Data
    array = sitk.GetArrayFromImage(sitk_image)

    # 3. Setup VTK Image
    vtk_image = vtk.vtkImageData()
    vtk_image.SetOrigin(sitk_image.GetOrigin())
    vtk_image.SetSpacing(sitk_image.GetSpacing())
    vtk_image.SetDimensions(sitk_image.GetSize())

    # 4. Flip Y axis?
    # VTK and SimpleITK have different conventions for the Y axis in memory.
    # For a minimal viewer, we often need to flip it to avoid "mirrored" images.
    # We will skip the flip for now to keep it fast, but be aware of it.

    flat_data = array.flatten()
    vtk_data = numpy_to_vtk(flat_data, deep=True, array_type=vtk.VTK_FLOAT)
    vtk_image.GetPointData().SetScalars(vtk_data)

    return vtk_image
