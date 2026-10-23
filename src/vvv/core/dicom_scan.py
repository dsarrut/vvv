"""DICOM folder scan for the DICOM browser: one folder at a time (pure: the
same files give the same result), merged into series, with an on-disk cache.

The cache (DicomScanCache) keeps the result of each scanned folder in the
user config folder, never in the scanned folders. A folder is reused only if
its signature (name, size and modification time of every file it holds)
and the library versions are unchanged; on any doubt it is scanned again.
"""

import copy
import hashlib
import json
import os

from vvv.utils import clean_string, get_config_dir, write_json_atomic

CACHE_VERSION = 1  # bump when the scan output changes
CACHE_MAX_ROOTS = 50  # cached scan roots kept (least recently used dropped)


def is_dicom_part10(path):
    """A DICOM Part 10 file: the 4 bytes 'DICM' after the 128-byte preamble.
    RT-Struct files always are; checking it avoids parsing the other files
    (images, NIfTI, JSON...) with pydicom."""
    try:
        with open(path, "rb") as f:
            f.seek(128)
            return f.read(4) == b"DICM"
    except OSError:
        return False


def _image_series_info(d, sid, file_names, file_reader):
    """Browser info of one image series (header of its first file)."""
    file_reader.SetFileName(file_names[0])
    file_reader.ReadImageInformation()

    def get_tag(tag, default=""):
        if file_reader.HasMetaDataKey(tag):
            try:
                val = file_reader.GetMetaData(tag).strip()
                return clean_string(val)
            except Exception:
                return default
            return default

    # --- FORMAT DATE & TIME ---
    d_str = get_tag("0008|0020")
    t_str = get_tag("0008|0030")
    fmt_date = d_str
    if len(d_str) >= 8:
        fmt_date = f"{d_str[0:4]}-{d_str[4:6]}-{d_str[6:8]}"
        if len(t_str) >= 4:
            fmt_date += f" {t_str[0:2]}:{t_str[2:4]}"

    # --- FUZZY SEARCH FOR INJECTED DOSE (Nested Sequences) ---
    dose_str = ""
    for k in file_reader.GetMetaDataKeys():
        if "0018|1074" in k:  # Radionuclide Total Dose
            try:
                raw_dose = file_reader.GetMetaData(k).strip()
                try:
                    dose_str = (
                        f"{float(raw_dose) / 1e6:.2f} MBq"
                    )
                except Exception:
                    dose_str = raw_dose
            except Exception:
                dose_str = ""
            dose_str = clean_string(dose_str)
            break

    size_tup = file_reader.GetSize()
    x, y = size_tup[0], size_tup[1]
    z = size_tup[2] if len(size_tup) > 2 else 1

    series_info = {
        "id": sid,
        "dir": d,
        "files": list(file_names),
        "patient_name": get_tag("0010|0010", "Unknown"),
        "study_desc": get_tag("0008|1030", "Unknown"),
        "series_desc": get_tag("0008|103e", "Unknown"),
        "modality": get_tag("0008|0060", "Unknown"),
        "date": fmt_date if fmt_date else "Unknown",
        "spacing": f"{file_reader.GetSpacing()[0]:.2f} x {file_reader.GetSpacing()[1]:.2f}",
        "frame_of_ref_uid": get_tag("0020|0052", ""),
        "study_instance_uid": get_tag("0020|000d", ""),
        "tags": [],
        "_base_z": z,
        "_base_x": x,
        "_base_y": y,
    }

    # --- CURATED MASTER TAG LIST ---
    target_tags = {
        "0008|0008": "Image Type",
        "0008|0020": "Study Date",
        "0008|0030": "Study Time",
        "0008|0060": "Modality",
        "0008|0070": "Manufacturer",
        "0008|1030": "Study Description",
        "0008|103E": "Series Description",
        "0010|0010": "Patient Name",
        "0010|0020": "Patient ID",
        "0010|0030": "Patient Birth Date",
        "0010|0040": "Patient Sex",
        "0018|0015": "Body Part Examined",
        "0018|0050": "Slice Thickness",
        "0018|1074": "Radionuclide Total Dose",
        "0018|0031": "Radiopharmaceutical",
        "0020|0011": "Series Number",
        "0028|0010": "Rows",
        "0028|0011": "Columns",
    }

    # Only append tags that actually contain data
    for tag, name in target_tags.items():
        val = dose_str if tag == "0018|1074" else get_tag(tag)

        if val:
            # Format standalone dates/times cleanly
            if (
                tag in ("0008|0020", "0010|0030")
                and len(val) == 8
            ):
                val = f"{val[0:4]}-{val[4:6]}-{val[6:8]}"
            elif tag == "0008|0030" and len(val) >= 4:
                val = (
                    f"{val[0:2]}:{val[2:4]}:{val[4:6]}"
                    if len(val) >= 6
                    else f"{val[0:2]}:{val[2:4]}"
                )

            series_info["tags"].append((tag, name, val))

    return series_info


