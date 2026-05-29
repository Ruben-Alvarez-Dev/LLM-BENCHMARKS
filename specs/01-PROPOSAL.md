# 01-PROPOSAL — Vision y Propuesta General

> Fase: Proposal | Estado: Draft
> Fecha: 2026-05-29

---

## 1. Problema Actual

LLM-BENCHMARKS existe como un conjunto de:
- Scripts Python CLI (orchestrator)
- Archivos markdown con resultados
- BD SQLite local
- Procesos manuales via SSH a maquinas remotas

**Problemas concretos:**
- No hay interfaz para ver resultados sin CLI
- Agregar una maquina nueva requiere configuracion manual SSH
- No hay trazabilidad atomica de acciones
- Los benchmarks requieren conocimientos de los flags de llama-cli
- Comparar resultados entre maquinas requiere juntar archivos a mano
- No hay logging de que se hizo, cuando, por que, en que estado

## 2. Vision

Un solo comando de instalacion → una app web responsiva que da control total sobre:

1. **Deteccion y registro de maquinas** — hardware, engines, conectividad
2. **Catalogo de modelos vivo** — escaneo automatico de directorios locales y remotos
3. **Benchmark automatizado** — seleccion, ejecucion, monitoreo en vivo
4. **Dashboard comparativo** — graficos, rankings, exportacion
5. **Trazabilidad absoluta** — cada clic, cada accion, cada resultado queda registrado

## 3. Principios de Diseno

### 3.1 Atomic Logging (WAL Pattern)

Toda accion sigue este ciclo inmutable:

```
1. LOG: "voy a ejecutar X en Y con config Z" → se persiste en action_log
2. LOCK: se marca el recurso como "ocupado"
3. EXEC: se ejecuta la accion
4. LOG: "resultado: status, metricas, duracion" → se actualiza action_log
5. UNLOCK: se libera el recurso
```

Si el paso 3 falla (crash, timeout, disconnect):
- El action_log muestra exactamente donde fallo
- El estado del recurso queda como "error: <mensaje>"
- Nunca hay estado inconsistente

### 3.2 Machine-Agnostic Orchestration

El backend no ejecuta benchmarks localmente. Solo orquesta:
- Backend → API → Worker Agent (via SSH) → Maquina objetivo
- Cada maquina tiene su propio Worker Agent que recibe comandos y devuelve resultados
- El Backend mantiene cola de tareas por maquina

### 3.3 Progressive Enhancement

La app funciona en cualquier ordenador con navegador:
- Mobile: panel de monitoreo, notificaciones
- Tablet: dashboard, resultados
- Desktop: control total, configuracion, graficos

## 4. Componentes Principales

### 4.1 Installer (`install.sh`)
- Detecta OS, arquitectura, RAM, engines disponibles
- Clona el repo, instala dependencias (Python, Node si aplica)
- Crea la BD inicial, configura el primer host (localhost)
- Levanta el servidor web

### 4.2 Backend (FastAPI)
- API REST para todas las operaciones
- Motor de orquestacion (cola de tareas, ejecucion remota)
- Generador de reportes (Markdown, CSV, JSON)
- Logger atomico (WAL pattern)

### 4.3 Frontend (SPA)
- Dashboard con metricas en vivo
- Formularios para nueva maquina, nuevo benchmark
- Tablas comparativas con sorting/filtrado
- Graficos (velocidad vs contexto, RAM vs velocidad)
- Logs de actividad en tiempo real (Server-Sent Events)

### 4.4 Worker Agent (Script remoto)
- Se deploya via SSH a cada maquina objetivo
- Recibe comandos JSON, ejecuta, devuelve resultados JSON
- Reporta progreso en vivo
- Maneja timeouts, errores, desconexiones

## 5. Flujo de Usuario Tipico

```
1. Abre http://localhost:8540
2. Ve dashboard vacio con "Agregar maquina"
3. Agrega "Mac Mini M1" (local, detectado automaticamente)
4. Agrega "MacBook Pro M1 Max" (remoto, via SSH/Tailscale)
5. Ambas aparecen en "Maquinas" con su hardware detectado
6. Va a "Modelos" → escanea los directorios configurados
7. Aparecen Qwen3.5-4B, Qwen2.5-7B-1M, etc. con sus tamanos
8. Selecciona Qwen3.5-4B, elige "Mac Mini M1", config 16K q4_0
9. Click "Ejecutar Benchmark"
10. Ve progreso en vivo: "Cargando modelo...", "Prefill...", "Generando..."
11. Al terminar, el resultado aparece en la tabla comparativa
12. Va a "Reportes" → ve grafico: Qwen3.5-4B en MM vs MBP
13. Exporta a PDF o CSV
```

## 6. Metricas de Exito

| Metrica | Objetivo |
|---|---|
| Tiempo install → dashboard funcional | < 2 minutos |
| Agregar maquina remota | < 3 clicks |
| Ejecutar benchmark | < 5 clicks |
| Resultados visibles post-benchmark | < 1 segundo |
| Trazabilidad de acciones | 100% (toda accion en log atomico) |
| Sin estado inconsistente post-fallo | 100% (WAL pattern) |

## 7. Stack Tecnologico Propuesto

| Capa | Tecnologia |
|---|---|
| Backend | Python 3.9+ / FastAPI |
| Frontend | HTML+CSS+JS (SPA vanilla o React ligero) |
| BD | SQLite (WAL mode) |
| Orquestacion remota | SSH + subprocess con timeouts |
| Logging atomico | Tabla action_log con WAL pattern |
| Charts | Chart.js o similar (CDN) |
| Instalacion | Bash script (install.sh) |
| Contenedor | Docker opcional (docker-compose) |
