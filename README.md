
This is VVV, a tentative successor to VV.

VVV is a software to view 3D/4D (medical) images.

Goal
- fast
- command line + keyboard driven

Features:
- 3D/4D image slice viewer (most file formats supported, mhd, nii, nrrd, etc.)
- Command line based: `vvv ct.nii.gz`
- Images synchronization, sub-pixel accuracy
- Overlays: crosshairs, tracker, scalebar
- Window/Level control, Colormap, auto-windowing
- Fusion of two images: alpha blending, registration difference, checkerboard
- Basic ROI masks management (load binary mask images)
- Basic DICOM browser


## Installation

```bash
    git clone https://github.com/dsarrut/vvv
    cd vvv
    pip install -e .
```
