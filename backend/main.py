"""LLM-BENCHMARKS — FastAPI Application

Entry point del servidor web. Inicializa BD, registra routers, y levanta API.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import subprocess
import platform

from backend.database import get_connection, init_db, AtomicAction, get_action_log
from backend.models import MachineCreate, MachineResponse, ActionLogEntry, BenchmarkResult

app = FastAPI(
    title="LLM-BENCHMARKS",
    description="Benchmark suite for local LLM inference on Apple Silicon",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    """Inicializa BD al arrancar."""
    init_db()


# ─── System ─────────────────────────────────────────────────────────

@app.get("/api/system/health")
def health():
    return {"status": "ok", "timestamp": __import__("datetime").datetime.utcnow().isoformat()}


@app.get("/api/system/info")
def system_info():
    """Informacion del host donde corre el servidor."""
    import multiprocessing
    return {
        "hostname": platform.node(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "system": platform.system(),
        "ram_gb": round(os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / (1024**3), 1)
            if hasattr(os, 'sysconf') else None,
        "cpu_count": multiprocessing.cpu_count(),
        "python": sys.version,
    }


@app.get("/api/system/logs")
def action_logs(
    action_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0)
):
    """Consulta el action log con filtros."""
    db = get_connection()
    logs = get_action_log(db, action_type, status, resource_type, limit, offset)
    db.close()
    return {"logs": logs, "total": len(logs), "limit": limit, "offset": offset}


# ─── Machines ────────────────────────────────────────────────────────

@app.get("/api/machines")
def list_machines():
    db = get_connection()
    rows = db.execute("SELECT * FROM machines ORDER BY name").fetchall()
    db.close()
    return {"machines": [dict(r) for r in rows]}


@app.post("/api/machines", status_code=201)
def create_machine(machine: MachineCreate):
    db = get_connection()
    with AtomicAction(db, "register_machine", "machine", request=machine.dict()):
        try:
            cur = db.execute("""
                INSERT INTO machines (name, host, port, user, identity_file)
                VALUES (?, ?, ?, ?, ?)
            """, (machine.name, machine.host, machine.port, machine.user, machine.identity_file))
            db.commit()
            machine_id = cur.lastrowid
            return {"id": machine_id, "name": machine.name, "status": "registered"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/machines/{machine_id}")
def get_machine(machine_id: int):
    db = get_connection()
    row = db.execute("SELECT * FROM machines WHERE id=?", (machine_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Machine not found")
    return dict(row)


@app.delete("/api/machines/{machine_id}", status_code=204)
def delete_machine(machine_id: int):
    db = get_connection()
    with AtomicAction(db, "delete_machine", "machine", resource_id=machine_id):
        db.execute("DELETE FROM machines WHERE id=?", (machine_id,))
        db.execute("DELETE FROM models WHERE machine_id=?", (machine_id,))
        db.commit()
    db.close()


# ─── Models ──────────────────────────────────────────────────────────

@app.get("/api/models")
def list_models(machine_id: Optional[int] = Query(None), format: Optional[str] = Query(None)):
    db = get_connection()
    where = []
    params = []
    if machine_id:
        where.append("m.machine_id = ?")
        params.append(machine_id)
    if format:
        where.append("m.format = ?")
        params.append(format)
    where_clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = db.execute(f"""
        SELECT m.*, mac.name as machine_name
        FROM models m
        LEFT JOIN machines mac ON m.machine_id = mac.id
        {where_clause}
        ORDER BY m.name
    """, params).fetchall()
    db.close()
    return {"models": [dict(r) for r in rows]}


# ─── Benchmarks ─────────────────────────────────────────────────────

@app.get("/api/benchmarks")
def list_benchmarks(
    model_id: Optional[int] = Query(None),
    machine_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200)
):
    db = get_connection()
    where = []
    params = []
    if model_id:
        where.append("br.model_id = ?")
        params.append(model_id)
    if machine_id:
        where.append("br.machine_id = ?")
        params.append(machine_id)
    if status:
        where.append("br.status = ?")
        params.append(status)
    where_clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = db.execute(f"""
        SELECT br.*, mo.name as model_name, ma.name as machine_name
        FROM benchmark_results br
        LEFT JOIN models mo ON br.model_id = mo.id
        LEFT JOIN machines ma ON br.machine_id = ma.id
        {where_clause}
        ORDER BY br.created_at DESC
        LIMIT ?
    """, params + [limit]).fetchall()
    db.close()
    return {"benchmarks": [dict(r) for r in rows]}


@app.get("/api/benchmarks/summary")
def benchmark_summary():
    """Resumen global: totales por maquina y estado."""
    db = get_connection()
    rows = db.execute("""
        SELECT
            ma.name as machine_name,
            COUNT(br.id) as total_tests,
            SUM(CASE WHEN br.status = 'ok' THEN 1 ELSE 0 END) as passed,
            ROUND(AVG(br.decode_speed), 1) as avg_speed,
            MAX(br.context_len) as max_context
        FROM benchmark_results br
        JOIN machines ma ON br.machine_id = ma.id
        GROUP BY ma.name
        ORDER BY ma.name
    """).fetchall()
    db.close()
    return {"summary": [dict(r) for r in rows]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8540)
