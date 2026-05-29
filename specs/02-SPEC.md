# 02-SPEC — Especificacion Tecnica Detallada

> Fase: Spec | Estado: Draft
> Depende de: 01-PROPOSAL.md
> Fecha: 2026-05-29

---

## 1. Database Schema (Atomic Logging)

### 1.1 Tablas de Dominio

```sql
-- Maquinas registradas
CREATE TABLE machines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,          -- "Mac Mini M1", "MacBook Pro M1 Max"
    host TEXT NOT NULL,                 -- 100.77.1.20 o mac-mini.local
    port INTEGER DEFAULT 22,
    user TEXT DEFAULT 'admin',
    identity_file TEXT,                 -- ruta a clave SSH
    chip TEXT,                          -- Apple M1 (detectado)
    ram_gb REAL,                        -- 16.0 (detectado)
    disk_total_gb REAL,
    disk_free_gb REAL,
    engines TEXT,                       -- JSON: ["llama-cpp","mlx"]
    is_local INTEGER DEFAULT 0,         -- 1 si es localhost
    status TEXT DEFAULT 'offline',      -- online, offline, error
    last_seen TEXT,                     -- timestamp
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Modelos descubiertos (scan de directorios)
CREATE TABLE models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                  -- Qwen3.5-4B, Gemma-3-1B
    format TEXT NOT NULL,               -- gguf, safetensors (mlx)
    path TEXT NOT NULL,                  -- ruta absoluta en disco
    machine_id INTEGER REFERENCES machines(id),
    size_bytes INTEGER,                 -- tamano en disco
    params_b REAL,                      -- 4.0 para Qwen3.5-4B
    context_max INTEGER,                -- contexto maximo teorico
    quant TEXT,                         -- Q4_K_M, mlx-4bit, etc
    tags TEXT,                          -- JSON para metadatos extra
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(path, machine_id)
);

-- Benchmark results
CREATE TABLE benchmark_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER REFERENCES models(id),
    machine_id INTEGER REFERENCES machines(id),
    engine TEXT NOT NULL,                -- llama-cpp, mlx
    context_len INTEGER,
    kv_format TEXT,
    flash_attn INTEGER,
    quant TEXT,
    decode_speed REAL,                  -- tok/s
    prefill_speed REAL,                 -- tok/s
    prompt_tokens INTEGER,
    generated_tokens INTEGER,
    load_time_ms REAL,
    total_time_ms REAL,
    ram_peak_gb REAL,
    ram_estimate_gb REAL,
    status TEXT NOT NULL,               -- ok, oom, timeout, error
    error_message TEXT,
    raw_output TEXT,                    -- output completo del engine
    session_id INTEGER REFERENCES benchmark_sessions(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Sesiones de benchmark (agrupan runs)
CREATE TABLE benchmark_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,                           -- "Campana Qwen 2026-05-29"
    description TEXT,
    status TEXT DEFAULT 'pending',       -- pending, running, completed, failed
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### 1.2 Atomic Action Log (WAL Pattern)

```sql
-- Trazabilidad atomica de TODAS las acciones del sistema
CREATE TABLE action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,           -- scan_models, run_benchmark, add_machine, delete_model, etc
    action_id TEXT UNIQUE NOT NULL,      -- UUID v4 de esta accion (generado ANTES de ejecutar)
    status TEXT NOT NULL DEFAULT 'pending', -- pending, running, completed, failed, rolled_back
    resource_type TEXT,                  -- machine, model, benchmark, session
    resource_id INTEGER,                 -- ID del recurso afectado
    machine_id INTEGER REFERENCES machines(id),
    request JSON,                        -- parametros completos de la accion
    response JSON,                       -- resultado de la accion
    error_message TEXT,
    progress_pct REAL DEFAULT 0,          -- 0-100 para seguimiento en vivo
    progress_message TEXT,                -- "Cargando modelo...", "Generando..."
    duration_ms REAL,                    -- cuanto tardo
    parent_action_id TEXT,               -- para acciones hijas (benchmark → sub-benchmarks)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX idx_action_log_status ON action_log(status);
CREATE INDEX idx_action_log_resource ON action_log(resource_type, resource_id);
CREATE INDEX idx_action_log_created ON action_log(created_at);
```

### 1.3 Logs de Engine (output crudo)

```sql
-- Output crudo de los engines de inferencia
CREATE TABLE engine_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT REFERENCES action_log(action_id),
    machine_id INTEGER REFERENCES machines(id),
    engine TEXT NOT NULL,
    stream TEXT NOT NULL,               -- stdout, stderr
    line_number INTEGER,
    content TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## 2. API REST (FastAPI)