def _rtstruct_info(d, fpath):
    """Browser info of an RT-Struct file, or None for any other file."""
    import pydicom

    head = pydicom.dcmread(fpath, stop_before_pixels=True, specific_tags=["Modality"])
    if str(getattr(head, "Modality", "")).upper() != "RTSTRUCT":
        return None
    ds = pydicom.dcmread(fpath, stop_before_pixels=True, force=True)
    sid = str(getattr(ds, "SeriesInstanceUID", ""))
    if not sid:
        sid = f"RTSTRUCT_{os.path.basename(fpath)}"

    p_name = clean_string(
        str(getattr(ds, "PatientName", "Unknown"))
    )
    s_desc = clean_string(
        str(getattr(ds, "StudyDescription", "Unknown"))
    )
    struct_label = clean_string(
        str(getattr(ds, "StructureSetLabel", ""))
    )
    ser_desc = clean_string(
        str(
            getattr(
                ds,
                "SeriesDescription",
                struct_label or "RT Structure Set",
            )
        )
    )

    d_str = clean_string(
        str(getattr(ds, "StudyDate", ""))
    )
    t_str = clean_string(
        str(getattr(ds, "StudyTime", ""))
    )
    fmt_date = d_str
    if len(d_str) >= 8:
        fmt_date = f"{d_str[0:4]}-{d_str[4:6]}-{d_str[6:8]}"
        if len(t_str) >= 4:
            fmt_date += f" {t_str[0:2]}:{t_str[2:4]}"

    seq_rois = (
        getattr(ds, "StructureSetROISequence", None) or []
    )
    num_rois = len(seq_rois)

    frame_of_ref_uid = ""
    ref_series_uid = ""
    if (
        hasattr(ds, "ReferencedFrameOfReferenceSequence")
        and ds.ReferencedFrameOfReferenceSequence
    ):
        for rfor in ds.ReferencedFrameOfReferenceSequence:
            if hasattr(rfor, "FrameOfReferenceUID"):
                frame_of_ref_uid = str(
                    rfor.FrameOfReferenceUID
                )
            if hasattr(rfor, "RTReferencedStudySequence"):
                for rstud in rfor.RTReferencedStudySequence:
                    if hasattr(
                        rstud, "RTReferencedSeriesSequence"
                    ):
                        for (
                            rser
                        ) in rstud.RTReferencedSeriesSequence:
                            if hasattr(
                                rser, "SeriesInstanceUID"
                            ):
                                ref_series_uid = str(
                                    rser.SeriesInstanceUID
                                )
                                break
    if not frame_of_ref_uid and hasattr(
        ds, "FrameOfReferenceUID"
    ):
        frame_of_ref_uid = str(ds.FrameOfReferenceUID)

    study_instance_uid = str(
        getattr(ds, "StudyInstanceUID", "")
    )

    tags = []

    def add_t(tg, name, val):
        if val:
            tags.append(
                (tg, name, clean_string(str(val)))
            )

    add_t("0008|0008", "Image Type", "RTSTRUCT")
    add_t("0008|0020", "Study Date", d_str)
    add_t("0008|0030", "Study Time", t_str)
    add_t("0008|0060", "Modality", "RTSTRUCT")
    add_t(
        "0008|0070",
        "Manufacturer",
        getattr(ds, "Manufacturer", ""),
    )
    add_t("0008|1030", "Study Description", s_desc)
    add_t("0008|103E", "Series Description", ser_desc)
    add_t(
        "3006|0002",
        "Structure Set Label",
        struct_label,
    )
    add_t("0010|0010", "Patient Name", p_name)
    add_t(
        "0010|0020",
        "Patient ID",
        getattr(ds, "PatientID", ""),
    )
    add_t(
        "0010|0030",
        "Patient Birth Date",
        getattr(ds, "PatientBirthDate", ""),
    )
    add_t(
        "0010|0040",
        "Patient Sex",
        getattr(ds, "PatientSex", ""),
    )
    add_t(
        "3006|0020",
        "ROIs Count",
        f"{num_rois} ROI(s)",
    )

    return {
        "id": sid,
        "dir": d,
        "files": [fpath],
        "patient_name": p_name,
        "study_desc": s_desc,
        "series_desc": ser_desc,
        "modality": "RTSTRUCT",
        "date": fmt_date if fmt_date else "Unknown",
        "spacing": "N/A",
        "size": f"{num_rois} ROI(s)",
        "frame_of_ref_uid": frame_of_ref_uid,
        "referenced_series_uid": ref_series_uid,
        "study_instance_uid": study_instance_uid,
        "structure_set_label": struct_label,
        "num_rois": num_rois,
        "tags": tags,
        "_is_rtstruct": True,
    }

