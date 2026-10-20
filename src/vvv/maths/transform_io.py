import os
import re
import numpy as np
import SimpleITK as sitk


class TransformIO:
    """A pure mathematical utility for reading/writing 3D affine transforms."""

    @staticmethod
    def read_transform(filepath, fallback_center=None):
        """
        Parses .mat, .txt, Elastix, or standard ITK transforms into an Euler3DTransform.
        Supports standard 4x4 homogeneous matrices (16 values), old custom 4x3 matrices (12 values),
        and 3x3 rotation matrices (9 values).
        Converts from standard ITK convention (Fixed -> Moving) to VVV forward display space (Moving -> World).
        Uses fallback_center if the matrix lacks a defined Center of Rotation.
        """
        disk_transform = None

        # --- 1. Hand-parse simple text arrays ---
        if filepath.lower().endswith(".mat") or filepath.lower().endswith(".txt"):
            try:
                arr = np.loadtxt(filepath).flatten()
                if len(arr) == 16:
                    # 4x4 homogeneous matrix: [R | Offset] with [0 0 0 1] on last row
                    M = arr.reshape(4, 4)
                    R = M[0:3, 0:3]
                    offset = M[0:3, 3]
                elif len(arr) == 12:
                    # Old custom 4x3 matrix format: 9 rotation + 3 offset
                    R = arr[:9].reshape(3, 3)
                    offset = arr[9:12]
                elif len(arr) == 9:
                    # 3x3 rotation matrix only
                    R = arr.reshape(3, 3)
                    offset = np.zeros(3)
                else:
                    raise ValueError("Unsupported matrix size")

                # Snap it back to perfect orthogonality using SVD
                U, _, Vt = np.linalg.svd(R)
                R_ortho = U @ Vt

                # Ensure it's a true rotation (determinant must be +1, not -1 reflection)
                if np.linalg.det(R_ortho) < 0:
                    U[:, -1] *= -1
                    R_ortho = U @ Vt

                C = (
                    np.array(fallback_center, dtype=np.float64)
                    if fallback_center is not None
                    else np.zeros(3)
                )
                # In ITK Euler3DTransform: p' = R @ (p - C) + C + T = R @ p + (C + T - R @ C).
                # Therefore, offset = C + T - R @ C => T = offset - C + R @ C
                T = offset - C + R_ortho @ C

                disk_transform = sitk.Euler3DTransform()
                disk_transform.SetCenter(C.tolist())
                disk_transform.SetMatrix(R_ortho.flatten().tolist())
                disk_transform.SetTranslation(T.tolist())
            except Exception:
                pass  # Fall through to standard Elastix/ITK parsers

        # --- 2. Try to parse as an Elastix Parameter File ---
        if disk_transform is None:
            try:
                with open(filepath, "r") as f:
                    content = f.read()

                if "TransformParameters" in content and "CenterOfRotationPoint" in content:
                    params_match = re.search(r"\(TransformParameters(.*?)\)", content)
                    center_match = re.search(r"\(CenterOfRotationPoint(.*?)\)", content)
                    if params_match and center_match:
                        params = params_match.group(1).split()
                        center = center_match.group(1).split()

                        disk_transform = sitk.Euler3DTransform()
                        disk_transform.SetRotation(
                            float(params[0]), float(params[1]), float(params[2])
                        )
                        disk_transform.SetTranslation(
                            (float(params[3]), float(params[4]), float(params[5]))
                        )
                        disk_transform.SetCenter(
                            (float(center[0]), float(center[1]), float(center[2]))
                        )
            except Exception:
                pass

        # --- 3. Fallback to standard ITK Transform Reader ---
        if disk_transform is None:
            generic_transform = sitk.ReadTransform(filepath)
            disk_transform = sitk.Euler3DTransform()
            if generic_transform.GetDimension() == 3:
                disk_transform.SetMatrix(generic_transform.GetMatrix())
                disk_transform.SetTranslation(generic_transform.GetTranslation())
                if hasattr(generic_transform, "GetCenter"):
                    disk_transform.SetCenter(generic_transform.GetCenter())

            # Failsafe: If Center of Rotation is exactly 0,0,0, update center while preserving offset
            if (
                np.allclose(disk_transform.GetCenter(), [0, 0, 0])
                and fallback_center is not None
            ):
                C = np.array(fallback_center, dtype=np.float64)
                R = np.array(disk_transform.GetMatrix()).reshape(3, 3)
                T = np.array(disk_transform.GetTranslation())
                T_new = T - C + R @ C
                disk_transform.SetCenter(C.tolist())
                disk_transform.SetTranslation(T_new.tolist())

        # Convert from standard ITK convention (Fixed -> Moving)
        # to VVV forward display space (Moving -> World).
        try:
            inv = disk_transform.GetInverse()
            euler = sitk.Euler3DTransform()
            euler.SetMatrix(inv.GetMatrix())
            euler.SetTranslation(inv.GetTranslation())
            if hasattr(inv, "GetCenter"):
                euler.SetCenter(inv.GetCenter())
            return euler
        except Exception:
            return disk_transform

    @staticmethod
    def write_transform(transform, filepath):
        """Writes an Euler3DTransform to disk (.mat, .txt, or ITK formats) in standard ITK convention (Fixed -> Moving)."""
        # Invert from VVV forward display space (Moving -> World) to standard ITK convention (Fixed -> Moving)
        try:
            disk_transform = transform.GetInverse()
        except Exception:
            disk_transform = transform

        if filepath.lower().endswith(".mat") or filepath.lower().endswith(".txt"):
            R = np.array(disk_transform.GetMatrix()).reshape(3, 3)
            C = (
                np.array(disk_transform.GetCenter())
                if hasattr(disk_transform, "GetCenter")
                else np.zeros(3)
            )
            T = np.array(disk_transform.GetTranslation())
            offset = C + T - R @ C

            with open(filepath, "w") as f:
                f.write(f"{R[0, 0]:.6f} {R[0, 1]:.6f} {R[0, 2]:.6f} {offset[0]:.6f}\n")
                f.write(f"{R[1, 0]:.6f} {R[1, 1]:.6f} {R[1, 2]:.6f} {offset[1]:.6f}\n")
                f.write(f"{R[2, 0]:.6f} {R[2, 1]:.6f} {R[2, 2]:.6f} {offset[2]:.6f}\n")
                f.write("0.000000 0.000000 0.000000 1.000000\n")
        else:
            # Otherwise use standard SimpleITK .tfm format
            if not os.path.splitext(filepath)[1]:
                filepath = filepath + ".tfm"
            sitk.WriteTransform(disk_transform, filepath)
