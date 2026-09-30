"""Process and host metrics.

Sampling functions block for a short interval, so callers in async code should run them with
``asyncio.to_thread``. Inside a container, ``psutil`` reports host-wide CPU and memory; the
container memory limit is read separately from cgroup v2.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psutil

_CGROUP_MEMORY_MAX = Path("/sys/fs/cgroup/memory.max")
_CGROUP_MEMORY_CURRENT = Path("/sys/fs/cgroup/memory.current")


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
    container_limit: int | None
    container_current: int | None


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
    in_container: bool
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
        container_limit=_read_cgroup_bytes(_CGROUP_MEMORY_MAX),
        container_current=_read_cgroup_bytes(_CGROUP_MEMORY_CURRENT),
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
        in_container=Path("/.dockerenv").exists(),
        boot_time=datetime.fromtimestamp(psutil.boot_time(), tz=UTC),
    )


def path_size(path: Path) -> int:
    """Size of a file, or total size of files in a directory. Missing paths count as zero."""
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())
    return 0


def _read_cgroup_bytes(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    return int(raw) if raw.isdigit() else None
