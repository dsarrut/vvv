"""System memory pressure, for the status bar warning: when the system runs
out of memory it swaps, and vvv seems to hang with no clue why. Cheap probes
(a few µs), no psutil needed. Every function returns None when it cannot tell."""

import ctypes
import ctypes.util
import os
import sys

OK, WARNING, CRITICAL = "ok", "warning", "critical"

_libc = None


def _sysctl(name, ctype):
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(ctypes.util.find_library("c"))
    value = ctype()
    size = ctypes.c_size_t(ctypes.sizeof(value))
    if _libc.sysctlbyname(name.encode(), ctypes.byref(value), ctypes.byref(size), None, 0) != 0:
        return None
    return value


class _XswUsage(ctypes.Structure):  # macOS vm.swapusage
    _fields_ = [("total", ctypes.c_uint64), ("avail", ctypes.c_uint64), ("used", ctypes.c_uint64),
                ("pagesize", ctypes.c_uint32), ("encrypted", ctypes.c_bool)]


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def _meminfo(text):
    """{field: bytes} of /proc/meminfo (or /proc/self/status) text."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "kB":
            out[parts[0].rstrip(":")] = int(parts[1]) * 1024
    return out


def _psi_level(text):
    """Level from Linux pressure stall info: the share of the last 10 s that
    tasks waited for memory ('some': at least one, 'full': all)."""
    avg = {}
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] in ("some", "full"):
            fields = dict(p.split("=") for p in parts[1:])
            avg[parts[0]] = float(fields.get("avg10", 0.0))
    if avg.get("full", 0.0) > 10.0:
        return CRITICAL
    if avg.get("some", 0.0) > 10.0:
        return WARNING
    return OK


def pressure():
    """(level, swap_used_bytes): level is OK, WARNING or CRITICAL (None if
    unknown), swap_used_bytes None if unknown."""
    try:
        if sys.platform == "darwin":
            lvl = _sysctl("kern.memorystatus_vm_pressure_level", ctypes.c_int)
            swap = _sysctl("vm.swapusage", _XswUsage)
            level = None if lvl is None else {1: OK, 2: WARNING, 4: CRITICAL}.get(lvl.value, OK)
            return level, None if swap is None else int(swap.used)
        if sys.platform.startswith("linux"):
            info = _meminfo(_read("/proc/meminfo") or "")
            swap = info["SwapTotal"] - info["SwapFree"] if "SwapTotal" in info else None
            psi = _read("/proc/pressure/memory")
            if psi:
                return _psi_level(psi), swap
            if "MemAvailable" in info and info.get("MemTotal"):
                free = info["MemAvailable"] / info["MemTotal"]
                return (CRITICAL if free < 0.05 else WARNING if free < 0.10 else OK), swap
            return None, swap
        if sys.platform == "win32":
            class _Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32)] + [
                    (n, ctypes.c_uint64) for n in ("total_phys", "avail_phys", "total_page",
                                                   "avail_page", "total_virt", "avail_virt", "avail_ext")
                ]
            st = _Status()
            st.dwLength = ctypes.sizeof(st)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return None, None
            load = st.dwMemoryLoad
            return (CRITICAL if load >= 97 else WARNING if load >= 90 else OK), None
    except Exception:
        pass
    return None, None


def process_memory():
    """Memory used by vvv (bytes), swapped-out part included, or None."""
    try:
        if sys.platform == "darwin":
            buf = (ctypes.c_uint64 * 40)()  # rusage_info_v2
            libproc = ctypes.CDLL(ctypes.util.find_library("proc"))
            if libproc.proc_pid_rusage(os.getpid(), 2, ctypes.byref(buf)) == 0:
                return int(buf[9])  # ri_phys_footprint (after a 16-byte uuid)
        elif sys.platform.startswith("linux"):
            st = _meminfo(_read("/proc/self/status") or "")
            if "VmRSS" in st:
                return st["VmRSS"] + st.get("VmSwap", 0)
        import psutil  # optional (the "memory" extra)

        return int(psutil.Process().memory_info().rss)
    except Exception:
        return None
