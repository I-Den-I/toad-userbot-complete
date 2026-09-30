from __future__ import annotations

import os
import time
from pathlib import Path

from tests.fakes import FakeClock
from toad_userbot.system.heartbeat import Heartbeat, is_alive
from toad_userbot.system.logtail import filter_by_level, tail_lines
from toad_userbot.system.metrics import (
    own_cgroup_dir,
    path_size,
    sample_cpu,
    sample_disk,
    sample_memory,
)


def test_tail_lines_reads_only_the_end(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_text("".join(f"line {index}\n" for index in range(10_000)), encoding="utf-8")

    assert tail_lines(log, 3) == ["line 9997", "line 9998", "line 9999"]
    assert len(tail_lines(log, 2_500)) == 2_500


def test_tail_lines_short_and_missing_files(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_text("один\nдва", encoding="utf-8")

    assert tail_lines(log, 10) == ["один", "два"]
    assert tail_lines(log, 0) == []
    assert tail_lines(tmp_path / "missing.log", 10) == []


def test_filter_by_level() -> None:
    lines = [
        "2026-09-30T12:00:00Z [debug    ] a",
        "2026-09-30T12:00:01Z [info     ] b",
        "2026-09-30T12:00:02Z [warning  ] c",
        "Traceback (most recent call last):",
        "2026-09-30T12:00:03Z [error    ] d",
    ]
    assert filter_by_level(lines, "warning") == [lines[2], lines[4]]
    assert filter_by_level(lines, "debug") == [lines[0], lines[1], lines[2], lines[4]]


def test_heartbeat_and_liveness(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "heartbeat"
    assert not is_alive(path, max_age=60)

    Heartbeat(path, clock).beat()

    assert path.read_text(encoding="utf-8") == clock.now().isoformat()
    assert is_alive(path, max_age=60)
    stale = time.time() - 600
    os.utime(path, (stale, stale))
    assert not is_alive(path, max_age=60)


def test_path_size(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"x" * 10)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b").write_bytes(b"x" * 5)

    assert path_size(tmp_path / "a") == 10
    assert path_size(tmp_path) == 15
    assert path_size(tmp_path / "missing") == 0


def test_metric_samplers_return_sane_values(tmp_path: Path) -> None:
    cpu = sample_cpu(interval=0.01)
    memory = sample_memory()
    disk = sample_disk(tmp_path)

    assert cpu.cores >= 1
    assert memory.process_rss > 0
    assert 0 < memory.system_used <= memory.system_total
    assert disk.total >= disk.used


def test_own_cgroup_dir_for_systemd_service(tmp_path: Path) -> None:
    proc = tmp_path / "cgroup"
    proc.write_text("0::/system.slice/toad-userbot.service\n", encoding="utf-8")

    found = own_cgroup_dir(proc, root=tmp_path / "fs")

    assert found == tmp_path / "fs" / "system.slice" / "toad-userbot.service"


def test_own_cgroup_dir_in_container_and_edge_cases(tmp_path: Path) -> None:
    container = tmp_path / "container"
    container.write_text("0::/\n", encoding="utf-8")
    cgroup_v1 = tmp_path / "v1"
    cgroup_v1.write_text("12:memory:/docker/abc\n", encoding="utf-8")

    assert own_cgroup_dir(container, root=tmp_path) == tmp_path
    assert own_cgroup_dir(cgroup_v1, root=tmp_path) is None
    assert own_cgroup_dir(tmp_path / "missing", root=tmp_path) is None