### 2.1 Endpoints de Maquinas

```
GET    /api/machines                    — Listar todas las maquinas
POST   /api/machines                    — Registrar nueva maquina
GET    /api/machines/:id                — Detalle de maquina
PATCH  /api/machines/:id                — Actualizar maquina
DELETE /api/machines/:id                — Eliminar maquina
POST   /api/machines/:id/test           — Test de conectividad SSH
POST   /api/machines/:id/scan           — Escanear directorios de modelos
GET    /api/machines/:id/models         — Modelos descubiertos en esa maquina
GET    /api/machines/:id/stats          — Estadisticas de la maquina
```

### 2.2 Endpoints de Modelos

```
GET    /api/models                      — Listar todos los modelos (con filtros)
GET    /api/models/:id                  — Detalle del modelo
DELETE /api/models/:id                  — Eliminar modelo del catalogo
POST   /api/models/:id/benchmark        — Programar benchmark para este modelo
GET    /api/models/:id/results          — Resultados de benchmark para este modelo
```

### 2.3 Endpoints de Benchmarks

```
POST   /api/benchmarks                  — Crear y ejecutar un benchmark
       Body: { model_id, machine_id, config: { context, kv_format, flash, ... } }
GET    /api/benchmarks/:id              — Estado y resultado del benchmark
GET    /api/benchmarks/:id/log          — Log en vivo del benchmark (SSE stream)
POST   /api/benchmarks/:id/cancel       — Cancelar benchmark en ejecucion
GET    /api/benchmarks                  — Listar benchmarks (con filtros)
DELETE /api/benchmarks/:id              — Eliminar un resultado
```

### 2.4 Endpoints de Sesiones

```
POST   /api/sessions                    — Crear nueva sesion de benchmark
GET    /api/sessions                    — Listar sesiones
GET    /api/sessions/:id                — Detalle de sesion
PATCH  /api/sessions/:id                — Actualizar sesion
POST   /api/sessions/:id/start          — Iniciar sesion
POST   /api/sessions/:id/cancel         — Cancelar sesion
```

### 2.5 Endpoints de Reportes

```
GET    /api/reports/summary             — Resumen global
GET    /api/reports/comparison          — Comparativa entre maquinas
       Query: ?machine_ids=1,2&model_id=3
GET    /api/reports/ranking             — Ranking de modelos por metrica
       Query: ?metric=decode_speed&limit=10
GET    /api/reports/export              — Exportar resultados
       Query: ?format=csv|json|md
```

### 2.6 Endpoints de Sistema

```
GET    /api/system/health               — Health check del servidor
GET    /api/system/info                 — Informacion del host
GET    /api/system/logs                 — Action log (con paginacion y filtros)
       Query: ?action_type=run_benchmark&status=completed&limit=50
GET    /api/system/discover             — Detectar hardware local y engines
```

## 3. Frontend Routes (SPA)

```
/                                    → Dashboard principal
/machines                            → Gestion de maquinas
/machines/:id                        → Detalle de maquina
/models                              → Catalogo de modelos
/models/:id                          → Detalle de modelo
/benchmarks                          → Benchmarks (activos e historicos)
/benchmarks/:id                      → Detalle/progreso de benchmark
/benchmarks/new                      → Nuevo benchmark (wizard)
/sessions                            → Sesiones de benchmark
/reports                             → Dashboard comparativo
/reports/ranking                     → Ranking de modelos
/reports/export                      → Exportar datos
/logs                                → Action log (trazabilidad)
/settings                            → Configuracion
```

## 4. Worker Agent Protocol

### 4.1 Acciones Soportadas

```json
// Request que el Backend envia via SSH
{
    "action": "benchmark",
    "action_id": "uuid-v4",
    "params": {
        "model_path": "/Users/local/.../model.gguf",
        "engine": "llama-cpp",
        "config": {
            "context_len": 16384,
            "kv_format": "q4_0",
            "flash_attn": true,
            "temperature": 0.0,
            "max_tokens": 256
        }
    }
}

// Response del Worker Agent
{
    "action_id": "uuid-v4",
    "status": "completed",
    "result": {
        "decode_speed": 13.2,
        "prefill_speed": 79.4,
        "prompt_tokens": 8192,
        "generated_tokens": 256,
        "load_time_ms": 5469.87,
        "total_time_ms": 41509.64,
        "ram_peak_gb": 9.86
    },
    "logs": [
        {"stream": "stdout", "line": 1, "content": "load_backend: loaded MTL backend..."},
        {"stream": "stdout", "line": 2, "content": "[Prompt: 79.4 t/s | Generation: 13.2 t/s]"}
    ],
    "duration_ms": 41509.64
}
```

