"""The system memory probes: they never raise, and read Linux pressure info."""

import vvv.core.system_memory as M


def test_probes_never_raise():
    level, swap = M.pressure()
    assert level in (None, M.OK, M.WARNING, M.CRITICAL)
    assert swap is None or swap >= 0
    mine = M.process_memory()
    assert mine is None or mine > 1e6


def test_linux_pressure_stall_info():
    psi = "some avg10={} avg60=0.00 avg300=0.00 total=1\nfull avg10={} avg60=0.00 avg300=0.00 total=1\n"
    assert M._psi_level(psi.format(0.5, 0.0)) == M.OK
    assert M._psi_level(psi.format(25.0, 2.0)) == M.WARNING
    assert M._psi_level(psi.format(60.0, 30.0)) == M.CRITICAL
    assert M._meminfo("MemTotal:  1000 kB\nSwapFree: 10 kB\n") == {"MemTotal": 1024000, "SwapFree": 10240}


def test_macos_level_needs_little_free_memory():
    """macOS stays at pressure 2 (warning) with plenty free: not a warning."""
    assert M._darwin_level(2, 40) == M.OK
    assert M._darwin_level(1, 60) == M.OK
    assert M._darwin_level(2, 12) == M.WARNING
    assert M._darwin_level(2, 3) == M.CRITICAL
    assert M._darwin_level(4, 30) == M.CRITICAL
    assert M._darwin_level(2, None) == M.OK  # free % unknown: the level alone is not enough
    assert M._darwin_level(None, None) is None
