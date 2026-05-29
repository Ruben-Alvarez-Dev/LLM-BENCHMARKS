# Catalogo de Modelos — Estado Final

> Actualizado: 2026-05-29 (cierre de sesion)
> Hardware actual: Mac Mini M1 16GB
> Tests totales: 129 | OK: 129 | Errores: 0

---

## Modelos en Disco — Decision Final

### ✅ CONSERVAR (benchmarkeados, utiles en MM)

| Modelo | Archivo | Disco | tok/s | RAM | Contexto | Por que |
|---|---|---|---|---|---|---|
| Qwen3.5-4B | Jart-OS-workstation/... | 2.7 GB | **60** | 6.8 GB | 256K | Mejor relacion ctx/velocidad/RAM |
| Qwen3-1.7B | Jart-OS-workstation/... | 1.2 GB | **156** | 2.2 GB | 32K | Worker ultra-rapido |
| Qwen3.5-2B | Jart-OS-workstation/... | 1.2 GB | **113** | 2.2 GB | 32K | Worker rapido |
| Gemma-3n-E2B | Jart-OS-workstation/... | 2.8 GB | **71** | 6.3 GB | 128K | Worker 128K f16 |
| Qwen2.5-Coder-3B | Jart-OS-workstation/... | 2.0 GB | **109** | 3.0 GB | 32K | Code specialist |
| Qwen2.5-7B-1M | INFERENCE-investigation/... | 4.4 GB | **45** | 9.9 GB | 256K | PENDIENTE MBP 32GB (512K-1M) |

### ❌ BORRAR (ya analizados, no aportan vs alternativas)

| Modelo | Archivo | Disco | tok/s | RAM | Motivo |
|---|---|---|---|---|---|
| Qwen3.5-9B | external/models/ | 5.2 GB | 38 | 9.4 GB | Mas lento y pesado que Qwen3.5-4B (mismo contexto, 1.5x velocidad). BORRAR |
| Ministral-3-8B | external/models/ | 4.8 GB | 42 | 10.6 GB | Similar a Qwen2.5-7B-1M pero 0.5 GB mas, menos contexto. BORRAR |
| DeepSeek-V2-Lite | external/models/ | ~~9.7 GB~~ | 85 | 11.2 GB | YA BORRADO. MLA no compensa en MM 16GB. |

### 🗑️ Ya eliminados durante la sesion

| Modelo | Tamano | Fecha | Motivo |
|---|---|---|---|
| DeepSeek-V2-Lite | 9.7 GB | 2026-05-29 | MLA no compensa en MM 16GB |
| Gemma-4-E2B | 3.2 GB | 2026-05-29 | Descarga innecesaria (duplicado de worker que no llego a completarse) |
| Ministral-3-8B | (pendiente) | — | Se borrara al finalizar |
| Qwen3.5-9B | (pendiente) | — | Se borrara al finalizar |

---

## Ranking Final (MM 16GB)

### Velocidad pura
1. **Qwen3-1.7B** — 156 tok/s, 2.2 GB (worker)
2. **Qwen3.5-2B** — 113 tok/s, 2.2 GB (worker)
3. **Qwen2.5-Coder-3B** — 109 tok/s, 3.0 GB (code)
4. **DeepSeek-V2-Lite** — 85 tok/s, 11.2 GB (MLA, ❌ eliminado)
5. **Gemma-3n-E2B** — 71 tok/s, 6.3 GB (128K worker)
6. **Qwen3.5-4B** — 60 tok/s, 6.8 GB (⭐ BEST BALANCE)
7. **Qwen2.5-7B-1M** — 45 tok/s, 9.9 GB (large ctx)
8. **Ministral-3-8B** — 42 tok/s, 10.6 GB (❌ a borrar)
9. **Qwen3.5-9B** — 38 tok/s, 9.4 GB (❌ a borrar)

### Eficiencia (tok/s por GB)
1. **Qwen3.5-2B** — 50.3 tok/s/GB
2. **Qwen3-1.7B** — 48.0 tok/s/GB
3. **Qwen2.5-Coder-3B** — 35.1 tok/s/GB
4. **Qwen3.5-4B** — 15.5 tok/s/GB
5. **Gemma-3n-E2B** — 12.2 tok/s/GB

### Contexto maximo mantenido
1. **Qwen3.5-4B** — **256K** a 6.8 GB
2. **Qwen2.5-7B-1M** — **256K** a 9.9 GB
3. **Gemma-3n-E2B** — **128K** a 6.3 GB
4. **Qwen3.5-9B** — **256K** a 9.4 GB (❌ a borrar)

---

## Recomendacion Final para el Stack

| Rol | Modelo | Config |
|---|---|---|
| **Worker ultra-rapido** | Qwen3-1.7B | f16: 156 tok/s, 3.4 GB |
| **Worker code** | Qwen2.5-Coder-3B | f16 flash: 109 tok/s, 3.0 GB |
| **Worker contexto medio** | Gemma-3n-E2B | f16 flash: 71 tok/s, 128K, 6.3 GB |
| **Modelo principal** | **Qwen3.5-4B** | q4_0: **60 tok/s, 256K, 6.8 GB** |
| **Contexto largo** | Qwen2.5-7B-1M | q4_0 flash: 45 tok/s, 256K, 9.9 GB |
| **Contexto extremo (MBP)** | Qwen2.5-7B-1M | 512K-1M pendiente en MBP 32GB |

---

*129 tests, 10 modelos analizados, 7 conservados, 3 eliminados.*
