"""Cost, in CPU-seconds, on three lines that are never summed.

**Why CPU-seconds and not wall-clock.** Wall-clock was disqualified by
measurement, twice over. `models/lgbm.py` freezes `num_threads: 0` — every core —
into the parameters published in `metrics/model.json`, and on a 32-core machine
the same walk-forward gave 55.7 s wall against 54.9 s CPU at one thread and
61.0 s wall against 1588.5 s CPU at thirty-two. The wall:CPU ratio moves from
0.99 to 26.1 on one machine by changing one parameter. Separately, the identical
workload measured 202.7 s of wall on a loaded machine and 59.9 s on an idle one —
3.4x, from nothing but neighbours. A number that disagrees with itself by 3.4x
cannot decide whether a foundation model is cheaper than a GBM.

There is a trap inside that: `params={"num_threads": 1}` alone does **not**
serialise the work. It gave a CPU:wall ratio of 1.38, which is impossible for one
thread — OpenMP threads keep spinning. Only `OMP_NUM_THREADS=1` in the
environment brings it to 0.99. Both are set, and `hardware.n_threads` records
what was actually asked for rather than what someone intended.

**Why three lines, never summed.** The refit is 98.7% of the GBM's cost, and a
zero-shot model refits never. Adding `fit` to `infer` hands the foundation model
a ~76x win that belongs to the protocol — 55 refits is a choice of this harness —
and says nothing about the model. `load_cpu_s` is the third line because leaving
it out hides the opposite thing: a checkpoint that takes longer to read than to
run would look free.

`fit_cpu_s` is **measured, not stipulated**, including for the zero-shot arms
where it is expected to be 0.0. An RFC whose doctrine is executable provenance
cannot assert the number that decides the comparison.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

#: Field names that would collapse the three lines back into one. Checked by
#: name *and* by value, because the interesting version of this mistake is a
#: field called something innocent that happens to hold `fit + infer`.
FORBIDDEN_TOTALS = ("total_cpu_s", "cpu_s", "cost_per_prediction", "seconds")


class CostGateError(RuntimeError):
    """G7 refused. `gate` is what goes into the artifact's `failed_gate`."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(message)
        self.gate = gate


def _ram_gb() -> float:
    """Total physical memory, from the standard library on both platforms.

    The RFC once declared this unmeasurable offline and made the field nullable —
    `psutil` is not in the lockfile and `resource` is Unix-only. The premise was
    false: `GlobalMemoryStatusEx` and `os.sysconf` are both stdlib, and adding a
    dependency to read a number the OS already exposes would have been the wrong
    fix for a problem that did not exist.
    """
    if sys.platform == "win32":
        import ctypes  # platform-specific, imported where used

        class _MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return round(status.ullTotalPhys / 2**30, 2)

    return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 2)


def peak_rss_mb() -> float:
    """Peak resident set size of this process, in MB, from the standard library.

    A foundation model that wins on latency and loses 600x on memory did not get
    cheaper, so the number is reported alongside the CPU lines rather than
    instead of them.
    """
    if sys.platform == "win32":
        import ctypes  # platform-specific, imported where used

        class _Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        # `GetCurrentProcess` returns a pseudo-handle. Without an explicit
        # `restype` ctypes assumes `c_int` and truncates it on 64-bit, the call
        # fails, and the first version of this function returned **0.0** — the
        # exact placeholder G7 exists to reject, produced by the code that feeds
        # G7. Hence the explicit signatures and the raise: a memory reading that
        # cannot be taken must not come back as a plausible-looking zero.
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_Counters),
            ctypes.c_ulong,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int

        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise CostGateError(
                "cost-provenance",
                f"GetProcessMemoryInfo failed (error {ctypes.get_last_error()}); "
                "peak RSS is unreadable and must not be reported as zero",
            )
        return round(counters.PeakWorkingSetSize / 2**20, 1)

    import resource  # Unix-only, imported where used

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports kilobytes, macOS bytes.
    return round(peak / (2**10 if sys.platform == "linux" else 2**20), 1)


