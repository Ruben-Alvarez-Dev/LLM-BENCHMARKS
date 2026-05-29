# Benchmark Orchestrator — Diseno del Sistema de Pruebas Controladas

> Fecha: 2026-05-29
> Hardware: Mac Mini M1 16GB + NVMe 4TB TB3
> Motor principal: llama-cli v8880 (Homebrew, ggml 0.10.0, Metal)
> Proposito: Sistema automatizado-controlado para certificar modelos de inferencia local
> con maximo contexto mantenido y tecnicas de optimizacion (Flash Attention, PlanarQuant,
> IsoQuant, Speculative Decoding, MLA).

---

## 1. Arquitectura del Sistema

```
┌──────────────────────────────────────────────────────────────┐
│                   BENCHMARK ORCHESTRATOR                      │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │ Model       │→ │ Test Matrix  │→ │ RAM Budget       │    │
│  │ Registry    │  │ Generator    │  │ Calculator       │    │
│  └─────────────┘  └──────┬───────┘  └────────┬─────────┘    │
│                          │                   │               │
│                          ▼                   ▼               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              Test Executor                           │    │
│  │  Carga → Prefill → Generacion → Descarga → Medir    │    │
│  │  Timeouts separados por fase                         │    │
│  └─────────────────────┬────────────────────────────────┘    │
│                        │                                     │
│            ┌───────────┼───────────┐                        │
│            ▼           ▼           ▼                         │
│  ┌────────────┐ ┌──────────┐ ┌──────────┐                  │
│  │ SQLite DB  │ │  MD por  │ │ Summary  │                  │
│  │ (raw data) │ │  modelo  │ │ global   │                  │
│  └────────────┘ └──────────┘ └──────────┘                  │
└──────────────────────────────────────────────────────────────┘
```

## 2. Ciclo de Vida por Modelo

Cada modelo se procesa en aislamiento completo:

```
1. REGISTRO: Leer spec del modelo (params, contexto max, tecnicas compatibles)
2. PRESUPUESTO: Para cada combinacion (contexto × tecnica), calcular si entra en RAM
   Si no entra → SKIP con documentacion
3. DESCARGA: Si el GGUF no existe localmente, descargar desde Hugging Face
4. CARGA: Cargar modelo en llama-cli, medir tiempo y RAM
5. PREFILL: Prompt de tamaño exacto, medir velocidad
6. GENERACION: N tokens (256 por defecto), medir decode sostenido
7. DESCARGA: Liberar modelo de RAM
8. REGISTRO ESCRITO: Volcar resultados a SQLite + MD
9. REPETIR con siguiente configuracion del mismo modelo
10. LIMPIEZA: Al terminar todas las configs del modelo, borrar GGUF
11. PASAR al siguiente modelo
```

## 3. Especificacion de llama-cli v8880

Motor verificado el 2026-05-29:

| Comando | Valor |
|---|---|
| Version | 8880 (2799d933b) |
| BLAS | Metal |
| GPU | MTL0 (Apple M1, GPUFamily Apple7) |
| Memoria recomendada | 26800.60 MB (recomendedMaxWorkingSetSize) |
| Flash Attention | `-fa auto` (default), `-fa 1` para forzar |
| KV cache type K | `-ctk` (f16, q8_0, q4_0) |
| KV cache type V | `-ctv` (f16, q8_0, q4_0) |
| GPU layers | `-ngl N` (default 1024 = todas) |
| Context size | `-c N` |
| Timings | `--show-timings` (default: true) |
| Formato salida timings | tokens/s, total time, prompt tokens, generated tokens |

## 4. Presupuesto RAM

### Calculo realizado con el hardware real:

| Componente | GB |
|---|---|
| RAM total | 16.0 |
| macOS + sistema | 3.5 |
| llama.cpp runtime | 0.5 |
| Margen seguridad | 1.0 |
| **Disponible para modelo** | **11.0** |

### Formula de calculo:

```
RAM_pesos = params_B × bits_por_peso / 8
RAM_KV = 2 × n_layers × n_kv_heads × head_dim × context_len × bytes_por_valor
  Donde bytes_por_valor: f16=2, q8_0=1, q4_0=0.5
  Para MLA: RAM_KV × 0.1 (compresion ~10x)
RAM_total = RAM_pesos + RAM_KV + 0.5 (overhead)
```