### 4.2 Progreso en Vivo

```json
// Eventos SSE que el Worker Agent envia durante la ejecucion
{"event": "progress", "data": {"pct": 10, "message": "Loading model..."}}
{"event": "progress", "data": {"pct": 30, "message": "Prefilling prompt (8192 tokens)..."}}
{"event": "progress", "data": {"pct": 60, "message": "Generating (50/256 tokens)..."}}
{"event": "progress", "data": {"pct": 90, "message": "Measuring memory..."}}
{"event": "result", "data": {"decode_speed": 13.2, ...}}
{"event": "error", "data": {"message": "OOM: model requires 12GB but only 11GB available"}}
```

## 5. Sistema de Logging Atomico

### 5.1 Write-Ahead Log Pattern

Cada accion sigue este protocolo, implementado en el backend:

```
1. Generar action_id (UUID v4)
2. INSERT en action_log con status='pending', request=parametros
3. COMMIT (la accion ya esta registrada antes de empezar)
4. UPDATE action_log SET status='running', started_at=NOW()
5. Ejecutar la accion (via SSH o local)
6. UPDATE action_log SET status='completed', response=resultado, duration_ms=...
7. INSERT en tabla de dominio (benchmark_results, etc)
8. COMMIT final
```

Si el paso 5 falla:
```
5a. Capturar excepcion
5b. UPDATE action_log SET status='failed', error_message=..., completed_at=NOW()
5c. INSERT en tabla de dominio con status='error'
5d. COMMIT
```

### 5.2 Acciones Trackeadas Obligatoriamente

Toda accion de estas categorias DEBE pasar por action_log:

| Categoria | Acciones |
|---|---|
| Maquinas | register, update, delete, test_connection, scan_models |
| Modelos | discover, delete |
| Benchmarks | create, run, cancel, retry |
| Sesiones | create, start, complete, cancel |
| Export | report_generate, data_export |
| Sistema | install, upgrade, config_change |

## 6. Interfaz de Usuario

### 6.1 Dashboard Principal

```
┌─────────────────────────────────────────────────────┐
│  LLM BENCHMARKS                          [usuario]  │
├─────────────────────────────────────────────────────┤
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐              │
│  │ 2    │ │ 43   │ │ 156  │ │ 12   │              │
│  │Máqs  │ │Models│ │Tests │ │Pend. │              │
│  └──────┘ └──────┘ └──────┘ └──────┘              │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ Últimos Benchmarks                    [→]   │   │
│  │ ┌─────┬────────┬──────┬──────┬──────┬────┐ │   │
│  │ │Model│Máquina│t/s   │ Ctx  │ RAM  │Sta │ │   │
│  │ ├─────┼────────┼──────┼──────┼──────┼────┤ │   │
│  │ │Q3.5B│Mini    │60.1  │256K  │6.8GB │✅  │ │   │
│  │ │Q3.5B│MBP     │60.3  │256K  │6.8GB │✅  │ │   │
│  │ └─────┴────────┴──────┴──────┴──────┴────┘ │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ Activity Log (últimas 10)           [→]     │   │
│  │ 14:32  Benchmark Q3.5-4B → Mini ✅         │   │
│  │ 14:28  Benchmark Q3.5-4B → MBP  ✅         │   │
│  │ 14:20  Scan models → MBP       ✅ 142 found│   │
│  │ 14:15  Machine MBP online      ✅          │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 6.2 Wizard de Benchmark

```
Step 1: Select Model
  [Buscar modelo...]
  ☐ Qwen3.5-4B       2.7GB  GGUF  256K ctx
  ☐ Gemma-3-1B       1.3GB  MLX   32K ctx
  ☐ ...

Step 2: Select Machine
  ☐ Mac Mini M1     [online]  16GB RAM
  ☐ MacBook Pro M1  [online]  32GB RAM

Step 3: Configure
  Contexto: [16384] [32768] [65536] [131072] [262144]
  KV Format: [q4_0 ☑] [f16 ☐] [q8_0 ☐]
  Flash Attention: [on ☑] [off ☐]
  Generation tokens: [256]
  Temperature: [0.0]

Step 4: Review & Run
  → 20 tests a ejecutar en "Mac Mini M1"
  → Tiempo estimado: 5-15 minutos
  → RAM estimada: 4.7-6.8 GB
  [▲ Ejecutar ahora] [📅 Programar]
