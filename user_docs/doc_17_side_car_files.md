# Side-Car Files

A side-car file sits next to an image and has the same name, with another extension. VVV reads it when it loads the image and writes it when you save. It keeps what the image file format cannot hold: the voxel unit, the names and colors of the labels of a label map, and the registration transform.

---

## Which Files

| File (for `ct.nii.gz`) | Holds | Read | Written |
| :--- | :--- | :--- | :--- |
| `ct.json` | the voxel unit (`"unit"`) | when the image is loaded | when the image is saved, or with the save icon next to an edited unit |
| `labels.json` (for a label map `labels.nii.gz`) | the label names and colors | when the label map is loaded as ROIs | when ROIs are saved as one multi-label image |
| `ct.tfm`, else `ct.mat` | the registration transform | when the image is loaded: the transform is applied | **Save** / **Save As** in the Transform panel (Save As proposes `ct.tfm`) |

**Naming rule**: the image name without its extension. `ct.nii.gz`, `ct.nii`, `ct.mha`, `ct.mhd` and `ct.mha.gz` all use `ct.json` and `ct.tfm`. Two images with the same name in one folder (`ct.mha` and `ct.nii.gz`) share their side-car files.

---

## The `.json` File

One file can hold the unit and the labels:

```json
{
  "unit": "Gy",
  "1": {"name": "liver", "color": [255, 0, 0]},
  "2": {"name": "lung", "color": [0, 128, 255]}
}
```

* **Unit**: any text; common spellings are normalized (`hu` → `HU`, `bqml` → `Bq/mL`, `gy` → `Gy`, ...). Without a unit, `"modality": "CT"` gives `HU` and `"modality": "PT"` gives `SUV`.
* **Labels**: one entry per label value. Also accepted: `{"1": "liver"}`, `{"labels": {"1": "liver"}, "colors": {"1": [255, 0, 0]}}`, a list `[{"label": 1, "name": "liver", "color": ...}]`; colors as `[0–255]`, `[0.0–1.0]` or `"#RRGGBB"`.
* **Other keys are kept**: VVV only changes its own keys (saving the unit keeps the labels, saving a label map keeps the unit), so you can add your own notes. The file is written safely (never left half-written).
* **Edit by hand**: it is plain JSON; reload the image to read it again.

---

## The Transform Side-Car

* **Applied at each load**: when `ct.tfm` (or `ct.mat`) is next to `ct.nii.gz`, the image is shown with this transform every time it is loaded, also from a workspace (a workspace does not store transforms).
* **Shown in the Transform panel**: the file name, followed by `(side-car)`; hover it to see its full path.
* **Unload**: the <kbd>×</kbd> icon of the Transform panel removes the transform; the image is shown as read from disk. The file is kept, so the transform is applied again at the next load: rename or delete the file to stop that.
* **Another transform**: a transform file loaded with the Load icon replaces the side-car for this session.

---

## Where VVV Tells You

* **Active Viewer**: `Unit: HU (ct.json)`; hover `(ct.json)` for its full path. After you change the unit it shows `(modified, unsaved)` and a save icon: the icon writes only the unit to the `.json` file (the image is not rewritten).
* **Save messages**: `Saved: ct.nii.gz (+ ct.json)`, and the same for a label map.
* **ROIs**: hover the name of a label-map ROI: `Name and color from labels.json (side-car file)`.
* **Transform panel**: `ct.tfm (side-car)`, and a message when it is applied.
* **Unreadable file**: a warning in the status bar (or in the workspace warnings); the file is then never overwritten.
