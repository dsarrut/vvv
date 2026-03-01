from enum import Enum, auto


class ViewMode(Enum):
    AXIAL = auto()
    SAGITTAL = auto()
    CORONAL = auto()
    HISTOGRAM = auto()


# Small helper to format the list of floats
def fmt(values, precision=3):
    # Round to max precision, then convert to string to remove trailing zeros
    return " ".join([f"{round(x, precision):g}" for x in values])
