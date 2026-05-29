# 03-DESIGN — Diseno Detallado de la Arquitectura

> Fase: Design | Estado: Draft
> Depende de: 02-SPEC.md
> Fecha: 2026-05-29

---

## 1. Arquitectura General

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLIENTE (Navegador)                        │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │Dashboard│ │Máquinas  │ │ Modelos  │ │Benchmarks│ │ Logs   │ │
│  └────┬────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘ │
│       └───────────┴────────────┴────────────┴────────────┘       │
│                          │  HTTP/SSE                              │
│                          ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    BACKEND (FastAPI)                         │  │
│  │  ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │  │
│  │  │Routers │ │ Services │ │  Worker  │ │  Report Generator│ │  │
│  │  │  REST  │ │ (logica) │ │Protocol  │ │  (MD/CSV/JSON)   │ │  │
│  │  └───┬────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘ │  │
│  │      └───────────┴────────────┴─────────────────┘            │  │
│  │                          │                                    │  │
│  │  ┌───────────────────────▼────────────────────────────────┐  │  │
│  │  │              SQLite + Action Log (WAL)                 │  │  │
│  │  │  machines │ models │ benchmark_results │ action_log    │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                          │  SSH                                   │
│                          ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              WORKER AGENT (en cada máquina objetivo)         │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │  │
│  │  │ Comando  │ │ llama-   │ │ mlx_lm   │ │ Progress     │  │  │
│  │  │ Router   │ │ cli exec │ │ bench    │ │ Reporter     │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## 2. Flujo de Datos: Benchmark

### 2.1 Diagrama de Secuencia

```
Usuario        Frontend          Backend              Worker Agent (SSH)
   │               │                │                        │
   │ Click "Run"   │                │                        │
   │──────────────>│                │                        │
   │               │ POST /api/benchmarks                    │
   │               │───────────────>│                        │
   │               │                │                        │
   │               │                │ 1. Generar action_id   │
   │               │                │ 2. INSERT action_log   │
   │               │                │    status=pending      │
   │               │                │ 3. COMMIT              │
   │               │                │                        │
   │               │                │ 4. UPDATE action_log   │
   │               │                │    status=running      │
   │               │                │                        │
   │               │                │ 5. ssh comando JSON    │
   │               │                │───────────────────────>│
   │               │                │                        │
   │               │   SSE stream   │                        │
   │               │<══════════════>│    progress events     │
   │               │                │<═══════════════════════│
   │  Live progress │               │                        │
   │<══════════════│                │                        │
   │               │                │                        │
   │               │                │ 6. ssh resultado JSON  │
   │               │                │<───────────────────────│
   │               │                │                        │
   │               │                │ 7. INSERT result       │
   │               │                │    benchmark_results   │
   │               │                │ 8. UPDATE action_log   │
   │               │                │    status=completed    │
   │               │                │ 9. COMMIT              │
   │               │                │                        │
   │  Resultado    │                │                        │
   │<──────────────│                │                        │
```

## 3. Componentes del Backend

### 3.1 database.py

```python
# Maneja conexion SQLite con WAL mode
# Migraciones automaticas al iniciar
# Context manager para sesiones atomicas

class AtomicAction:
    """Context manager para acciones atomicas con WAL pattern."""
    
    def __init__(self, db, action_type, resource_type=None, resource_id=None, request=None):
        self.action_id = str(uuid4())
        self.db = db
        
    def __enter__(self):
        # INSERT action_log con status=pending
        # COMMIT inmediato
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            # UPDATE action_log status=failed
            # COMMIT
        else:
            # UPDATE action_log status=completed
            # COMMIT
```

### 3.2 ssh_client.py

```python
class SSHClient:
    """Cliente SSH para comunicacion con Worker Agent."""
    
    def __init__(self, machine: Machine):
        self.host = machine.host
        self.port = machine.port
        self.user = machine.user
        self.key = machine.identity_file
    
    def execute(self, command: dict) -> Generator:
        """Envia comando JSON, recibe eventos SSE en vivo."""
        # Abre conexion SSH
        # Envia comando como JSON por stdin
        # Lee stdout linea por linea
        # Cada linea es un evento JSON
        # Yield eventos al caller
        # Timeout configurable por fase
    
    def test_connection(self) -> dict:
        """Verifica conectividad y detecta hardware."""
        # uptime, sysctl, which llama-cli, pip show mlx-lm
```

### 3.3 benchmark_service.py

```python
class BenchmarkService:
    """Orquesta la ejecucion de benchmarks."""

    def run(self, model_id, machine_id, config):
        with AtomicAction(db, "run_benchmark", "benchmark") as action:
            machine = get_machine(machine_id)
            model = get_model(model_id)
            
            # Construir comando segun engine
            command = self.build_command(model, config)
            
            # Ejecutar via SSH
            ssh = SSHClient(machine)
            for event in ssh.execute(command):
                # Cada evento: {"pct": 50, "message": "Generating..."}
                action.update_progress(event["pct"], event["message"])
                yield event  # SSE stream al frontend
            
            # Procesar resultado
            result = self.parse_result(event, model, machine, config)
            
            # Persistir
            db.insert_benchmark_result(result)
            return result
```

