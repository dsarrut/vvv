
This is VVV, a tentative successor to VV (https://github.com/open-vv)

VVV is a software to view 3D/4D (medical) images.

Goal
- fast
- command line + keyboard driven

Features:
- 3D/4D image slice viewer (most file formats supported, mhd, nii, nrrd, etc.)
- Command line based: `vvv ct.nii.gz`
- Multi-Planar slicing (MPR): instantly switch between Axial, Coronal, and Sagittal orientations (F1, F2, F3)
- Images synchronization, sub-pixel accuracy
- Overlays: crosshairs, tracker, scalebar
- Window/Level control, Colormap, auto-windowing
- Fusion of two images: alpha blending, registration difference, checkerboard
- Basic ROI masks management (load binary mask images)
- Basic DICOM browser
- Session management: save workspaces to file
- History: automatically remembers images last views.


## Installation

```bash
    git clone https://github.com/dsarrut/vvv
    cd vvv
    pip install -e .
```

## Command line

```bash
    vvv ct.nii.gz spect.nii.gz -s    # load the two images, synchronize
    vvv ct.nii.gz, spect.nii.gz, jet  # load two images, fuse them with jet colormapping
    vvv my_session.vvw # restore the session for the file
    
```

## Screenshots

![Alt text](screenshots/ct.png?raw=true "vvv ct.nii.gz")

![Alt text](screenshots/ct_spect.png?raw=true "vvv ct.nii.gz, spect.nii.gz, jet")

![Alt text](screenshots/ct_4d.png?raw=true "vvv ct_4D.mha")

![Alt text](screenshots/rois.png?raw=true "vvv and open ROIs")

![Alt text](screenshots/dicom.png?raw=true "vvv and mini DICOM browser")
