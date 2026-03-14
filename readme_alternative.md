

RadiAnt DICOM Viewer: The gold standard for sheer speed and fluidity on Windows. It is highly optimized, loads massive datasets instantly, and has brilliant multi-planar reconstruction (MPR). However, it is strictly commercial, Windows-only (mostly), GUI-first, and practically ignores non-DICOM research formats (like .nrrd or .mhd).

Horos / OsiriX: The dominant players in the macOS ecosystem. OsiriX is the commercial/FDA-cleared version, while Horos is the open-source fork. They offer a beautiful GUI, robust database management, and great 3D rendering. However, they are heavily tied to Apple, can be slow to launch for a quick file check, and are built around a database paradigm rather than a quick CLI load.

3D Slicer: The absolute powerhouse of open-source medical imaging. Cross-platform and capable of reading almost anything. It is incredible for complex pipelines. The massive downside: it is heavy, slow to boot, and overkill if you just want to check a registration result or look at an overlay.

FSLeyes: Written in Python and OpenGL, this is the default viewer for the FSL neuroimaging suite. It is highly CLI-driven, cross-platform, and handles overlays and syncs beautifully. It is very close in spirit to your project but is heavily tailored toward brain imaging, fMRI timeseries, and the .nii format.

ITK-SNAP: Excellent, lightweight, and cross-platform open-source viewer. Very fast to launch and supports research formats perfectly. However, its entire UI and workflow are heavily optimized strictly for manual and semi-automatic segmentation, making general-purpose multi-image syncing a bit clunky.

| Viewer | Short Description | License | OS | Launch Speed | CLI-Friendly | Primary Formats | Target Workflow |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **RadiAnt** | Highly optimized, fluid MPR, and instant loading. The gold standard for sheer speed, but heavily GUI-reliant. | Commercial | Windows | Instant | Poor | DICOM only | Clinical reading |
| **Horos / OsiriX** | The dominant macOS tools. Beautiful UI and robust local database, but built around import paradigms rather than quick command-line checks. | Commercial / Open Source | macOS | Moderate | Poor | DICOM | Clinical / Research |
| **3D Slicer** | The open-source powerhouse. Reads everything and handles complex pipelines, but is heavy, overkill for simple viewing, and slow to boot. | Open Source | Win/Mac/Linux | Slow | Moderate | Everything | Processing / Pipelines |
| **FSLeyes** | Python/OpenGL viewer for the FSL suite. Excellent CLI and overlay handling, but highly tailored toward neuroimaging and fMRI timeseries. | Open Source | Win/Mac/Linux | Fast | Excellent | NIfTI, DICOM | Neuroimaging |
| **ITK-SNAP** | Lightweight and cross-platform with great ITK support, but the UI is strictly optimized for manual and semi-automatic segmentation tasks. | Open Source | Win/Mac/Linux | Fast | Moderate | Everything (ITK) | Segmentation |
| **vv (Original)** | C++/Qt predecessor. Extremely fast, CLI-first, handles research formats flawlessly, and supports complex overlays and synchronization. | Open Source | Win/Mac/Linux | Instant | Excellent | Everything (ITK) | Fast research viewing |
| **vvv (New)** | Modern Python/DearPyGui successor. Eliminates heavy C++ build steps while maintaining the CLI-first, ultra-fast syncing and fusion workflow. | Open Source | Win/Mac/Linux | Instant | Excellent | Everything (ITK) | Fast research viewing |

Missing Features in vvv (Strictly Viewing/CLI focused). Keeping the strict scope in mind—no processing, no segmentation, no filters, just pure, fast, academic viewing and syncing—here are the most valuable features currently missing:


- 4D / Time-Series Support: Handling a 4th dimension with a time slider. This is critical for dynamic studies, kinetic modeling, and viewing Monte Carlo simulations tracked over time.

- Maximum Intensity Projection (MIP): Rendering thicker slices by projecting the maximum voxel value through a slab. This is a massive quality-of-life feature for visualizing tracers in overlays or checking dose distributions.

- Quick ROI Statistics: Not for exporting segmentations, but simply the ability to hold a key, draw a quick 2D circle or box on the image, and instantly see the Mean, Max, Min, and Standard Deviation inside that region in the tracker text.

- Dose map

- Point-to-Point Measurement: A simple ruler tool (click point A, click point B) that calculates the exact physical distance in millimeters.

- Robust DICOM Directory Loading: SimpleITK can handle single .nii or .mhd files beautifully, but pointing the CLI at a messy directory of 300 DICOM slices and having it automatically parse the series into a clean 3D volume is usually a pain point that requires dedicated logic.

- Multi-Planar Reconstruction (MPR) Off-Axis: The ability to freely rotate the slicing plane to arbitrary oblique angles, rather than being locked strictly to Axial, Sagittal, and Coronal.

- Colorbars / Legends: A visual legend in the UI showing the mapping of the colormap to physical values (especially for overlays like Dosimetry or Registration).