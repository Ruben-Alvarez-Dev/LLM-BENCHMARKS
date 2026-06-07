"""CLI F1 — velocidad vía llama-bench (-d nativo) + calidad vía llama-cli + validez ambiental.

Decisión 2026-06-06 (incidente llama-cli b8880, ver SESSION.md): velocidad y calidad
van por instrumentos distintos. Antes de cada celda se hace pre-flight ambiental;
si no hay RAM o hay procesos pesados, el run se ejecuta solo con --force-env y
queda marcado valid=0 (no puntúa en rankings ni veredictos).

Ejemplo:
  PYTHONPATH=src python3 -m frontier_bench.cli measure \
    --model-file <ruta.gguf> --name QwenPaw-Flash-9B --machine mbp-m1max-32g \
    --ctx 16384 --depths 0,50,90 --reps 3
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

from .adapters.corpus.real_corpus import RealCorpus
from .adapters.engines.llamabench import LlamaBench
from .adapters.engines.llamacpp_cli import LlamaCppCli
from .adapters.probes.macos_env import snapshot
from .adapters.storage.sqlite_store import SqliteStore, cell_key
from .domain.entities import (ArchKind, CellSpec, CellStatus, KvProfile, LoadProfile,
                              ModelSpec)
from .domain.environment import assess
from .domain.kv_model import budget, GiB
from .domain.entities import MachineFacts, Platform


def cmd_measure(args: argparse.Namespace) -> int:
    bench = LlamaBench(binary=args.bench_binary)
    info = bench.info()
    print(f"engine: llamacpp v{info.version} ({info.commit}) [llama-bench]")

    kv = KvProfile(arch=ArchKind.HYBRID_LINEAR if args.arch == "hybrid" else ArchKind(args.arch),
                   n_layers=args.layers, kv_heads=args.kv_heads, head_dim=args.head_dim,
                   full_attn_layers=args.full_attn_layers,
                   recurrent_state_mb=args.recurrent_mb)
    mfile = Path(args.model_file).expanduser()
    model = ModelSpec(model_id=args.name, name=args.name, params_b=args.params_b,
                      quant=args.quant, file_bytes=mfile.stat().st_size, kv=kv,
                      context_native=args.ctx_native, context_max=args.ctx_native,
                      file_path=str(mfile))

    store = SqliteStore(args.db)
    engine_key = f"llamacpp@{info.version}+{info.commit}"
    machine = MachineFacts(machine_id=args.machine, hostname="local", chip="",
                           ram_gb=0, platform=Platform.METAL)

    # ── pre-flight ambiental ──
    env_before = snapshot()
    required_gb = model.file_bytes / GiB + 2.0   # pesos + colchón KV/buffers
    pre = assess(env_before, None, required_gb)
    if pre.reasons:
        print("⚠ ENTORNO NO VÁLIDO:")
        for r in pre.reasons:
            print(f"   - {r}")
        if not args.force_env:
            print("   abortado (usa --force-env para correr igualmente: quedará valid=0)")
            store.log_action("cli.measure", "preflight_abort",
                             {"reasons": list(pre.reasons)})
            return 2
    for w in pre.warnings:
        print(f"⚠ aviso: {w}")

    corpus = RealCorpus(args.corpus_root or ["."]) if args.needles else None
    quality = LlamaCppCli(binary=args.cli_binary) if args.needles else None

    depths = [int(d) for d in args.depths.split(",")]
    print(f"\n{'depth':>6} {'decode t/s (med±σ)':>20} {'prefill t/s':>12} "
          f"{'needles':>8} {'válido':>7}")
    for depth in depths:
        cell = CellSpec(machine_id=args.machine, engine_id=engine_key,
                        model_id=args.name, ctx=args.ctx, depth_pct=depth, slots=1,
                        profile=LoadProfile.S, techniques=("flash_attn", "kv_q8"))
        run = bench.run_cell(cell, model, workdir=args.workdir, reps=args.reps)
        run.cell_key = cell_key(cell)

        # needles a profundidad (texto real, llama-cli)
        if quality and depth > 0:
            qrun = quality.run_cell(cell, model, corpus, workdir=args.workdir,
                                    reps=0, warmup=0, corpus_seed=args.seed)
            run.measurements += [m for m in qrun.measurements
                                 if m.metric == "needle_recall"]

        # ── post-flight: validez ──
        env_after = snapshot()
        report = assess(env_before, env_after, required_gb)
        run.valid = report.valid and not run.error
        run.interference = report.reasons

        cell.status = CellStatus.FAILED if run.error else CellStatus.OK
        store.save_cells([cell], campaign_id=args.campaign)
        store.save_run(run)
        store.log_action("cli.measure", "run_cell",
                         {"cell": run.cell_key, "valid": run.valid,
                          "interference": list(run.interference), "error": run.error})

        dec = [m.value for m in run.measurements if m.metric == "decode_tps"]
        pre_v = [m.value for m in run.measurements if m.metric == "prefill_tps"]
        ndl = [m.value for m in run.measurements if m.metric == "needle_recall"]
        if dec:
            sigma = statistics.stdev(dec) if len(dec) > 1 else 0.0
            print(f"{depth:>5}% {statistics.median(dec):>12.1f} ± {sigma:<5.2f} "
                  f"{statistics.median(pre_v) if pre_v else 0:>12.1f} "
                  f"{int(ndl[0]) if ndl else '-':>8} "
                  f"{'sí' if run.valid else 'NO':>7}")
        else:
            print(f"{depth:>5}%  ERROR: {run.error}")
    store.close()
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """Perfila una máquina (local o ssh) y la registra en BD. Coste ~0, sin modelos."""
    from .adapters.probes.host_profiler import profile_host
    from .adapters.runners.local import LocalRunner
    from .adapters.runners.ssh import SshRunner

    runner = SshRunner(host=args.ssh, user=args.user) if args.ssh else LocalRunner()
    profile = profile_host(runner, machine_id=args.machine_id)
    f = profile.facts
    print(f"máquina    : {f.machine_id} ({f.hostname})")
    print(f"chip       : {f.chip}  ·  RAM {f.ram_gb} GB  ·  {f.platform.value}")
    print(f"bandwidth  : {f.bandwidth_gbs or '?'} GB/s  ·  wired limit: "
          f"{f.wired_limit_gb or 'default(~2/3)'} GB  ·  budget GPU: {f.gpu_budget_gb:.1f} GB")
    print(f"SO         : {profile.os_name} {profile.arch}"
          + (f"  ·  GPU: {profile.gpu}" if profile.gpu else ""))
    print("engines    :")
    for name, info in (profile.engines or {}).items():
        print(f"  - {name:12s} {info['version'] or ''}  ({info['path']})")
    if not profile.engines:
        print("  (ninguno encontrado)")
    store = SqliteStore(args.db)
    store.save_machine(f, profile.to_facts_json())
    store.log_action("cli.probe", "machine_registered",
                     {"machine_id": f.machine_id, "via": "ssh" if args.ssh else "local"})
    store.close()
    print(f"\n✓ registrada en {args.db}")
    return 0


def cmd_check_updates(args: argparse.Namespace) -> int:
    """Política de Rubén: comprobar updates ANTES de una campaña, proponer y esperar
    aprobación humana. Este comando solo PROPONE — jamás ejecuta el upgrade."""
    from .adapters.runners.local import LocalRunner
    from .adapters.runners.ssh import SshRunner
    from .domain.maintenance import check_updates

    runner = SshRunner(host=args.ssh, user=args.user) if args.ssh else LocalRunner()
    proposals = check_updates(runner)
    if not proposals:
        print("✓ engines al día (brew). Nada que proponer.")
        return 0
    print("Updates disponibles — REQUIEREN TU APROBACIÓN (no se ejecuta nada):")
    for p in proposals:
        print(f"  - {p.component}: {p.current} → {p.latest}   [{p.command}]")
    print("\nSi apruebas, ejecuta tú el comando (o pídemelo explícitamente).")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="frontier_bench")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("probe", help="perfilar y registrar una máquina (local o --ssh)")
    pr.add_argument("--machine-id", required=True)
    pr.add_argument("--ssh", default=None, help="host remoto (red local o Tailscale)")
    pr.add_argument("--user", default="", help="usuario ssh")
    pr.add_argument("--db", default="data/frontier_bench_v2.db")
    pr.set_defaults(fn=cmd_probe)

    ui = sub.add_parser("ui", help="dashboard web local (stdlib, sin dependencias)")
    ui.add_argument("--port", type=int, default=4400)
    ui.add_argument("--db", default="data/frontier_bench_v2.db")
    ui.add_argument("--techniques", default="techniques.yaml")
    ui.set_defaults(fn=lambda a: __import__(
        "frontier_bench.adapters.web.server", fromlist=["serve"]
    ).serve(a.db, a.techniques, a.port))

    up = sub.add_parser("check-updates",
                        help="propone updates de engines (NUNCA ejecuta sin aprobación)")
    up.add_argument("--ssh", default=None)
    up.add_argument("--user", default="")
    up.set_defaults(fn=cmd_check_updates)
    m = sub.add_parser("measure", help="decode-at-depth (perfil S) con validez ambiental")
    m.add_argument("--model-file", required=True)
    m.add_argument("--name", required=True)
    m.add_argument("--machine", required=True)
    m.add_argument("--ctx", type=int, default=32768)
    m.add_argument("--depths", default="0,50,90")
    m.add_argument("--reps", type=int, default=3)
    m.add_argument("--arch", default="hybrid",
                   choices=["dense_gqa", "hybrid", "swa", "mla", "recurrent"])
    m.add_argument("--layers", type=int, default=32)
    m.add_argument("--kv-heads", type=int, default=4)
    m.add_argument("--head-dim", type=int, default=256)
    m.add_argument("--full-attn-layers", type=int, default=8)
    m.add_argument("--recurrent-mb", type=float, default=25.0)
    m.add_argument("--params-b", type=float, default=0.0)
    m.add_argument("--quant", default="Q4_K_S")
    m.add_argument("--ctx-native", type=int, default=262144)
    m.add_argument("--db", default="data/frontier_bench_v2.db")
    m.add_argument("--workdir", default="data/runs")
    m.add_argument("--campaign", default="f1-acceptance")
    m.add_argument("--seed", type=int, default=1234)
    m.add_argument("--bench-binary", default="llama-bench")
    m.add_argument("--cli-binary", default="llama-cli")
    m.add_argument("--corpus-root", action="append", default=None)
    m.add_argument("--needles", action="store_true", default=False)
    m.add_argument("--force-env", action="store_true", default=False)
    m.set_defaults(fn=cmd_measure)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
