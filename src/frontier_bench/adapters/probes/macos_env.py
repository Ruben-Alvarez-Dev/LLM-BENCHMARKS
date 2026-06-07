"""Sonda de entorno macOS — snapshots baratos (vm_stat/ps/sysctl), sin cargar nada.

Implementa la captura para domain.environment. Comandos de coste ~0:
no toca la GPU ni reserva memoria.
"""
from __future__ import annotations

import os
import re
import subprocess

from ...domain.environment import EnvSnapshot, ProcessInfo

GiB = 1024 ** 3

# procesos del propio banco: no cuentan como interferencia
BENCH_ALLOWLIST = ("llama-bench", "llama-cli", "llama-server", "frontier_bench",
                   "mlx_lm", "Python", "python3")


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout


def snapshot(heavy_threshold_gb: float = 2.0) -> EnvSnapshot:
    # RAM total
    total = int(_run(["sysctl", "-n", "hw.memsize"]).strip() or 0) / GiB
    n_cores = int(_run(["sysctl", "-n", "hw.physicalcpu"]).strip() or 1)

    # vm_stat: páginas libres + inactivas + purgables (recuperables)
    vm = _run(["vm_stat"])
    page_size = 16384 if "page size of 16384" in vm else 4096
    def pages(label: str) -> int:
        m = re.search(rf"{label}:\s+(\d+)", vm)
        return int(m.group(1)) if m else 0
    free_pages = pages("Pages free") + pages("Pages inactive") + pages("Pages purgeable")
    free_gb = free_pages * page_size / GiB

    # swap
    sw = _run(["sysctl", "-n", "vm.swapusage"])
    m = re.search(r"used = ([\d.]+)M", sw)
    swap_gb = float(m.group(1)) / 1024 if m else 0.0

    # load average
    up = _run(["uptime"])
    m = re.search(r"load averages?:\s+([\d.,]+)", up)
    load1 = float(m.group(1).replace(",", ".")) if m else 0.0

    # procesos pesados ajenos
    heavy: list[ProcessInfo] = []
    me = os.getpid()
    for line in _run(["ps", "-axo", "pid=,rss=,comm="]).splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, rss_kb, comm = parts
        try:
            rss_gb = int(rss_kb) * 1024 / GiB
        except ValueError:
            continue
        name = os.path.basename(comm)
        if (rss_gb >= heavy_threshold_gb and int(pid) != me
                and not any(a.lower() in name.lower() for a in BENCH_ALLOWLIST)):
            heavy.append(ProcessInfo(name=name, rss_gb=round(rss_gb, 2)))
    heavy.sort(key=lambda p: -p.rss_gb)

    return EnvSnapshot(free_ram_gb=round(free_gb, 2), total_ram_gb=round(total, 2),
                       swap_used_gb=round(swap_gb, 3), load_avg_1m=load1,
                       n_cores=n_cores, heavy_processes=tuple(heavy))
