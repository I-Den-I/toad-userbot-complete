"""Process and host metrics.

Sampling functions block for a short interval, so callers in async code should run them with
``asyncio.to_thread``. ``psutil`` reports host-wide CPU and memory; the memory limit of the
process's own cgroup (systemd service or container) is read separately from cgroup v2.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psutil

_CGROUP_ROOT = Path("/sys/fs/cgroup")
_PROC_SELF_CGROUP = Path("/proc/self/cgroup")


@dataclass(frozen=True, slots=True)
class CpuSnapshot:
    process_percent: float
    system_percent: float
    cores: int
    load_average: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    process_rss: int
    system_total: int
    system_used: int
    system_available: int
    system_percent: float
    swap_used: int
    swap_total: int
    cgroup_limit: int | None
    cgroup_current: int | None


@dataclass(frozen=True, slots=True)
class DiskSnapshot:
    total: int
    used: int
    free: int
    percent: float


@dataclass(frozen=True, slots=True)
class HostInfo:
    hostname: str
    platform: str
    python: str
    pid: int
    supervisor: str | None
    boot_time: datetime


def sample_cpu(interval: float = 0.5) -> CpuSnapshot:
    process = psutil.Process()
    process.cpu_percent(None)
    system = psutil.cpu_percent(interval=interval)
    try:
        load = os.getloadavg()
    except OSError:  # pragma: no cover - not available on every platform
        load = None
    return CpuSnapshot(
        process_percent=process.cpu_percent(None),
        system_percent=system,
        cores=psutil.cpu_count() or 1,
        load_average=load,
    )


def sample_memory() -> MemorySnapshot:
    cgroup = own_cgroup_dir()
    virtual = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return MemorySnapshot(
        process_rss=psutil.Process().memory_info().rss,
        system_total=virtual.total,
        system_used=virtual.used,
        system_available=virtual.available,
        system_percent=virtual.percent,
        swap_used=swap.used,
        swap_total=swap.total,
        cgroup_limit=_read_cgroup_bytes(cgroup / "memory.max") if cgroup else None,
        cgroup_current=_read_cgroup_bytes(cgroup / "memory.current") if cgroup else None,
    )


def sample_disk(path: Path) -> DiskSnapshot:
    usage = psutil.disk_usage(str(path))
    return DiskSnapshot(total=usage.total, used=usage.used, free=usage.free, percent=usage.percent)


def host_info() -> HostInfo:
    return HostInfo(
        hostname=platform.node(),
        platform=platform.platform(terse=True),
        python=sys.version.split()[0],
        pid=os.getpid(),
        supervisor=_supervisor(),
        boot_time=datetime.fromtimestamp(psutil.boot_time(), tz=UTC),
    )


def path_size(path: Path) -> int:
    """Size of a file, or total size of files in a directory. Missing paths count as zero."""
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())
    return 0


def own_cgroup_dir(proc_cgroup: Path = _PROC_SELF_CGROUP, root: Path = _CGROUP_ROOT) -> Path | None:
    """cgroup v2 directory of this process, e.g. ``system.slice/toad-userbot.service``.

    Inside a container with a private cgroup namespace the path is ``/``, i.e. the root.
    """
    try:
        lines = proc_cgroup.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("0::"):
            return root / line.removeprefix("0::").lstrip("/")
    return None


def _supervisor() -> str | None:
    if "INVOCATION_ID" in os.environ:  # set by systemd for every service it starts
        return "systemd"
    if Path("/.dockerenv").exists():
        return "Docker"
    return None


def _read_cgroup_bytes(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    return int(raw) if raw.isdigit() else None
