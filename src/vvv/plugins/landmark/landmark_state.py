from typing import List, Optional


class Landmark:
    """Data model representing a 3D physical point landmark."""

    def __init__(
        self,
        id: str,
        name: str,
        pt_phys: List[float],
        color: Optional[List[int]] = None,
        visible: bool = True,
        show_name: bool = True,
    ):
        self.id = id
        self.name = name
        self.pt_phys = list(pt_phys)
        self.color = list(color) if color is not None else [255, 0, 0, 255]
        self.visible = visible
        self.show_name = show_name
        self.file_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "pt_phys": self.pt_phys,
            "color": self.color,
            "visible": self.visible,
            "show_name": self.show_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Landmark":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", "Landmark"),
            pt_phys=data.get("pt_phys", [0.0, 0.0, 0.0]),
            color=data.get("color", [255, 0, 0, 255]),
            visible=data.get("visible", True),
            show_name=data.get("show_name", True),
        )

    def snap_to_voxel_grid(self, volume) -> None:
        """Snaps physical coordinate pt_phys to nearest voxel center in volume."""
        if volume is None or self.pt_phys is None:
            return
        import numpy as np
        v_idx = volume.physic_coord_to_voxel_coord(self.pt_phys)
        v_center = np.round(v_idx)
        snapped_phys = volume.voxel_coord_to_physic_coord(v_center)
        self.pt_phys = list(snapped_phys)

    def to_csv_row(self) -> dict:
        return {
            "ID": self.id,
            "Name": self.name,
            "X_mm": f"{self.pt_phys[0]:.4f}",
            "Y_mm": f"{self.pt_phys[1]:.4f}",
            "Z_mm": f"{self.pt_phys[2]:.4f}",
            "Color_R": str(self.color[0]),
            "Color_G": str(self.color[1]),
            "Color_B": str(self.color[2]),
            "Color_A": str(self.color[3] if len(self.color) > 3 else 255),
            "Visible": str(self.visible),
            "ShowName": str(self.show_name),
        }

    @classmethod
    def from_csv_row(cls, row: dict, landmark_id: str) -> "Landmark":
        lm_id = row.get("ID", row.get("id", landmark_id))
        x = float(row.get("X_mm", row.get("x", 0.0)))
        y = float(row.get("Y_mm", row.get("y", 0.0)))
        z = float(row.get("Z_mm", row.get("z", 0.0)))
        r = int(row.get("Color_R", row.get("r", 255)))
        g = int(row.get("Color_G", row.get("g", 0)))
        b = int(row.get("Color_B", row.get("b", 0)))
        a = int(row.get("Color_A", row.get("a", 255)))
        vis_str = str(row.get("Visible", "True")).lower()
        visible = vis_str in ("true", "1", "yes")
        show_str = str(row.get("ShowName", "True")).lower()
        show_name = show_str in ("true", "1", "yes")
        name = row.get("Name", row.get("name", f"Landmark {lm_id}"))
        return cls(
            id=lm_id,
            name=name,
            pt_phys=[x, y, z],
            color=[r, g, b, a],
            visible=visible,
            show_name=show_name,
        )

