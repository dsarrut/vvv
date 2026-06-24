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
        Uses fallback_center if the matrix lacks a defined Center of Rotation.
        """
        new_transform = sitk.Euler3DTransform()

        # --- 1. Hand-parse simple text arrays ---
        if filepath.lower().endswith(".mat") or filepath.lower().endswith(".txt"):
            try:
                arr = np.loadtxt(filepath).flatten()
                if len(arr) == 16:
                    # 4x4 homogeneous matrix: [R | T] with [0 0 0 1] on last row
                    M = arr.reshape(4, 4)
                    R = M[0:3, 0:3]
                    trans_vec = M[0:3, 3].tolist()
                elif len(arr) == 12:
                    # Old custom 4x3 matrix format: 9 rotation + 3 translation
                    R = arr[:9].reshape(3, 3)
                    trans_vec = arr[9:12].tolist()
                elif len(arr) == 9:
                    # 3x3 rotation matrix only
                    R = arr.reshape(3, 3)
                    trans_vec = [0.0, 0.0, 0.0]
                else:
                    raise ValueError("Unsupported matrix size")

                # Snap it back to perfect orthogonality using SVD.
                U, _, Vt = np.linalg.svd(R)
                R_ortho = U @ Vt

                # Ensure it's a true rotation (determinant must be +1, not -1 reflection)
                if np.linalg.det(R_ortho) < 0:
                    U[:, -1] *= -1
                    R_ortho = U @ Vt

                rot_matrix = R_ortho.flatten().tolist()
                new_transform.SetMatrix(rot_matrix)
                new_transform.SetTranslation(trans_vec)

                if fallback_center is not None:
                    new_transform.SetCenter(fallback_center)

                return new_transform
            except Exception as e:
                pass  # Fall through to standard Elastix/ITK parsers

        # --- 2. Try to parse as an Elastix Parameter File ---
        with open(filepath, "r") as f:
            content = f.read()

        if "TransformParameters" in content and "CenterOfRotationPoint" in content:
            params_match = re.search(r"\(TransformParameters(.*?)\)", content)
            center_match = re.search(r"\(CenterOfRotationPoint(.*?)\)", content)
            if params_match and center_match:
                params = params_match.group(1).split()
                center = center_match.group(1).split()

                new_transform.SetRotation(
                    float(params[0]), float(params[1]), float(params[2])
                )
                new_transform.SetTranslation(
                    (float(params[3]), float(params[4]), float(params[5]))
                )
                new_transform.SetCenter(
                    (float(center[0]), float(center[1]), float(center[2]))
                )
                return new_transform

        # --- 3. Fallback to standard ITK Transform Reader ---
        generic_transform = sitk.ReadTransform(filepath)
        if generic_transform.GetDimension() == 3:
            new_transform.SetMatrix(generic_transform.GetMatrix())
            new_transform.SetTranslation(generic_transform.GetTranslation())
            if hasattr(generic_transform, "GetCenter"):
                new_transform.SetCenter(generic_transform.GetCenter())

        # Failsafe: If Center of Rotation is exactly 0,0,0, fix it.
        if (
            np.allclose(new_transform.GetCenter(), [0, 0, 0])
            and fallback_center is not None
        ):
            new_transform.SetCenter(fallback_center)

        return new_transform

    @staticmethod
    def write_transform(transform, filepath):
        """Writes an Euler3DTransform to disk (.mat, .txt, or ITK formats)."""
        if filepath.lower().endswith(".mat") or filepath.lower().endswith(".txt"):
            mat = transform.GetMatrix()  # Tuple of 9 (r00, r01, r02, r10, r11, r12, r20, r21, r22)
            trans = transform.GetTranslation()  # Tuple of 3 (tx, ty, tz)

            with open(filepath, "w") as f:
                f.write(f"{mat[0]:.6f} {mat[1]:.6f} {mat[2]:.6f} {trans[0]:.6f}\n")
                f.write(f"{mat[3]:.6f} {mat[4]:.6f} {mat[5]:.6f} {trans[1]:.6f}\n")
                f.write(f"{mat[6]:.6f} {mat[7]:.6f} {mat[8]:.6f} {trans[2]:.6f}\n")
                f.write("0.000000 0.000000 0.000000 1.000000\n")
        else:
            # Otherwise use standard SimpleITK .tfm format
            sitk.WriteTransform(transform, filepath)
