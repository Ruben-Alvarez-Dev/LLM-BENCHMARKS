"""SQLite Writer — persistencia de resultados de tests.

Schema definido en el diseno del Benchmark Orchestrator:
- models: catalogo de modelos
- test_runs: resultados individuales
- errors: errores detallados
"""
import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict

from .test_executor import TestResult

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "benchmark_results.db"
)


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Obtiene conexion a la BD, crea el archivo y esquemas si no existen."""
    if db_path and db_path != ":memory:" and os.path.dirname(db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    """Crea las tablas si no existen."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            params_b REAL,
            architecture TEXT,
            attention TEXT,
            context_max INTEGER,
            quant TEXT,
            hardware TEXT DEFAULT "m1-mini-16gb"
        );

        CREATE TABLE IF NOT EXISTS test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER,
            hardware TEXT DEFAULT "m1-mini-16gb",
            context_len INTEGER,
            kv_format TEXT,
            flash_attn INTEGER,
            status TEXT,
            load_time_s REAL,
            decode_speed REAL,
            prefill_speed REAL,
            total_time_ms REAL,
            prompt_tokens INTEGER,
            generated_tokens INTEGER,
            ram_estimate_gb REAL,
            ram_model_gb REAL,
            ram_context_gb REAL,
            ram_total_observed_gb REAL,
            error TEXT,
            timestamp TEXT,
            FOREIGN KEY (model_id) REFERENCES models(id)
        );

        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            error_type TEXT,
            error_message TEXT,
            raw_output TEXT,
            FOREIGN KEY (run_id) REFERENCES test_runs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_runs_model ON test_runs(model_id);
        CREATE INDEX IF NOT EXISTS idx_runs_status ON test_runs(status);
        CREATE INDEX IF NOT EXISTS idx_runs_context ON test_runs(context_len);
    """)


def upsert_model(conn: sqlite3.Connection, model_name: str, params_b: float,
                 architecture: str, attention: str, context_max: int,
                 quant: str, hardware: str = "m1-mini-16gb") -> int:
    """Inserta o actualiza un modelo. Retorna su ID."""
    cur = conn.execute("""
        INSERT INTO models (name, params_b, architecture, attention, context_max, quant, hardware)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            params_b=excluded.params_b,
            architecture=excluded.architecture,
            attention=excluded.attention,
            context_max=excluded.context_max,
            quant=excluded.quant,
            hardware=excluded.hardware
    """, (model_name, params_b, architecture, attention, context_max, quant, hardware))
    conn.commit()
    row = conn.execute("SELECT id FROM models WHERE name = ?", (model_name,)).fetchone()
    return row["id"] if row else cur.lastrowid


def save_result(conn: sqlite3.Connection, result: TestResult) -> int:
    """Guarda un TestResult en la BD. Retorna el ID del test_run."""
    from .model_registry import get_model

    # Registrar modelo
    model_spec = get_model(result.model_name)
    quant_str = result.quant or "unknown"
    if model_spec:
        model_id = upsert_model(
            conn, model_spec.name, model_spec.params_b,
            model_spec.arch, model_spec.attn, model_spec.context_max, quant_str,
            result.hardware
        )
    else:
        model_id = upsert_model(
            conn, result.model_name, 0.0, "unknown", "unknown", 0, quant_str,
            result.hardware
        )

    # Registrar test run
    cur = conn.execute("""
        INSERT INTO test_runs
            (model_id, hardware, context_len, kv_format, flash_attn, status,
             load_time_s, decode_speed, prefill_speed, total_time_ms,
             prompt_tokens, generated_tokens,
             ram_estimate_gb, ram_model_gb, ram_context_gb, ram_total_observed_gb,
             error, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        model_id,
        result.hardware,
        result.context_len,
        result.kv_format,
        1 if result.flash_attn else 0,
        result.status,
        result.load_time_ms / 1000.0 if result.load_time_ms else None,
        result.decode_speed,
        result.prefill_speed,
        result.total_time_ms,
        result.prompt_tokens,
        result.generated_tokens,
        result.ram_estimate_gb,
        result.ram_model_gb,
        result.ram_context_gb,
        result.ram_total_observed_gb,
        result.error_message,
        result.timestamp,
    ))
    run_id = cur.lastrowid

    # Registrar error si existe
    if result.error_type:
        conn.execute("""
            INSERT INTO errors (run_id, error_type, error_message, raw_output)
            VALUES (?, ?, ?, ?)
        """, (
            run_id,
            result.error_type,
            result.error_message or "",
            result.raw_output[:2000] if result.raw_output else "",
        ))

    conn.commit()
    return run_id