```

### 6.3 Dashboard Comparativo

```
┌─────────────────────────────────────────────────┐
│ Model: Qwen3.5-4B                                │
├─────────────────────────────────────────────────┤
│ ┌──── Speed vs Context ──────────────────────┐  │
│ │  ████████████████████  60.1 t/s @ 16K      │  │
│ │  ████████████████████  60.0 t/s @ 32K      │  │
│ │  ████████████████████  59.7 t/s @ 64K      │  │
│ │  ████████████████████  60.1 t/s @ 128K     │  │
│ │  ████████████████████  59.7 t/s @ 256K     │  │
│ └─────────────────────────────────────────────┘  │
│                                                  │
│ ┌── Mini vs MBP ────────────────────────────┐  │
│ │  Mini: ████████████████  13.2 t/s (7B-1M) │  │
│ │  MBP:  ██████████████████████████  47 t/s │  │
│ └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## 7. Esquema de Instalacion

### install.sh

```bash
#!/bin/bash
# 1. Detectar OS y arquitectura
# 2. Clonar repo (si no existe)
# 3. Instalar dependencias Python
# 4. Crear BD inicial
# 5. Detectar hardware local → registrar como maquina
# 6. Escanear directorios de modelos locales
# 7. Levantar servidor (uvicorn + frontend estatico)
# 8. Abrir navegador en http://localhost:8540
```

### docker-compose.yml (alternativa)

```yaml
services:
  app:
    build: .
    ports: ["8540:8540"]
    volumes:
      - ./data:/app/data          # BD persistente
      - /Users/local:/models:ro   # Modelos locales (opcional)
      - ~/.ssh:/home/app/.ssh:ro  # Claves SSH para maquinas remotas
```

## 8. Seguridad

- Las claves SSH se almacenan en la maquina host, no en la BD
- El Worker Agent solo acepta conexiones desde el Backend
- Cada accion tiene UUID unico para evitar replay
- Timeout configurable por accion (default: 5min para benchmark)
- Las maquinas remotas solo ejecutan comandos del Worker Agent, no shell arbitraria
- Logs de engine no incluyen prompts ni outputs de usuario (solo metricas)

## 9. Paginacion y Filtros

Toda lista GET soporta:

```
?page=1&per_page=50&sort=created_at&order=desc
&filter[status]=completed
&filter[machine_id]=1
&filter[created_at][gte]=2026-05-01
&filter[created_at][lte]=2026-05-29
```

## 10. Resumen de Archivos del Proyecto

```
LLM-BENCHMARKS/
├── install.sh                          # Instalacion 1-click
├── docker-compose.yml                  # Alternativa Docker
├── backend/
│   ├── main.py                         # FastAPI entry point
│   ├── database.py                     # SQLite connection + migrations
│   ├── models.py                       # Pydantic models
│   ├── routers/
│   │   ├── machines.py                 # /api/machines/*
│   │   ├── models_api.py               # /api/models/*
│   │   ├── benchmarks.py               # /api/benchmarks/*
│   │   ├── sessions.py                 # /api/sessions/*
│   │   ├── reports.py                  # /api/reports/*
│   │   └── system.py                   # /api/system/*
│   ├── services/
│   │   ├── machine_service.py          # Logica de maquinas
│   │   ├── model_service.py            # Escaneo y registro de modelos
│   │   ├── benchmark_service.py        # Ejecucion de benchmarks
│   │   ├── ssh_client.py               # Cliente SSH para Workers
│   │   ├── worker_protocol.py          # Protocolo Worker Agent
│   │   └── report_service.py           # Generacion de reportes
│   └── worker_agent.py                 # Script que se deploya en maquinas remotas
├── frontend/
│   ├── index.html                      # SPA entry point
│   ├── css/
│   │   └── app.css
│   ├── js/
│   │   ├── app.js                      # Router + state
│   │   ├── api.js                      # API client
│   │   ├── components/
│   │   │   ├── dashboard.js
│   │   │   ├── machines.js
│   │   │   ├── models.js
│   │   │   ├── benchmarks.js
│   │   │   ├── reports.js
│   │   │   └── logs.js
│   │   └── charts.js                   # Graficos (Chart.js)
│   └── templates/                      # HTML parcial
├── data/
│   └── benchmark.db                    # SQLite
├── docs/                               # Docs existentes (se mantienen)
├── engines/                            # Orchestrator existente (se mantiene como referencia)
├── models/
│   └── STATUS.md
├── scripts/
│   └── run-benchmark.sh
├── specs/
│   ├── 01-PROPOSAL.md
│   ├── 02-SPEC.md
│   └── 03-DESIGN.md
├── .gitignore
├── LICENSE
└── README.md
```