def scan_dicom_dir(d, reader, file_reader):
    """Series of one folder (not recursive): [(series uid, info)], the image
    series with the files of this folder only. Raises on a folder error."""
    entries = []
    claimed_files = set()
    for sid in reader.GetGDCMSeriesIDs(d):
        file_names = reader.GetGDCMSeriesFileNames(d, sid)
        if not file_names:
            continue
        claimed_files.update(file_names)
        entries.append((sid, _image_series_info(d, sid, list(file_names), file_reader)))

    # RT-Struct files are ignored by the GDCM series reader
    try:
        dir_entries = os.listdir(d)
    except Exception:
        dir_entries = []
    for f in dir_entries:
        fpath = os.path.join(d, f)
        if fpath in claimed_files or not os.path.isfile(fpath) or not is_dicom_part10(fpath):
            continue
        try:
            info = _rtstruct_info(d, fpath)
        except Exception:
            info = None
        if info:
            entries.append((info["id"], info))
    return entries


def merge_dir_entries(series_dict, entries):
    """Add one folder's series: an image series met again (another folder)
    gets the files not already there (by base name, e.g. backup copies); an
    RT-Struct already met is kept as is."""
    for sid, info in entries:
        if sid not in series_dict:
            series_dict[sid] = copy.deepcopy(info)
        elif not info.get("_is_rtstruct") and not series_dict[sid].get("_is_rtstruct"):
            files = series_dict[sid]["files"]
            existing = {os.path.basename(f) for f in files}
            for fn in info["files"]:
                if os.path.basename(fn) not in existing:
                    files.append(fn)


def finalize_series(series_dict):
    """The browser list: internal keys removed, the image size set (files
    count, or the header Z size for a single multi-frame file)."""
    found = []
    for s in series_dict.values():
        if s.pop("_is_rtstruct", False):
            found.append(s)
            continue
        x, y, z_header = s.pop("_base_x"), s.pop("_base_y"), s.pop("_base_z")
        file_count = len(s["files"])
        z_dim = z_header if (z_header > 1 and file_count == 1) else file_count
        s["size"] = f"{x} x {y} x {z_dim}"
        found.append(s)
    return found


