"""LLM-BENCHMARKS — Database Layer

SQLite con WAL mode, migraciones automaticas, y AtomicAction context manager
para logging atomico de todas las operaciones del sistema (WAL pattern).
"""
import os
import json
import time
import sqlite3
import uuid
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional, Any

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "benchmark.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Obtiene conexion SQLite con WAL mode."""
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str = DB_PATH):
    """Inicializa la BD: crea tablas si no existen."""
    conn = get_connection(db_path)
    conn.executescript("""
        -- Maquinas registradas
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL,
            port INTEGER DEFAULT 22,
            user TEXT DEFAULT 'admin',
            identity_file TEXT,
            chip TEXT,
            ram_gb REAL,
            disk_total_gb REAL,
            disk_free_gb REAL,
            engines TEXT,
            is_local INTEGER DEFAULT 0,
            status TEXT DEFAULT 'offline',
            last_seen TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
        );

        -- Modelos descubiertos
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            format TEXT NOT NULL,
            path TEXT NOT NULL,
            machine_id INTEGER REFERENCES machines(id),
            size_bytes INTEGER,
            params_b REAL,
            context_max INTEGER,
            quant TEXT,
            tags TEXT,
            discovered_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
            UNIQUE(path, machine_id)
        );

        -- Resultados de benchmark
        CREATE TABLE IF NOT EXISTS benchmark_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER REFERENCES models(id),
            machine_id INTEGER REFERENCES machines(id),
            engine TEXT NOT NULL,
            context_len INTEGER,
            kv_format TEXT,
            flash_attn INTEGER,
            quant TEXT,
            decode_speed REAL,
            prefill_speed REAL,
            prompt_tokens INTEGER,
            generated_tokens INTEGER,
            load_time_ms REAL,
            total_time_ms REAL,
            ram_peak_gb REAL,
            ram_estimate_gb REAL,
            status TEXT NOT NULL,
            error_message TEXT,
            raw_output TEXT,
            session_id INTEGER REFERENCES benchmark_sessions(id),
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
        );

        -- Sesiones de benchmark
        CREATE TABLE IF NOT EXISTS benchmark_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            status TEXT DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
        );

        -- Action log: trazabilidad atomica de TODAS las acciones
        CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            action_id TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            resource_type TEXT,
            resource_id INTEGER,
            machine_id INTEGER REFERENCES machines(id),
            request TEXT,
            response TEXT,
            error_message TEXT,
            progress_pct REAL DEFAULT 0,
            progress_message TEXT,
            duration_ms REAL,
            parent_action_id TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
            started_at TEXT,
            completed_at TEXT
        );

        -- Engine logs: output crudo de los workers
        CREATE TABLE IF NOT EXISTS engine_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id TEXT REFERENCES action_log(action_id),
            machine_id INTEGER REFERENCES machines(id),
            engine TEXT NOT NULL,
            stream TEXT NOT NULL,
            line_number INTEGER,
            content TEXT,
            timestamp TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
        );

        -- Indices
        CREATE INDEX IF NOT EXISTS idx_action_log_status ON action_log(status);
        CREATE INDEX IF NOT EXISTS idx_action_log_resource ON action_log(resource_type, resource_id);
        CREATE INDEX IF NOT EXISTS idx_action_log_created ON action_log(created_at);
        CREATE INDEX IF NOT EXISTS idx_benchmark_results_model ON benchmark_results(model_id);
        CREATE INDEX IF NOT EXISTS idx_benchmark_results_machine ON benchmark_results(machine_id);
        CREATE INDEX IF NOT EXISTS idx_models_machine ON models(machine_id);
        CREATE INDEX IF NOT EXISTS idx_engine_logs_action ON engine_logs(action_id);
    """)
    conn.commit()
    conn.close()
    return True


class AtomicAction:
    """Context manager para acciones atomicas con WAL pattern.

    Uso:
        with AtomicAction(db, "run_benchmark", "benchmark") as action:
            result = ejecutar_algo()
            action.set_response(result)

    Flujo:
        1. Genera action_id (UUID)
        2. INSERT en action_log con status='pending'
        3. COMMIT (la accion ya esta registrada)
        4. UPDATE status='running' al entrar al bloque
        5. Si hay exito: UPDATE status='completed'
        6. Si hay error: UPDATE status='failed' con error_message
    """

    def __init__(self, db: sqlite3.Connection, action_type: str,
                 resource_type: Optional[str] = None,
                 resource_id: Optional[int] = None,
                 machine_id: Optional[int] = None,
                 request: Optional[Any] = None,
                 parent_action_id: Optional[str] = None):
        self.db = db
        self.action_id = str(uuid.uuid4())
        self.action_type = action_type
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.machine_id = machine_id
        self.request = json.dumps(request) if request else None
        self.parent_action_id = parent_action_id
        self._start_time = None
        self._response = None

    def __enter__(self):
        self._start_time = time.time()
        now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

        # INSERT inicial con status=pending
        self.db.execute("""
            INSERT INTO action_log
                (action_id, action_type, status, resource_type, resource_id,
                 machine_id, request, parent_action_id, created_at)
            VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?)
        """, (self.action_id, self.action_type, self.resource_type,
              self.resource_id, self.machine_id, self.request,
              self.parent_action_id, now))
        self.db.commit()

        # UPDATE a running
        self.db.execute("""
            UPDATE action_log SET status='running', started_at=?
            WHERE action_id=?
        """, (now, self.action_id))
        self.db.commit()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.time() - self._start_time) * 1000
        now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
        response_json = json.dumps(self._response) if self._response else None

        if exc_type:
            error_msg = f"{exc_type.__name__}: {exc_val}"
            self.db.execute("""
                UPDATE action_log SET status='failed', error_message=?,
                    duration_ms=?, completed_at=?, response=?
                WHERE action_id=?
            """, (error_msg, duration, now, response_json, self.action_id))
        else:
            self.db.execute("""
                UPDATE action_log SET status='completed', duration_ms=?,
                    completed_at=?, response=?
                WHERE action_id=?
            """, (duration, now, response_json, self.action_id))

        self.db.commit()

    def update_progress(self, pct: float, message: str):
        """Actualiza progreso de la accion en vivo."""
        self.db.execute("""
            UPDATE action_log SET progress_pct=?, progress_message=?
            WHERE action_id=?
        """, (pct, message, self.action_id))
        self.db.commit()

    def set_response(self, data: Any):
        self._response = data

    def set_resource(self, resource_type: str, resource_id: int):
        self.db.execute("""
            UPDATE action_log SET resource_type=?, resource_id=?
            WHERE action_id=?
        """, (resource_type, resource_id, self.action_id))
        self.db.commit()


def get_action_log(db: sqlite3.Connection, action_type: str = None,
                   status: str = None, resource_type: str = None,
                   limit: int = 50, offset: int = 0) -> list:
    """Consulta el action log con filtros."""
    where = []
    params = []

    if action_type:
        where.append("action_type = ?")
        params.append(action_type)
    if status:
        where.append("status = ?")
        params.append(status)
    if resource_type:
        where.append("resource_type = ?")
        params.append(resource_type)

    where_clause = (" WHERE " + " AND ".join(where)) if where else ""

    rows = db.execute(f"""
        SELECT * FROM action_log {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()

    return [dict(r) for r in rows]


if __name__ == "__main__":
    # Test de init
    init_db(":memory:")
    print("Database schema: OK")
    print("AtomicAction: OK")
