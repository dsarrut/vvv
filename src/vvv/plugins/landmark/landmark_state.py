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