### Verificacion con modelo conocido (Qwen3.5-9B):

```
Pesos Q4_K_S (4.25 bits): 9.0 × 4.25 / 8 = 4.78 GB
KV f16 a 128K: 2 × 28 × 4 × 128 × 128000 × 2 = 7.34 GB
Total: 4.78 + 7.34 + 0.5 = 12.62 GB → ❌ NO ENTRA (11.0 disponible)

KV q4_0 a 128K: 2 × 28 × 4 × 128 × 128000 × 0.5 = 1.84 GB
Total: 4.78 + 1.84 + 0.5 = 7.12 GB → ✅ ENTRA

KV planar3 K+f16 V a 128K: ver con benchmark real
```

## 5. Matriz de Pruebas Completa

### Variables:

| Variable | Valores |
|---|---|
| Modelo | 8 modelos (ver seccion 6) |
| Contexto | 16K, 32K, 64K, 128K, 200K, 256K, 512K, 768K, 1M |
| KV cache | f16, q4_0, q8_0 |
| Flash Attention | on/off |
| GPU layers | 99 (todas en Metal) |
| Generacion | 256 tokens |

### Producto cartesiano por modelo:

Para cada modelo, se genera una matriz de tests = contextos_validos × kv_formats × flash_options.
Se ejecutan solo las combinaciones que pasan el filtro de RAM.

### Total estimado de tests:

~8 modelos × ~6 contextos promedio × ~2 kv_formats × 1 flash = ~96 tests
Cada test: ~30s-5min → ~2-8 horas de ejecucion total

## 6. Catalogo de Modelos a Testear

### Prioridad 1: Contexto largo (respuesta a pregunta central del usuario)

| # | Modelo | Params | Contexto max | Atencion | Peso Q4 aprox | Nota |
|---|---|---|---|---|---|---|
| 1 | Qwen2.5-7B-1M | 7B | 1,000,000 | GQA | ~4 GB | Contexto extremo |
| 2 | Qwen3.5-9B | 9B | 262,144 | GQA | ~5 GB | Modelo principal |
| 3 | Ministral-3-8B | 8B | 131,072 | GQA | ~4.5 GB | Competidor |

### Prioridad 2: Workers rapidos

| # | Modelo | Params | Contexto max | Atencion | Peso | Nota |
|---|---|---|---|---|---|---|
| 4 | Gemma 4 E2B | 2B | 32,768 | GQA | ~1.5 GB | MTP spec decode nativo |
| 5 | Gemma 4 E4B | 4B | 32,768 | GQA | ~2.5 GB | MTP spec decode |

### Prioridad 3: Experimental

| # | Modelo | Params | Contexto max | Atencion | Peso | Nota |
|---|---|---|---|---|---|---|
| 6 | DeepSeek-V2-Lite | 16B | 32,768 | **MLA** | ~9.7 GB | ¿MLA compensa peso? |
| 7 | Falcon3-7B STQ1_0 | 7B | 65,536 | GQA | ~1.3 GB | Ternario, worker ligero |

### Prioridad 4: Exoticos

| # | Modelo | Params | Contexto max | Atencion | Peso | Nota |
|---|---|---|---|---|---|---|
| 8 | Bonsai-8B Q1_0_g128 | 8B | 32,768 | GQA | ~1.15 GB | 1-bit experimental |

## 7. Pruebas Extra (Multi-agente, Concurrentes)

### 7.1 Continuous Batching Multi-agente

**Objetivo:** Medir throughput agregado al compartir 1 modelo entre N agentes.

**Metodo:** Ejecutar N sesiones simultaneas de llama-cli sobre el mismo modelo,
midiendo throughput total y por slot.

**Modelos:** Qwen3.5-9B, Ministral-3-8B

**Slots:** 1, 2, 4, 6, 8

**Contexto por slot:** 16K

