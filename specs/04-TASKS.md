# 04-TASKS — Plan de Trabajo Detallado

> Fase: Tasks | Estado: Draft
> Depende de: 03-DESIGN.md
> Fecha: 2026-05-29

---

## Fase 1: Fundacion (Prioridad Alta)

### T-01: install.sh
**Archivo:** `install.sh`
**Dependencias:** Ninguna
**Estimacion:** 2h
**Descripcion:** Script bash de instalacion 1-click.
- Detecta SO y arquitectura (`uname`, `sysctl`)
- Verifica dependencias (python3, pip3, git, ssh)
- Clona repo si no existe (`git clone`)
- Crea virtualenv e instala requirements
- Inicializa BD (corre `backend/main.py --init-db`)
- Detecta hardware local → registra como maquina
- Escanea directorios por defecto de modelos
- Arranca servidor (`uvicorn backend.main:app --port 8540`)
- Abre navegador (`open http://localhost:8540`)

### T-02: Database + Schema
**Archivos:** `backend/database.py`
**Dependencias:** T-01
**Estimacion:** 3h
**Descripcion:** Conexion SQLite, WAL mode, migraciones automaticas.
- `get_connection()` con WAL mode
- `run_migrations()` — crea tablas si no existen
- `AtomicAction` context manager (WAL pattern: pending → running → completed/failed)
- Schema completo: machines, models, benchmark_results, benchmark_sessions, action_log, engine_logs
- Indices para queries comunes

### T-03: Backend Core + Health
**Archivos:** `backend/main.py`, `backend/__init__.py`, `requirements.txt`
**Dependencias:** T-02
**Estimacion:** 2h
**Descripcion:** FastAPI basico con routers.
- Estructura de routers y services
- `GET /api/system/health` → ok
- `GET /api/system/info` → hostname, chip, RAM, disk
- CORS habilitado
- Error handlers globales
- Logger estructurado

### T-04: Models Pydantic
**Archivo:** `backend/models.py`
**Dependencias:** T-02
**Estimacion:** 1h
**Descripcion:** Todos los modelos Pydantic para request/response.
- MachineCreate, MachineResponse
- ModelResponse
- BenchmarkConfig, BenchmarkCreate, BenchmarkResult
- ActionLogEntry
- SessionCreate, SessionResponse
- Pagination, Filters
- ReportSummary, RankingEntry

### T-05: API Machines (CRUD)
**Archivos:** `backend/routers/machines.py`, `backend/services/machine_service.py`
**Dependencias:** T-03, T-04
**Estimacion:** 3h
**Descripcion:** CRUD completo de maquinas.
- `GET /api/machines` — lista paginada
- `POST /api/machines` — registrar nueva
- `GET /api/machines/:id` — detalle
- `PATCH /api/machines/:id` — actualizar
- `DELETE /api/machines/:id` — eliminar
- `POST /api/machines/:id/test` — test SSH + detectar hardware
- Cada operacion usa AtomicAction

### T-06: API Action Log
**Archivos:** `backend/routers/system.py`
**Dependencias:** T-02
**Estimacion:** 1h
**Descripcion:** Endpoint para consultar action_log.
- `GET /api/system/logs` — paginado, con filtros por action_type, status, resource_type
- `GET /api/system/logs/:action_id` — detalle de accion

---

## Fase 2: Core Benchmarking (Prioridad Alta)

### T-07: SSH Client
**Archivo:** `backend/services/ssh_client.py`
**Dependencias:** T-05
**Estimacion:** 3h
**Descripcion:** Cliente SSH asincrono.
- `test_connection()` — verifica SSH, uptime, detecta hardware
- `execute(command, timeout)` — envia JSON, recibe eventos linea a linea
- Timeout por fase configurable
- Reconexion automatica
- Manejo de errores: timeout, connection refused, auth failure

### T-08: Worker Agent
**Archivo:** `backend/worker_agent.py`
**Dependencias:** T-07
**Estimacion:** 3h
**Descripcion:** Script que se deploya en cada maquina objetivo.
- Lee comando JSON de stdin
- Envia eventos de progreso por stdout (lineas JSON)
- Soporta acciones: `benchmark`, `scan_models`, `detect_hardware`, `test`
- Para `benchmark`: llama-cli o mlx_lm.benchmark segun engine
- Timeout por fase (carga 60s, prefill 120s, generacion 120s)
- Reporta RAM peak via memory_profiler o psutil
- En logs de engine linea a linea

### T-09: Benchmark Service
**Archivo:** `backend/services/benchmark_service.py`
**Dependencias:** T-07, T-08
**Estimacion:** 4h
**Descripcion:** Orquestacion de benchmarks.
- `run(model_id, machine_id, config)` con AtomicAction
- Construye comando JSON para Worker Agent
- Procesa eventos SSE en vivo
- Parsea resultado y persiste en BD
- Maneja OOM, timeout, error
- `cancel(action_id)` — mata proceso remoto
- `retry(action_id)` — re-ejecuta con misma config

### T-10: API Benchmarks
**Archivos:** `backend/routers/benchmarks.py`
**Dependencias:** T-09
**Estimacion:** 3h
**Descripcion:** Endpoints de benchmark.
- `POST /api/benchmarks` — crear + ejecutar (o sesion)
- `GET /api/benchmarks/:id` — estado + resultado
- `GET /api/benchmarks/:id/log` — SSE stream en vivo
- `POST /api/benchmarks/:id/cancel` — cancelar
- `GET /api/benchmarks` — listar con filtros
- `DELETE /api/benchmarks/:id` — eliminar
- `POST /api/benchmarks/:id/retry` — re-ejecutar

