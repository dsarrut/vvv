1. Current Features
"Straighten on Load": Automatically detects and resamples oblique/tilted images to a pure Identity matrix upon loading, ensuring fast 2D slicing.

Metadata Preservation: Captures the original Direction Matrix before straightening, providing clean UI tags (e.g., "ID", "-1 0 0...") and a full 3x3 copyable tooltip for external scripts.

Extrinsic Rigid Registration: 6-DOF manual transform (Tx, Ty, Tz, Rx, Ry, Rz) applied strictly on top of the straightened physical space.

Dynamic Pivot (CoR): Allows users to snap the Center of Rotation to any crosshair pixel, automatically calculating a compensating translation to prevent visual jumping.

Robust Transform I/O: Reads/writes .tfm, .mat, and .txt files. Automatically applies SVD (Singular Value Decomposition) to correct rounding errors in imported rotation matrices.

Performance Toggles: Uses a 0.3s debouncer for smooth slider dragging

2. Limitations
Quantitative Data Loss on Oblique Load: Because the "Straighten on Load" strategy uses a 3D resampler, it slightly interpolates the raw voxel values of tilted images. For rigorous quantitative tasks, analyzing this interpolated array instead of the raw scanner data could introduce inaccuracies.

Rigid-Only & Manual: The system only supports rigid Euler3DTransform mappings. There is no automated image registration (e.g., Mutual Information) or support for deformable/B-spline transform fields.

Camera Lock: The crosshair and camera are always locked to the orthogonal axes of the base image. There is no "Oblique Slicer" allowing the user to rotate the camera plane itself through the 3D volume.

3. Code Structuration (Main Principles)
The architecture isolates intrinsic scanner data from extrinsic user manipulation:

VolumeData (The Vault): Handles disk I/O, reads metadata, neutralizes the intrinsic scanner orientation (straightening), and stores the immutable baseline pixel array.

SpatialEngine (The Math Layer): Wraps SimpleITK's native TransformContinuousIndexToPhysicalPoint. It manages the extrinsic Euler3DTransform as a pure mathematical overlay.

ViewState (The Visual Bridge): Owns the update_base_display_data methods, triggering the heavy ITK 3D resamplers only when the math needs to be baked into 2D display arrays.

RegistrationUI & Controller: Handles user interactions, debouncing timers, and file parsing.