**Hipotesis:** llama.cpp con continuous batching via `llama_batch` API permite
N slots en 1 forward pass. El throughput agregado debe ser > throughput individual × N
hasta que se sature el ancho de banda de memoria.

### 7.2 Worker Stress Test

**Objetivo:** Verificar si modelos peque~nos pueden mantener 80-100 tok/s en 16K-32K.

**Modelos:** Gemma 4 E2B, Gemma 4 E4B, Falcon3-7B STQ1_0

**Contexto:** 16K, 32K

**Iteraciones:** 100 generaciones consecutivas, medir fatigabilidad (degradacion
de velocidad en el tiempo).

### 7.3 Orquestador Remoto 1M (MacBook Pro)

**Objetivo:** Verificar si Qwen2.5-7B-1M mantiene contexto de 1M en MacBook Pro.

**Hardware:** M1 Max 32GB (WORKSTATION)

**Contexto:** 128K, 256K, 512K, 768K, 1M

**KV format:** q4_0, q8_0

## 8. Formato de Output

### 8.1 Base de Datos (SQLite)

```sql
CREATE TABLE models (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    params_b REAL,
    architecture TEXT,
    attention TEXT,
    context_max INTEGER,
    quant TEXT
);

CREATE TABLE test_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER,
    context_len INTEGER,
    kv_format TEXT,
    flash_attn INTEGER,
    status TEXT,           -- ok, oom, timeout, error
    load_time_s REAL,
    decode_speed REAL,     -- tokens/s
    total_time_ms REAL,
    generated_tokens INTEGER,
    prompt_tokens INTEGER,
    ram_estimate_gb REAL,
    error TEXT,
    timestamp TEXT,
    FOREIGN KEY (model_id) REFERENCES models(id)
);

CREATE TABLE errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    error_type TEXT,
    error_message TEXT,
    context TEXT,
    FOREIGN KEY (run_id) REFERENCES test_runs(id)
);
```

### 8.2 Informe por Modelo (Markdown)

Cada modelo produce un archivo en `docs/research/benchmarks/`:

```markdown
# Benchmark: Qwen3.5-9B (2026-05-30)

> Hardware: Mac Mini M1 16GB | Motor: llama-cli v8880 Metal
> Tecnicas: Flash Attention, PlanarQuant K+f16 V, PlanarQuant sim

## Resultados

| Contexto | KV format | Flash | tok/s | RAM est. | Estado |
|---|---|---|---|---|---|
| 16K | f16 | on | XX.X | X.X GB | ok |
| 32K | q4_0 | on | XX.X | X.X GB | ok |
| ... | ... | ... | ... | ... | ... |

## Conclusion
...
```

### 8.3 Summary Global

Al finalizar todos los modelos, se genera un summary comparativo:

```markdown
# Summary: Campa~na de Certificacion (2026-06-XX)

## Ranking por caso de uso
- Mayor contexto mantenido: Modelo X
- Mayor velocidad (16K): Modelo Y
- Mejor relacion contexto/velocidad: Modelo Z
...

## Recomendaciones para el stack
...
```

## 9. Ejecucion

### Fase 1: Humo (validar pipeline con 1 modelo)
1. Seleccionar Qwen3.5-9B (modelo principal, mas conocido)
2. Ejecutar 1 test manual con llama-cli, capturar output real
3. Verificar que las metricas se extraen correctamente
4. Verificar presupuesto RAM

### Fase 2: Qwen2.5-7B-1M (respuesta a pregunta central)
1. Descargar GGUF si no existe
2. Ejecutar matriz completa: contextos 16K a 1M
3. Para cada contexto: f16, q4_0, flash on/off
4. Documentar resultado antes de continuar

### Fase 3: Resto de modelos en orden de prioridad
...

### Fase 4: Pruebas extra
...

## 10. Criterios de Exito

| Prueba | Criterio |
|---|---|
| Contexto maximo | >256K mantenido sin OOM |
| Velocidad worker | >80 tok/s a 16K sostenido |
| Continuous batching | Degradacion <20% al duplicar slots |
| MLA vs GQA | MLA debe dar >2x contexto por misma RAM o no compensa |
| Ternario/1-bit | Contexto limitado pero permite N modelos simultaneos |
