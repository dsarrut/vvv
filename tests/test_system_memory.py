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
