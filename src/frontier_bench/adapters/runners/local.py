"""LocalRunner — ejecuta en la máquina donde corre la app. Implementa RunnerPort."""
from __future__ import annotations

import shutil
import subprocess
import time

from ...ports import ExecResult


class LocalRunner:
    runner_id = "local"

    def exec(self, cmd: list[str], timeout_s: float = 120.0,
             env: dict | None = None) -> ExecResult:
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout_s, env=env)
            return ExecResult(proc.returncode, proc.stdout, proc.stderr,
                              time.time() - t0)
        except subprocess.TimeoutExpired as e:
            return ExecResult(-1, e.stdout or "", f"timeout tras {timeout_s}s",
                              time.time() - t0)
        except FileNotFoundError as e:
            return ExecResult(-2, "", str(e), time.time() - t0)

    def exec_shell(self, script: str, timeout_s: float = 120.0) -> ExecResult:
        return self.exec(["/bin/sh", "-c", script], timeout_s)

    def put_file(self, local_path: str, remote_path: str) -> None:
        if local_path != remote_path:
            shutil.copy2(local_path, remote_path)

    def get_file(self, remote_path: str, local_path: str) -> None:
        if local_path != remote_path:
            shutil.copy2(remote_path, local_path)