def hardware_block(n_threads: int, device: str = "cpu") -> dict:
    """The stamp without which no cost number in this lane may be published.

    `n_threads` is passed in rather than detected: it has to be what the
    measurement was actually configured with, and `os.cpu_count()` would report
    the machine's cores while the run was pinned to one.
    """
    if n_threads < 1:
        raise CostGateError("cost-provenance", f"n_threads must be >= 1, got {n_threads!r}")
    return {
        "cpu_model": platform.processor() or platform.machine(),
        "n_threads": n_threads,
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "ram_gb": _ram_gb(),
        "device": device,
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


@dataclass
class CostMeter:
    """Three accumulators of `time.process_time()`, kept apart on purpose."""

    fit_cpu_s: float = 0.0
    infer_cpu_s: float = 0.0
    load_cpu_s: float = 0.0
    _peak_rss_mb: float = field(default=0.0, repr=False)

    @contextmanager
    def timing(self, line: str):
        if line not in ("fit", "infer", "load"):
            raise ValueError(f"unknown cost line {line!r}")
        start = time.process_time()
        try:
            yield
        finally:
            elapsed = time.process_time() - start
            setattr(self, f"{line}_cpu_s", getattr(self, f"{line}_cpu_s") + elapsed)
            self._peak_rss_mb = max(self._peak_rss_mb, peak_rss_mb())

    def block(self, n_predictions: int) -> dict:
        """The per-arm cost record. Deliberately has no total."""
        if n_predictions < 1:
            raise CostGateError(
                "cost-provenance", f"n_predictions must be >= 1, got {n_predictions!r}"
            )
        return {
            "fit_cpu_s": round(self.fit_cpu_s, 4),
            "infer_cpu_s": round(self.infer_cpu_s, 4),
            "load_cpu_s": round(self.load_cpu_s, 4),
            "peak_rss_mb": self._peak_rss_mb,
            "n_predictions": n_predictions,
            "fit_cpu_ms_per_prediction": round(1000.0 * self.fit_cpu_s / n_predictions, 4),
            "infer_cpu_ms_per_prediction": round(1000.0 * self.infer_cpu_s / n_predictions, 4),
            "load_cpu_ms_per_prediction": round(1000.0 * self.load_cpu_s / n_predictions, 4),
        }


LINES = ("fit_cpu_s", "infer_cpu_s", "load_cpu_s")


def assert_cost_provenance(artifact: dict) -> None:
    """G7 — a cost comparison may be published only with its provenance.

    Domain, not presence. `{"cpu_model": "", "n_threads": 0, "ram_gb": 0.0,
    "device": "unknown"}` satisfies every "is the block there?" check ever
    written, and publishes a comparison with a fabricated stamp.
    """
    hardware = artifact.get("hardware")
    if not isinstance(hardware, dict):
        raise CostGateError("cost-provenance", "no hardware block")

    problems = []
    if len(str(hardware.get("cpu_model", "")).replace(" ", "")) < 3:
        problems.append(f"cpu_model={hardware.get('cpu_model')!r}")
    if not isinstance(hardware.get("n_threads"), int) or hardware.get("n_threads", 0) < 1:
        problems.append(f"n_threads={hardware.get('n_threads')!r}")
    if not isinstance(hardware.get("ram_gb"), int | float) or hardware.get("ram_gb", 0) <= 0:
        problems.append(f"ram_gb={hardware.get('ram_gb')!r}")
    if hardware.get("device") not in ("cpu", "cuda"):
        problems.append(f"device={hardware.get('device')!r}")
    if problems:
        raise CostGateError(
            "cost-provenance", "hardware block is a placeholder: " + ", ".join(problems)
        )

    arms = artifact.get("arms") or []
    if not arms:
        raise CostGateError("cost-provenance", "no arms: the gate would pass vacuously")

    for arm in arms:
        arm_id = arm.get("id", "?")
        missing = [line for line in LINES if not isinstance(arm.get(line), int | float)]
        if missing:
            raise CostGateError("cost-provenance", f"{arm_id}: missing cost line(s) {missing}")
        _refuse_totals(arm_id, arm)


def _refuse_totals(arm_id: str, arm: dict) -> None:
    """No field may collapse two of the three lines back into one.

    Checked by name and by value. The name check catches the obvious version;
    the value check catches the interesting one, where a field with a harmless
    name happens to hold `fit + infer` and the reader has no way to know.
    """
    for name in FORBIDDEN_TOTALS:
        if name in arm:
            raise CostGateError(
                "cost-provenance",
                f"{arm_id}: field {name!r} collapses the cost lines; they are never summed",
            )

    sums = {
        "fit+infer": arm["fit_cpu_s"] + arm["infer_cpu_s"],
        "fit+load": arm["fit_cpu_s"] + arm["load_cpu_s"],
        "infer+load": arm["infer_cpu_s"] + arm["load_cpu_s"],
        "all three": sum(arm[line] for line in LINES),
    }
    # A line that is 0.0 makes some sums equal to a legitimate single line, and
    # that is not evidence of anything.
    interesting = {label: total for label, total in sums.items() if total > 0}
    for key, value in arm.items():
        if key in LINES or not isinstance(value, int | float) or value <= 0:
            continue
        for label, total in interesting.items():
            if abs(value - total) < 1e-9 and value not in (arm[line] for line in LINES):
                raise CostGateError(
                    "cost-provenance",
                    f"{arm_id}: field {key!r} equals {label}; the cost lines are never summed",
                )
