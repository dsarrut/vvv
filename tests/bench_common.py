"""Shared helpers for the vvv speed benchmarks (bench_core.py, bench_startup.py).

Results are JSON files in bench_results/<host>/<bench>_<date>_<commit>.json and
are only ever compared with results of the same host.
"""

import datetime
import glob
import json
import os
import platform
import socket
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_DIR = os.path.join(REPO, "bench_results")

# A scenario is flagged slower only if its new median is above the old run's own
# p90 (its frame-to-frame spread) AND slower by more than both thresholds:
# ~5 ms scenarios jitter by ±30 % between runs, >= 10 ms ones by a few %.
REL_THRESHOLD = 0.10
ABS_THRESHOLD_MS = 2.0
# Loading a large file depends on the OS state (page cache, memory compression):
# it varies by up to 2x between runs on macOS, so only big changes are flagged.
REL_THRESHOLD_BY_PREFIX = {"load.": 0.50}


def _beyond(ref, value, rel, abs_ms):
    """True if `value` (a median) is clearly above `ref` (a result dict)."""
    m = ref["median_ms"]
    return value > ref.get("p90_ms", m) and value - m > abs_ms and value > m * (1 + rel)


def _git(*args):
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def machine_name():
    """Stable machine name: the network hostname of a laptop changes (DHCP)."""
    if os.environ.get("VVV_BENCH_HOST"):
        return os.environ["VVV_BENCH_HOST"]
    if sys.platform == "darwin":
        name = subprocess.run(
            ["scutil", "--get", "LocalHostName"], capture_output=True, text=True
        ).stdout.strip()
        if name:
            return name.lower()
    return socket.gethostname().split(".")[0].lower()


def environment():
    import numpy
    import SimpleITK
    import dearpygui

    try:
        import numba

        numba_v = numba.__version__
    except Exception:
        numba_v = None
    dirty = [
        line
        for line in _git("status", "--porcelain").splitlines()
        if not line[3:].startswith("bench_results/")
    ]
    return {
        "host": machine_name(),
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "simpleitk": SimpleITK.Version_VersionString(),
        "dearpygui": dearpygui.__version__,
        "numba": numba_v,
        "commit": _git("rev-parse", "--short", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(dirty),
    }


def loadavg():
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        return None


def save_report(report):
    """Write report to bench_results/<host>/<bench>_<date>_<commit>.json; return the path."""
    env = report["env"]
    out_dir = os.path.join(RESULTS_DIR, env["host"])
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"{report['bench']}_{stamp}_{env['commit'] or 'nogit'}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return path


def list_reports(bench, host=None):
    """Result files of one bench for one host, oldest first (names sort by date)."""
    host = host or machine_name()
    return sorted(glob.glob(os.path.join(RESULTS_DIR, host, f"{bench}_*.json")))


def resolve_ref(ref, bench, host=None, before=None):
    """Find a result file: a path, a commit prefix (latest run of it), or None for
    the latest result older than `before` (a path)."""
    files = list_reports(bench, host)
    if before is not None:
        files = [f for f in files if os.path.abspath(f) != os.path.abspath(before)
                 and os.path.basename(f) < os.path.basename(before)]
    if ref is None:
        return files[-1] if files else None
    if os.path.isfile(ref):
        return ref
    matches = [f for f in files if os.path.splitext(f)[0].rsplit("_", 1)[-1].startswith(ref)]
    return matches[-1] if matches else None


def _describe(rep):
    e = rep["env"]
    return f"{e['commit']}{'+dirty' if e['dirty'] else ''} {rep['date']}"


def compare(old, new, rel=REL_THRESHOLD, abs_ms=ABS_THRESHOLD_MS):
    """Print old vs new for every scenario; return the number of regressions.

    Refuses to compare different hosts: speed is only comparable on one machine.
    """
    if old["env"]["host"] != new["env"]["host"]:
        print(f"  refusing to compare different machines: "
              f"{old['env']['host']} vs {new['env']['host']}")
        return 0

    print(f"\n  compare on {new['env']['host']}:  {_describe(old)}  →  {_describe(new)}")
    for label, a, b in [
        ("params", old.get("params"), new.get("params")),
        ("render modes", old.get("render_modes"), new.get("render_modes")),
        ("numba", old["env"].get("numba"), new["env"].get("numba")),
        ("python", old["env"].get("python"), new["env"].get("python")),
        ("numpy", old["env"].get("numpy"), new["env"].get("numpy")),
    ]:
        if a != b:
            print(f"  WARNING: {label} differ — may explain changes: {a} → {b}")
    for rep, name in [(old, "old"), (new, "new")]:
        la = (rep.get("loadavg") or {}).get("start")
        n = rep["env"].get("cpu_count") or 0
        if la and n and la[0] > 0.5 * n:
            print(f"  note: {name} run on a busy machine (load average {la})")

    print(f"\n  {'scenario':28s} {'old':>9s} {'new':>9s} {'Δ':>9s} {'Δ%':>7s}")
    print("  " + "-" * 66)
    n_reg = 0
    keys = list(old["results"]) + [k for k in new["results"] if k not in old["results"]]
    for key in keys:
        ra, rb = old["results"].get(key), new["results"].get(key)
        a = ra["median_ms"] if ra else None
        b = rb["median_ms"] if rb else None
        if a is None or b is None:
            print(f"  {key:28s} {'—' if a is None else f'{a:7.1f}ms':>9s} "
                  f"{'—' if b is None else f'{b:7.1f}ms':>9s}")
            continue
        d = b - a
        pct = 100.0 * d / a if a > 0 else 0.0
        r = next((v for k, v in REL_THRESHOLD_BY_PREFIX.items() if key.startswith(k)), rel)
        if _beyond(ra, b, r, abs_ms):
            flag = "  ▲ SLOWER"
            n_reg += 1
        elif _beyond(rb, a, r, abs_ms):
            flag = "  ▼ faster"
        else:
            flag = ""
        print(f"  {key:28s} {a:7.1f}ms {b:7.1f}ms {d:+7.1f}ms {pct:+6.1f}%{flag}")
    print(f"\n  {n_reg} regression(s)  (flagged if median > previous p90, "
          f"> {100 * rel:.0f}% and > {abs_ms:g} ms)")
    return n_reg


def load_report(path):
    with open(path) as f:
        return json.load(f)
