"""HostProfiler — perfila CUALQUIER máquina a través de un RunnerPort.

El mismo código perfila el MBP (LocalRunner), el mini (SshRunner) o un VPS Linux
(SshRunner): un único script con marcadores, una sola ida y vuelta, coste ~0
(sin cargar modelos). Es el primer paso de la auto-adaptación (specs v2/05 §3):
sus hechos alimentan al TuningAdvisor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...domain.entities import MachineFacts, Platform

# ancho de banda conocido por chip (informativo; GB/s)
BANDWIDTH = {
    "Apple M1 Max": 400.0, "Apple M1 Pro": 200.0, "Apple M1 Ultra": 800.0,
    "Apple M1": 68.0, "Apple M2 Max": 400.0, "Apple M2 Pro": 200.0,
    "Apple M2": 100.0, "Apple M3 Max": 400.0, "Apple M4 Max": 546.0,
}

PROBE_SCRIPT = r"""
# ssh no-interactivo no carga el PATH de login: añadimos rutas habituales
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:$HOME/bin:$HOME/.local/bin:$HOME/Library/Python/3.9/bin"
echo "@@OS@@";       uname -s; uname -m
echo "@@HOSTNAME@@"; hostname
echo "@@DARWIN@@";   sysctl -n machdep.cpu.brand_string 2>/dev/null; \
                     sysctl -n hw.memsize 2>/dev/null; \
                     sysctl -n hw.physicalcpu 2>/dev/null; \
                     sysctl -n iogpu.wired_limit_mb 2>/dev/null || echo "-"
echo "@@LINUX@@";    grep -m1 "model name" /proc/cpuinfo 2>/dev/null | cut -d: -f2; \
                     grep MemTotal /proc/meminfo 2>/dev/null; nproc 2>/dev/null
echo "@@GPU@@";      nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "-"
echo "@@ENGINES@@"
for b in llama-bench llama-cli llama-server; do
  p=$(command -v $b 2>/dev/null) && echo "$b|$p|$($b --version 2>&1 | grep -m1 -o 'version: [0-9]* ([0-9a-f]*)')" || echo "$b|-|-"
done
command -v mlx_lm.generate >/dev/null 2>&1 && echo "mlx|$(command -v mlx_lm.generate)|-" || echo "mlx|-|-"
echo "@@END@@"
"""

GiB = 1024 ** 3


@dataclass
class HostProfile:
    facts: MachineFacts
    os_name: str = ""
    arch: str = ""
    engines: dict[str, dict] = field(default_factory=dict)   # name -> {path, version}
    gpu: str = ""

    def to_facts_json(self) -> dict:
        return {"os": self.os_name, "arch": self.arch, "gpu": self.gpu,
                "engines": self.engines}


def _section(blob: str, name: str) -> str:
    m = re.search(rf"@@{name}@@\n(.*?)(?=@@|\Z)", blob, re.DOTALL)
    return m.group(1).strip() if m else ""


def parse_probe(blob: str, machine_id: str) -> HostProfile:
    os_lines = _section(blob, "OS").splitlines()
    os_name = os_lines[0].strip() if os_lines else "unknown"
    arch = os_lines[1].strip() if len(os_lines) > 1 else ""
    hostname = _section(blob, "HOSTNAME").strip() or "unknown"

    chip, ram_gb, cores, wired = "", 0.0, 0, None
    platform = Platform.CPU
    if os_name == "Darwin":
        d = _section(blob, "DARWIN").splitlines()
        chip = d[0].strip() if d else ""
        ram_gb = int(d[1]) / GiB if len(d) > 1 and d[1].strip().isdigit() else 0.0
        cores = int(d[2]) if len(d) > 2 and d[2].strip().isdigit() else 0
        if len(d) > 3 and d[3].strip().isdigit() and int(d[3]) > 0:
            wired = int(d[3]) / 1024
        platform = Platform.METAL if arch == "arm64" else Platform.CPU
    elif os_name == "Linux":
        lx = _section(blob, "LINUX").splitlines()
        chip = lx[0].strip() if lx else ""
        m = re.search(r"MemTotal:\s+(\d+)\s+kB", _section(blob, "LINUX"))
        ram_gb = int(m.group(1)) * 1024 / GiB if m else 0.0
        nums = [l for l in lx if l.strip().isdigit()]
        cores = int(nums[-1]) if nums else 0
        gpu = _section(blob, "GPU")
        platform = Platform.CUDA if gpu and gpu != "-" else Platform.CPU

    engines: dict[str, dict] = {}
    for line in _section(blob, "ENGINES").splitlines():
        parts = line.split("|")
        if len(parts) == 3 and parts[1] != "-":
            engines[parts[0]] = {"path": parts[1], "version": parts[2]}

    facts = MachineFacts(
        machine_id=machine_id, hostname=hostname, chip=chip,
        ram_gb=round(ram_gb, 1), platform=platform,
        wired_limit_gb=round(wired, 2) if wired else None,
        bandwidth_gbs=BANDWIDTH.get(chip.strip()))
    gpu = _section(blob, "GPU")
    return HostProfile(facts=facts, os_name=os_name, arch=arch,
                       engines=engines, gpu="" if gpu == "-" else gpu)


def profile_host(runner, machine_id: str, timeout_s: float = 60.0) -> HostProfile:
    """Una sola ida y vuelta por el RunnerPort (local o SSH)."""
    res = runner.exec_shell(PROBE_SCRIPT, timeout_s)
    if res.exit_code != 0 and "@@OS@@" not in res.stdout:
        raise RuntimeError(f"probe falló en {machine_id}: {res.stderr[:300]}")
    return parse_probe(res.stdout, machine_id)