## 4. Componentes del Frontend

### 4.1 Estructura SPA (Vanilla JS)

```
app.js — Router + State manager
├── router() — Hash-based routing (#/machines, #/models, etc)
├── state — Observable state: machines[], models[], benchmarks[], logs[]
│   └── subscribe() — Patron observer para actualizar UI
├── api.js — Fetch wrapper con metodos para cada endpoint
│   ├── GET, POST, PATCH, DELETE
│   ├── Manejo de errores global
│   └── SSE client para streams en vivo
├── components/
│   ├── Layout — Header, nav, footer
│   ├── Dashboard — Tarjetas de resumen, ultimos benchmarks, activity feed
│   ├── Machines — Lista, formulario, detalle
│   ├── Models — Catalogo con busqueda y filtros
│   ├── BenchmarkWizard — Paso a paso (modelo → maquina → config → run)
│   ├── BenchmarkDetail — Progreso en vivo, resultado, logs
│   ├── Reports — Tablas comparativas, graficos
│   └── Logs — Action log con filtros
└── charts.js — Chart.js wrappers para graficos
```

### 4.2 CSS Framework

Sin framework externo pesado. CSS custom:
- CSS Grid para layout
- CSS Variables para theming
- Responsive: mobile-first con breakpoints
- Componentes: cards, tables, forms, badges, modals

## 5. Modelo de Datos (Pydantic)

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class MachineCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    user: str = "admin"
    identity_file: Optional[str] = None

class MachineResponse(MachineCreate):
    id: int
    chip: Optional[str]
    ram_gb: Optional[float]
    engines: List[str]
    status: str
    last_seen: Optional[datetime]
    created_at: datetime

class BenchmarkConfig(BaseModel):
    context_len: int = 16384
    kv_format: str = "q4_0"
    flash_attn: bool = True
    max_tokens: int = 256
    temperature: float = 0.0

class BenchmarkCreate(BaseModel):
    model_id: int
    machine_id: int
    config: BenchmarkConfig
    session_id: Optional[int]

class BenchmarkResult(BaseModel):
    id: int
    model_name: str
    machine_name: str
    engine: str
    decode_speed: Optional[float]
    prefill_speed: Optional[float]
    ram_peak_gb: Optional[float]
    status: str
    created_at: datetime

class ActionLogEntry(BaseModel):
    id: int
    action_id: str
    action_type: str
    status: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    progress_pct: float
    progress_message: Optional[str]
    error_message: Optional[str]
    duration_ms: Optional[float]
    created_at: datetime
```

## 6. Plan de Implementacion

### Fase 1: Fundacion (Prioridad Alta)
```
1. install.sh — Script de instalacion
2. backend/database.py — Conexion SQLite + schema + migraciones
3. backend/main.py — FastAPI basico con health check
4. Tablas: machines, models, action_log
5. API: POST/GET machines, GET action_log
6. Test local: curl a la API
```

### Fase 2: Core Benchmarking (Prioridad Alta)
```
7. backend/services/ssh_client.py — Conexion SSH
8. backend/worker_agent.py — Script para maquinas remotas
9. backend/services/benchmark_service.py — Ejecucion de benchmarks
10. Tabla: benchmark_results, benchmark_sessions, engine_logs
11. API: POST/GET benchmarks con SSE stream
12. Frontend: Dashboard + BenchmarkWizard
```

### Fase 3: Multi-Maquina (Prioridad Media)
```
13. backend/services/machine_service.py — Deteccion de hardware
14. backend/services/model_service.py — Escaneo de directorios
15. API: POST scan, GET models
16. Frontend: Machines page, Models catalog
```

### Fase 4: Reportes y Dashboard (Prioridad Media)
```
17. backend/services/report_service.py — Reportes comparativos
18. API: GET reports/summary, ranking, export
19. Frontend: Reports page con Chart.js
20. Frontend: Logs page con action log
```

### Fase 5: Pulido (Prioridad Baja)
```
21. docker-compose.yml
22. Manejo de errores mejorado
23. Tests automatizados
24. README actualizado con screenshots
25. Video demo / docs de usuario
```

## 7. Dependencias

### Python
```
fastapi
uvicorn
asyncssh              # SSH asincrono
sqlite3               # (stdlib)
pydantic
python-multipart      # Para formularios
```

### Frontend
```
Chart.js (CDN)        # Graficos
highlight.js (CDN)    # Resaltado de logs
```

### Sistema
```
bash >= 4.0
ssh
python3 >= 3.9
pip3
git
```
