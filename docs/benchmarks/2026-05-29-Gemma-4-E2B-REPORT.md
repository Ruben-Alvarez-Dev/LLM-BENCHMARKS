# Benchmark: Gemma-4-E2B

| Model | Context | KV Format | Flash | tok/s | Prefill tok/s | RAM obs | RAM est | Status | Error |
|---|---|---|---|---|---|---|---|---|---|
| Gemma-4-E2B | 16K | f16 | off | 91.3 | 173.2 | 5.94 | 3.38 | ok |  |
| Gemma-4-E2B | 16K | f16 | on | 90.7 | 292.8 | 5.94 | 3.38 | ok |  |
| Gemma-4-E2B | 16K | q4_0 | off | 65.4 | 303.2 | 5.88 | 3.19 | ok |  |
| Gemma-4-E2B | 16K | q4_0 | on | 65.9 | 301.5 | 5.88 | 3.19 | ok |  |
| Gemma-4-E2B | 16K | q8_0 | off | 60.7 | 292.2 | 5.91 | 3.25 | ok |  |
| Gemma-4-E2B | 16K | q8_0 | on | 60.4 | 292.9 | 5.91 | 3.25 | ok |  |
| Gemma-4-E2B | 32K | f16 | off | 92.0 | 354.0 | 6.07 | 3.62 | ok |  |
| Gemma-4-E2B | 32K | f16 | on | 90.7 | 350.2 | 6.07 | 3.62 | ok |  |
| Gemma-4-E2B | 32K | q4_0 | off | 65.6 | 301.9 | 5.93 | 3.25 | ok |  |
| Gemma-4-E2B | 32K | q4_0 | on | 65.8 | 301.5 | 5.93 | 3.25 | ok |  |
| Gemma-4-E2B | 32K | q8_0 | off | 60.9 | 291.2 | 5.98 | 3.38 | ok |  |
| Gemma-4-E2B | 32K | q8_0 | on | 60.6 | 291.9 | 5.98 | 3.38 | ok |  |