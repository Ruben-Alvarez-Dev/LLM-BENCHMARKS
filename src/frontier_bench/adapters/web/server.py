"""Servidor web FRONTIER BENCH — stdlib puro (http.server), cero dependencias.

Endpoints:
  GET /                  → SPA (static/index.html)
  GET /api/summary       → contadores globales
  GET /api/machines      → máquinas registradas (probe)
  GET /api/cells         → celdas + última medida decode
  GET /api/techniques    → enciclopedia (techniques.yaml)
  GET /api/events        → SSE: cola del action_log (tiempo real, canal por defecto)

Uso: PYTHONPATH=src python3 -m frontier_bench.cli ui --port 4400
"""
from __future__ import annotations

import json
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(__file__).parent / "static"


def _q(db: str, sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def make_handler(db_path: str, techniques_path: str):

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silenciar access log
            pass

        def _json(self, data, code=200):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = (STATIC / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/summary":
                cells = _q(db_path, "SELECT status, COUNT(*) n FROM cells GROUP BY status")
                runs = _q(db_path, "SELECT valid, COUNT(*) n FROM runs GROUP BY valid")
                self._json({
                    "cells": {r["status"]: r["n"] for r in cells},
                    "runs_valid": sum(r["n"] for r in runs if r["valid"]),
                    "runs_invalid": sum(r["n"] for r in runs if not r["valid"]),
                    "machines": len(_q(db_path, "SELECT machine_id FROM machines")),
                })
            elif self.path == "/api/machines":
                rows = _q(db_path, "SELECT * FROM machines ORDER BY machine_id")
                for r in rows:
                    r["facts"] = json.loads(r.pop("facts_json") or "{}")
                self._json(rows)
            elif self.path == "/api/cells":
                rows = _q(db_path, """
                    SELECT c.cell_key, c.machine_id, c.model_id, c.ctx, c.depth_pct,
                           c.slots, c.profile, c.protocol, c.status, c.skip_reason,
                           r.valid, r.error,
                           (SELECT ROUND(value,1) FROM measurements m
                            WHERE m.run_id=r.run_id AND m.metric='decode_tps'
                            ORDER BY m.id LIMIT 1) AS decode_tps
                    FROM cells c
                    LEFT JOIN runs r ON r.run_id =
                      (SELECT MAX(run_id) FROM runs WHERE cell_key=c.cell_key)
                    ORDER BY c.rowid DESC LIMIT 300""")
                self._json(rows)
            elif self.path == "/api/techniques":
                from .yaml_lite import load_blocks
                try:
                    text = Path(techniques_path).read_text()
                    self._json(load_blocks(text))
                except OSError:
                    self._json([])
            elif self.path == "/api/events":
                # SSE: cola del action_log (canal-agnóstico: esto es el adapter por defecto)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                last_id = 0
                rows = _q(db_path, "SELECT MAX(id) mx FROM action_log")
                last_id = (rows[0]["mx"] or 0) - 10  # arranca con los 10 últimos
                try:
                    while True:
                        rows = _q(db_path,
                                  "SELECT id, ts, actor, action, payload_json FROM action_log "
                                  "WHERE id > ? ORDER BY id LIMIT 50", (last_id,))
                        for r in rows:
                            last_id = r["id"]
                            self.wfile.write(
                                f"data: {json.dumps(r)}\n\n".encode())
                        self.wfile.flush()
                        time.sleep(2)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            elif self.path == "/api/run-queue":
                queued = _q(db_path,
                            "SELECT id, ts, payload_json FROM action_log "
                            "WHERE action='run_request_queued' ORDER BY id DESC LIMIT 50")
                consumed = {row["payload_json"] and __import__("json").loads(
                    row["payload_json"]).get("queued_id")
                    for row in _q(db_path, "SELECT payload_json FROM action_log "
                                           "WHERE action='run_request_consumed'")}
                for r in queued:
                    r["consumed"] = r["id"] in consumed
                self._json(queued)
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path == "/api/run-requests":
                # wizard: encola un RunRequest (mismo canal que MCP bench_run_request)
                length = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    return self._json({"error": "json inválido"}, 400)
                payload = {
                    "filters": {k: body.get(k) for k in
                                ("model", "machine", "ctx", "only_failed")
                                if body.get(k)},
                    "repeats": int(body.get("repeats", 1)),
                    "force": bool(body.get("force", False)),
                    "note": body.get("note", "via UI"),
                }
                conn = sqlite3.connect(db_path)
                conn.execute("INSERT INTO action_log (ts,actor,action,payload_json) "
                             "VALUES (datetime('now'),'ui','run_request_queued',?)",
                             (json.dumps(payload),))
                conn.commit()
                conn.close()
                self._json({"queued": True, "request": payload})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def serve(db_path: str, techniques_path: str, port: int = 4400) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port),
                                make_handler(db_path, techniques_path))
    print(f"\n  FRONTIER BENCH UI → http://localhost:{port}\n")
    httpd.serve_forever()
