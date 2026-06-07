"""Adapter MCP — FRONTIER BENCH como servidor MCP por stdio (cero dependencias).

Tercera cara del hexágono (junto a la UI web y la CLI): el mismo dominio expuesto
como tools MCP para que MCP Lens lo renderice como un complemento más — y para que
cualquier agente pueda operar el banco de pruebas.

Protocolo: JSON-RPC 2.0 por líneas (stdio). Implementación mínima del subconjunto
MCP necesario: initialize, tools/list, tools/call, ping. Logs SIEMPRE a stderr.

Uso (MCP Lens / claude_desktop_config):
  command: python3, args: [-m, frontier_bench.adapters.mcp.server]
  env: PYTHONPATH=src, FRONTIER_BENCH_DB=data/frontier_bench_v2.db, cwd: LLM-BENCHMARKS
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

DB = os.environ.get("FRONTIER_BENCH_DB", "data/frontier_bench_v2.db")
TECHNIQUES = os.environ.get("FRONTIER_BENCH_TECHNIQUES", "techniques.yaml")


def _q(sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


# ───────────── tools ─────────────

def bench_summary(args: dict) -> dict:
    cells = {r["status"]: r["n"] for r in
             _q("SELECT status, COUNT(*) n FROM cells GROUP BY status")}
    runs = _q("SELECT valid, COUNT(*) n FROM runs GROUP BY valid")
    return {
        "machines": len(_q("SELECT machine_id FROM machines")),
        "cells_ok": cells.get("ok", 0),
        "cells_failed": cells.get("failed", 0),
        "cells_skipped": cells.get("skipped_budget", 0) + cells.get("skipped_unsupported", 0),
        "runs_validos": sum(r["n"] for r in runs if r["valid"]),
        "runs_invalidos": sum(r["n"] for r in runs if not r["valid"]),
    }


def bench_machines(args: dict) -> list[dict]:
    rows = _q("SELECT machine_id, hostname, chip, ram_gb, platform, "
              "wired_limit_gb, bandwidth_gbs, facts_json FROM machines")
    for r in rows:
        facts = json.loads(r.pop("facts_json") or "{}")
        r["engines"] = ", ".join(
            f"{k} {(v.get('version') or '').replace('version: ', '')}"
            for k, v in (facts.get("engines") or {}).items()) or "—"
    return rows


def bench_results(args: dict) -> list[dict]:
    sql = """SELECT c.cell_key, c.model_id, c.machine_id, c.ctx, c.depth_pct,
                    c.slots, c.profile, c.protocol, c.status, c.skip_reason,
                    r.valid,
                    (SELECT ROUND(value,1) FROM measurements m
                     WHERE m.run_id=r.run_id AND m.metric='decode_tps'
                     ORDER BY m.id LIMIT 1) AS decode_tps
             FROM cells c
             LEFT JOIN runs r ON r.run_id =
               (SELECT MAX(run_id) FROM runs WHERE cell_key=c.cell_key)
             WHERE 1=1"""
    params: list = []
    if args.get("model"):
        sql += " AND c.model_id LIKE ?"
        params.append(f"%{args['model']}%")
    if args.get("machine"):
        sql += " AND c.machine_id = ?"
        params.append(args["machine"])
    sql += " ORDER BY c.rowid DESC LIMIT ?"
    params.append(int(args.get("limit", 100)))
    return _q(sql, tuple(params))


def bench_rankings(args: dict) -> list[dict]:
    metric = args.get("metric", "decode_tps")
    rows = _q("""SELECT r.cell_key AS subject,
                        ROUND(AVG(m.value),1) AS valor_medio,
                        ROUND(MIN(m.value),1) AS min, ROUND(MAX(m.value),1) AS max,
                        COUNT(*) AS muestras
                 FROM measurements m JOIN runs r ON r.run_id=m.run_id
                 WHERE m.metric=? AND r.valid=1
                 GROUP BY r.cell_key ORDER BY valor_medio DESC LIMIT 25""", (metric,))
    return rows


def bench_techniques(args: dict) -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from frontier_bench.adapters.web.yaml_lite import load_blocks
    try:
        blocks = load_blocks(Path(TECHNIQUES).read_text())
    except OSError:
        return []
    return [{"id": b.get("id"), "purpose": b.get("purpose", ""),
             "not_for": b.get("not_for", ""),
             "soporta": ", ".join((b.get("supports") or {}).keys()),
             "avisos": ", ".join(b.get("warnings") or [])} for b in blocks]


def bench_action_log(args: dict) -> list[dict]:
    return _q("SELECT ts, actor, action, payload_json FROM action_log "
              "ORDER BY id DESC LIMIT ?", (int(args.get("limit", 30)),))


def bench_run_request(args: dict) -> dict:
    """Encola un RunRequest (selección granular). El executor (F3) lo consumirá;
    de momento queda registrado y visible — nada corre sin recursos ni aprobación."""
    payload = {"filters": {k: v for k, v in args.items()
                           if k in ("model", "machine", "ctx", "only_failed")},
               "repeats": int(args.get("repeats", 1)),
               "force": bool(args.get("force", False)),
               "note": args.get("note", "via MCP")}
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO action_log (ts,actor,action,payload_json) VALUES "
                 "(datetime('now'),'mcp','run_request_queued',?)",
                 (json.dumps(payload),))
    conn.commit()
    conn.close()
    return {"queued": True, "request": payload,
            "nota": "se ejecutará cuando el executor (F3) esté activo y el pre-flight ambiental lo permita"}


TOOLS = {
    "bench_summary": (bench_summary, "Estado global del banco: máquinas, celdas, runs válidos/inválidos", {}),
    "bench_machines": (bench_machines, "Máquinas registradas con hardware y engines detectados por el probe", {}),
    "bench_results": (bench_results, "Resultados (celdas+última medida). Filtros opcionales", {
        "model": {"type": "string"}, "machine": {"type": "string"},
        "limit": {"type": "number"}}),
    "bench_rankings": (bench_rankings, "Ranking por métrica sobre runs VÁLIDOS (default decode_tps)", {
        "metric": {"type": "string"}}),
    "bench_techniques": (bench_techniques, "Enciclopedia de técnicas: para qué sirve y para qué NO cada una", {}),
    "bench_action_log": (bench_action_log, "Trazabilidad: últimas acciones del banco", {
        "limit": {"type": "number"}}),
    "bench_run_request": (bench_run_request, "Encolar una petición de ejecución (selección granular, repeats, force)", {
        "model": {"type": "string"}, "machine": {"type": "string"},
        "repeats": {"type": "number"}, "force": {"type": "boolean"},
        "note": {"type": "string"}}),
}


# ───────────── JSON-RPC stdio ─────────────

def _reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    if error:
        msg["error"] = {"code": -32000, "message": str(error)}
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, id_ = req.get("method"), req.get("id")
        if method == "initialize":
            _reply(id_, {
                "protocolVersion": req["params"].get("protocolVersion", "2025-03-26"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "frontier-bench", "version": "2.0.0"}})
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            _reply(id_, {})
        elif method == "tools/list":
            tools = [{"name": name,
                      "description": desc,
                      "inputSchema": {"type": "object", "properties": props}}
                     for name, (_, desc, props) in TOOLS.items()]
            _reply(id_, {"tools": tools})
        elif method == "tools/call":
            name = req["params"]["name"]
            args = req["params"].get("arguments") or {}
            fn = TOOLS.get(name, (None,))[0]
            if fn is None:
                _reply(id_, error=f"tool desconocida: {name}")
                continue
            try:
                result = fn(args)
                _reply(id_, {"content": [{"type": "text",
                                          "text": json.dumps(result, ensure_ascii=False)}]})
            except Exception as e:  # noqa: BLE001
                _reply(id_, {"content": [{"type": "text", "text": f"error: {e}"}],
                             "isError": True})
        elif id_ is not None:
            _reply(id_, error=f"método no soportado: {method}")


if __name__ == "__main__":
    print("frontier-bench MCP server (stdio) listo", file=sys.stderr)
    main()