### T-11: Frontend — Dashboard
**Archivos:** `frontend/index.html`, `frontend/js/app.js`, `frontend/js/api.js`, `frontend/js/components/dashboard.js`, `frontend/css/app.css`
**Dependencias:** T-10
**Estimacion:** 4h
**Descripcion:** SPA basica con dashboard.
- Router hash-based
- State manager con observables
- API client con fetch + SSE
- Dashboard: tarjetas de resumen (maquinas, modelos, tests), ultimos benchmarks, activity feed
- Layout responsive con navegacion

### T-12: Frontend — BenchmarkWizard
**Archivos:** `frontend/js/components/benchmarks.js`
**Dependencias:** T-11
**Estimacion:** 3h
**Descripcion:** Wizard paso a paso para crear benchmarks.
- Paso 1: Seleccionar modelo (busqueda + filtros)
- Paso 2: Seleccionar maquina (con estado online/offline)
- Paso 3: Configurar (contexto, kv, flash, tokens, temp)
- Paso 4: Revisar y ejecutar
- Pantalla de progreso en vivo (barra + mensajes)
- Resultado al completar

---

## Fase 3: Multi-Maquina (Prioridad Media)

### T-13: Machine Detection + Scan
**Archivos:** `backend/services/machine_service.py`, `backend/services/model_service.py`
**Dependencias:** T-07, T-08
**Estimacion:** 3h
**Descripcion:** Deteccion de hardware y escaneo de modelos.
- `detect_hardware(ssh)` → chip, RAM, disk, engines, OS
- `scan_models(ssh, paths)` → busca GGUFs y safetensors en directorios
- Directorios por defecto: `.lmstudio/models/`, `Jart-OS-*/models/`, `huggingface/models/`
- Extrae metadata: formato, tamano, nombre, cuantizacion

### T-14: API Models
**Archivos:** `backend/routers/models_api.py`
**Dependencias:** T-13
**Estimacion:** 2h
**Descripcion:** Endpoints de modelos.
- `GET /api/models` — listar con filtros (formato, maquina, tamano)
- `GET /api/models/:id` — detalle
- `DELETE /api/models/:id` — eliminar del catalogo
- `POST /api/models/:id/benchmark` — shortcut para benchmark directo

### T-15: Frontend — Machines + Models
**Archivos:** `frontend/js/components/machines.js`, `frontend/js/components/models.js`
**Dependencias:** T-14
**Estimacion:** 3h
**Descripcion:** Paginas de gestion de maquinas y modelos.
- Machines: lista, agregar (formulario), detalle (hardware, engines, estado)
- Models: catalogo con busqueda, filtros (formato, maquina), sorting
- Boton "Benchmark" directo desde la lista de modelos
- Indicador de estado online/offline

---

## Fase 4: Reportes y Dashboard (Prioridad Media)

### T-16: Report Service
**Archivo:** `backend/services/report_service.py`
**Dependencias:** T-10
**Estimacion:** 3h
**Descripcion:** Generacion de reportes y exportacion.
- `summary()` — resumen global
- `comparison(machine_ids, model_id)` — comparativa entre maquinas
- `ranking(metric, limit)` — ranking de modelos por metrica
- `export(format)` — exportar a CSV, JSON, Markdown

### T-17: API Reports
**Archivos:** `backend/routers/reports.py`
**Dependencias:** T-16
**Estimacion:** 2h
**Descripcion:** Endpoints de reportes.
- `GET /api/reports/summary`
- `GET /api/reports/comparison?machine_ids=1,2&model_id=3`
- `GET /api/reports/ranking?metric=decode_speed&limit=10`
- `GET /api/reports/export?format=csv`

### T-18: Frontend — Reports + Charts
**Archivos:** `frontend/js/components/reports.js`, `frontend/js/charts.js`
**Dependencias:** T-17
**Estimacion:** 4h
**Descripcion:** Dashboard comparativo con graficos.
- Tabla comparativa maquina vs maquina
- Grafico velocidad vs contexto (Chart.js)
- Grafico RAM vs velocidad
- Ranking de modelos (top 10)
- Export button
- Logs page con action log filtrable

---

## Fase 5: Pulido (Prioridad Baja)

### T-19: Docker Setup
**Archivos:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`
**Dependencias:** T-10
**Estimacion:** 2h

### T-20: Tests
**Archivos:** `tests/`
**Dependencias:** T-10
**Estimacion:** 4h

### T-21: Error Handling + UX
**Archivos:** Varios
**Dependencias:** T-18
**Estimacion:** 2h

### T-22: README + Docs
**Archivos:** `README.md`
**Dependencias:** T-21
**Estimacion:** 2h

---

## Resumen de Tareas

| Fase | Tareas | Horas est. |
|---|---|---|
| F1: Fundacion | T-01 a T-06 | 12h |
| F2: Core Benchmarking | T-07 a T-12 | 20h |
| F3: Multi-Maquina | T-13 a T-15 | 8h |
| F4: Reportes | T-16 a T-18 | 9h |
| F5: Pulido | T-19 a T-22 | 10h |
| **Total** | **22 tareas** | **~59h** |