def save_results_batch(conn: sqlite3.Connection, results: List[TestResult]) -> List[int]:
    """Guarda multiples resultados en una transaccion."""
    ids = []
    for r in results:
        ids.append(save_result(conn, r))
    return ids


def get_summary(conn: sqlite3.Connection) -> str:
    """Genera un resumen de todos los tests almacenados."""
    rows = conn.execute("""
        SELECT m.name, COUNT(*) as tests,
               SUM(CASE WHEN tr.status = 'ok' THEN 1 ELSE 0 END) as passed,
               ROUND(AVG(tr.decode_speed), 1) as avg_speed,
               MAX(tr.context_len) as max_ctx
        FROM test_runs tr
        JOIN models m ON tr.model_id = m.id
        GROUP BY m.name
        ORDER BY m.name
    """).fetchall()

    lines = ["# Summary - Benchmark Results", ""]
    for r in rows:
        lines.append(
            f"## {r['name']}: {r['passed']}/{r['tests']} passed, "
            f"avg {r['avg_speed'] or 'N/A'} tok/s, max ctx {r['max_ctx']}"
        )
    lines.append("")
    if not rows:
        lines.append("No tests recorded yet.")

    return "\n".join(lines)


def export_to_markdown(conn: sqlite3.Connection, model_name: Optional[str] = None) -> str:
    """Exporta resultados como tabla Markdown."""
    if model_name:
        rows = conn.execute("""
            SELECT m.name, tr.hardware, tr.context_len, tr.kv_format,
                   CASE WHEN tr.flash_attn THEN 'on' ELSE 'off' END as flash,
                   tr.decode_speed, tr.prefill_speed,
                   tr.ram_total_observed_gb, tr.ram_estimate_gb,
                   tr.status, tr.error
            FROM test_runs tr
            JOIN models m ON tr.model_id = m.id
            WHERE m.name = ?
            ORDER BY tr.context_len
        """, (model_name,)).fetchall()
        title = f"Benchmark: {model_name}"
    else:
        rows = conn.execute("""
            SELECT m.name, tr.hardware, tr.context_len, tr.kv_format,
                   CASE WHEN tr.flash_attn THEN 'on' ELSE 'off' END as flash,
                   tr.decode_speed, tr.prefill_speed,
                   tr.ram_total_observed_gb, tr.ram_estimate_gb,
                   tr.status, tr.error
            FROM test_runs tr
            JOIN models m ON tr.model_id = m.id
            ORDER BY m.name, tr.context_len
        """).fetchall()
        title = "Benchmark Results - All Models"

    lines = [
        f"# {title}",
        "",
        "| Model | Hardware | Context | KV Format | Flash | tok/s | Prefill tok/s | RAM obs | RAM est | Status | Error |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        decode = f"{r['decode_speed']:.1f}" if r['decode_speed'] else "-"
        prefill = f"{r['prefill_speed']:.1f}" if r['prefill_speed'] else "-"
        ram_obs = f"{r['ram_total_observed_gb']:.2f}" if r['ram_total_observed_gb'] else "-"
        ram_est = f"{r['ram_estimate_gb']:.2f}" if r['ram_estimate_gb'] else "-"
        ctx_k = f"{r['context_len'] // 1024}K"
        err = r['error'] or ""
        lines.append(
            f"| {r['name']} | {r['hardware']} | {ctx_k} | {r['kv_format']} | {r['flash']} "
            f"| {decode} | {prefill} | {ram_obs} | {ram_est} "
            f"| {r['status']} | {err} |"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    conn = get_connection()
    print(f"DB: {DEFAULT_DB_PATH}")
    print(get_summary(conn))
    conn.close()
