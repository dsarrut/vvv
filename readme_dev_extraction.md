# Extraction Tool

* **Purpose**: Interactively defines a radiometric threshold window, visualizes it, and bakes it into a new mask mask volume.
* **Live Preview**: Temporarily overrides the target image's fusion renderer.
* **Generation Pipeline**:
  * Allocates a blank NumPy array and computes `np.where()` in a background thread to prevent UI lockups.
  * Constant mode outputs binary masks; Original mode captures isolated density data.