def dir_signature(d):
    """Signature of a folder's content: name, size and mtime of each file.
    None if the folder cannot be listed (then it is not cached)."""
    try:
        items = []
        with os.scandir(d) as it:
            for e in it:
                try:
                    if e.is_file():
                        st = e.stat()
                        items.append((e.name, st.st_size, st.st_mtime_ns))
                except OSError:
                    return None
    except OSError:
        return None
    items.sort()
    return hashlib.sha1(json.dumps(items).encode("utf-8", "surrogateescape")).hexdigest()


def _fingerprint():
    """Cache validity beyond the files: format version and library versions."""
    try:
        import SimpleITK as sitk

        sitk_v = sitk.Version_VersionString()
    except Exception:
        sitk_v = "?"
    try:
        import pydicom

        pyd_v = pydicom.__version__
    except Exception:
        pyd_v = "?"
    return {"version": CACHE_VERSION, "sitk": sitk_v, "pydicom": pyd_v}


class DicomScanCache:
    """Per-folder scan results of one scan root, in <config>/dicom_cache/."""

    def __init__(self, root, cache_dir=None):
        self.root = os.path.abspath(root)
        self.cache_dir = cache_dir or (get_config_dir() / "dicom_cache")
        key = hashlib.sha1(self.root.encode("utf-8", "surrogateescape")).hexdigest()[:20]
        self.path = os.path.join(os.fspath(self.cache_dir), f"{key}.json")
        self.dirs = {}  # folder -> {"sig": ..., "entries": [...]}
        self.hits = 0
        self.seen = set()
        self.changed = False
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("fingerprint") == _fingerprint() and data.get("root") == self.root:
                self.dirs = data.get("dirs", {}) or {}
        except Exception:
            self.dirs = {}  # missing / unreadable / other format: scan again

    def get(self, d, sig):
        """Cached entries of folder d if its signature is unchanged, else None."""
        self.seen.add(d)
        item = self.dirs.get(d)
        if sig is None or not isinstance(item, dict) or item.get("sig") != sig:
            return None
        try:
            entries = []
            for sid, info in item["entries"]:
                info = dict(info)
                info["tags"] = [tuple(t) for t in info.get("tags", [])]
                info["files"] = list(info["files"])
                entries.append((sid, info))
        except Exception:
            return None
        self.hits += 1
        return entries

    def put(self, d, sig, entries):
        if sig is None:
            return
        self.dirs[d] = {"sig": sig, "entries": [[sid, info] for sid, info in entries]}
        self.changed = True

    def save(self):
        """Write the cache (folders not met in this scan are dropped) and keep
        the CACHE_MAX_ROOTS most recently used roots. Errors are ignored: the
        cache is only a speed-up."""
        try:
            gone = set(self.dirs) - self.seen
            for d in gone:
                del self.dirs[d]
            os.makedirs(self.cache_dir, exist_ok=True)
            if self.changed or gone or not os.path.exists(self.path):
                write_json_atomic(
                    self.path,
                    {"fingerprint": _fingerprint(), "root": self.root, "dirs": self.dirs},
                    indent=None,
                )
            else:
                os.utime(self.path)  # recently used
            files = sorted(
                (os.path.join(self.cache_dir, f) for f in os.listdir(self.cache_dir) if f.endswith(".json")),
                key=os.path.getmtime,
            )
            for old in files[:-CACHE_MAX_ROOTS]:
                os.unlink(old)
        except Exception:
            pass

    @staticmethod
    def clear_all(cache_dir=None):
        cache_dir = cache_dir or (get_config_dir() / "dicom_cache")
        try:
            for f in os.listdir(cache_dir):
                if f.endswith(".json"):
                    os.unlink(os.path.join(cache_dir, f))
        except OSError:
            pass
