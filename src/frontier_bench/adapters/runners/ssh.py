"""SshRunner — ejecuta en una máquina remota vía SSH (red local o Tailscale).

v2.0 sin agente: solo necesita sshd + clave ya autorizada en el destino
(p.ej. admin@mac-mini.local). Cada exec es idempotente; BatchMode evita
prompts interactivos colgados. scp para ficheros.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

from ...ports import ExecResult

SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=accept-new"]


@dataclass
class SshRunner:
    host: str                 # "mac-mini.local" o nombre Tailscale
    user: str = ""            # "" => usuario por defecto del ssh_config
    runner_id: str = "ssh"

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    def ssh_argv(self, remote_cmd: str) -> list[str]:
        return ["ssh", *SSH_OPTS, self.target, remote_cmd]

    def exec(self, cmd: list[str], timeout_s: float = 120.0,
             env: dict | None = None) -> ExecResult:
        # composición segura sencilla: cada arg entre comillas simples
        quoted = " ".join("'" + c.replace("'", "'\\''") + "'" for c in cmd)
        prefix = ""
        if env:
            prefix = " ".join(f"{k}={v}" for k, v in env.items()) + " "
        return self.exec_shell(prefix + quoted, timeout_s)

    def exec_shell(self, script: str, timeout_s: float = 120.0) -> ExecResult:
        t0 = time.time()
        try:
            proc = subprocess.run(self.ssh_argv(script), capture_output=True,
                                  text=True, timeout=timeout_s)
            return ExecResult(proc.returncode, proc.stdout, proc.stderr,
                              time.time() - t0)
        except subprocess.TimeoutExpired as e:
            return ExecResult(-1, e.stdout or "", f"ssh timeout tras {timeout_s}s",
                              time.time() - t0)

    def put_file(self, local_path: str, remote_path: str) -> None:
        subprocess.run(["scp", *SSH_OPTS, local_path,
                        f"{self.target}:{remote_path}"], check=True, timeout=600)

    def get_file(self, remote_path: str, local_path: str) -> None:
        subprocess.run(["scp", *SSH_OPTS, f"{self.target}:{remote_path}",
                        local_path], check=True, timeout=600)
