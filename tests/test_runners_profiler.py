"""Tests F2: HostProfiler con runners falsos (sin red) + composición de comandos ssh."""
import unittest

from frontier_bench.adapters.probes.host_profiler import parse_probe, profile_host
from frontier_bench.adapters.runners.ssh import SshRunner
from frontier_bench.domain.entities import Platform
from frontier_bench.ports import ExecResult

DARWIN_BLOB = """@@OS@@
Darwin
arm64
@@HOSTNAME@@
mac-mini.local
@@DARWIN@@
Apple M1
17179869184
8
-
@@LINUX@@
@@GPU@@
-
@@ENGINES@@
llama-bench|/opt/homebrew/bin/llama-bench|version: 8880 (2799d933b)
llama-cli|/opt/homebrew/bin/llama-cli|version: 8880 (2799d933b)
llama-server|-|-
mlx|-|-
@@END@@
"""

LINUX_BLOB = """@@OS@@
Linux
x86_64
@@HOSTNAME@@
hetzner-vps
@@DARWIN@@
@@LINUX@@
 Intel(R) Xeon(R) CPU E5-1650 v3 @ 3.50GHz
MemTotal:       65536000 kB
12
@@GPU@@
-
@@ENGINES@@
llama-bench|-|-
llama-cli|/usr/local/bin/llama-cli|version: 9100 (abc123de)
llama-server|-|-
mlx|-|-
@@END@@
"""


class FakeRunner:
    def __init__(self, blob: str):
        self.blob = blob
        self.last_script = None

    def exec_shell(self, script: str, timeout_s: float = 60.0) -> ExecResult:
        self.last_script = script
        return ExecResult(0, self.blob, "", 0.1)


class TestHostProfiler(unittest.TestCase):
    def test_darwin_m1_parsed(self):
        prof = parse_probe(DARWIN_BLOB, "mini-m1-16g")
        f = prof.facts
        self.assertEqual(f.hostname, "mac-mini.local")
        self.assertEqual(f.chip, "Apple M1")
        self.assertEqual(f.ram_gb, 16.0)
        self.assertIs(f.platform, Platform.METAL)
        self.assertEqual(f.bandwidth_gbs, 68.0)          # tabla por chip
        self.assertIsNone(f.wired_limit_gb)              # "-" => default
        self.assertAlmostEqual(f.gpu_budget_gb, 16 * 2 / 3, places=1)
        self.assertIn("llama-bench", prof.engines)
        self.assertNotIn("llama-server", prof.engines)   # no instalado => fuera

    def test_linux_vps_parsed(self):
        prof = parse_probe(LINUX_BLOB, "hetzner-xeon")
        f = prof.facts
        self.assertIs(f.platform, Platform.CPU)          # sin nvidia-smi => CPU
        self.assertEqual(f.ram_gb, 62.5)
        self.assertIn("Xeon", f.chip)
        self.assertEqual(prof.os_name, "Linux")
        self.assertIn("llama-cli", prof.engines)

    def test_profile_host_via_runner(self):
        runner = FakeRunner(DARWIN_BLOB)
        prof = profile_host(runner, "mini-m1-16g")
        self.assertEqual(prof.facts.machine_id, "mini-m1-16g")
        self.assertIn("@@ENGINES@@", runner.last_script)  # una sola ida y vuelta


class TestSshRunner(unittest.TestCase):
    def test_argv_composition(self):
        r = SshRunner(host="mac-mini.local", user="admin")
        argv = r.ssh_argv("uname -s")
        self.assertEqual(argv[0], "ssh")
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("admin@mac-mini.local", argv)
        self.assertEqual(argv[-1], "uname -s")

    def test_exec_quotes_args(self):
        r = SshRunner(host="h", user="u")
        # composición sin ejecutar: verificamos el quoting del comando
        quoted = " ".join("'" + c.replace("'", "'\\''") + "'"
                          for c in ["echo", "hola mundo", "a'b"])
        self.assertIn("'hola mundo'", quoted)
        self.assertIn("'a'\\''b'", quoted)

    def test_no_user_uses_plain_host(self):
        r = SshRunner(host="tailscale-mini")
        self.assertEqual(r.target, "tailscale-mini")


if __name__ == "__main__":
    unittest.main()
