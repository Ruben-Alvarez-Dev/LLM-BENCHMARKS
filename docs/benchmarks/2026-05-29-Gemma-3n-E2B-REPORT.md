# Benchmark: Gemma-3n-E2B

| Model | Context | KV Format | Flash | tok/s | Prefill tok/s | RAM obs | RAM est | Status | Error |
|---|---|---|---|---|---|---|---|---|---|
| Gemma-3n-E2B | 16K | f16 | off | 70.7 | 94.8 | 5.22 | 3.38 | ok |  |
| Gemma-3n-E2B | 16K | f16 | on | 71.4 | 191.7 | 5.22 | 3.38 | ok |  |
| Gemma-3n-E2B | 16K | q4_0 | off | 62.0 | 184.1 | 5.10 | 3.19 | ok |  |
| Gemma-3n-E2B | 16K | q4_0 | on | 62.2 | 183.1 | 5.10 | 3.19 | ok |  |
| Gemma-3n-E2B | 16K | q8_0 | off | 60.2 | 181.4 | 5.14 | 3.25 | ok |  |
| Gemma-3n-E2B | 16K | q8_0 | on | 60.2 | 178.7 | 5.14 | 3.25 | ok |  |
| Gemma-3n-E2B | 32K | f16 | off | 71.5 | 190.4 | 5.37 | 3.62 | ok |  |
| Gemma-3n-E2B | 32K | f16 | on | 71.6 | 192.8 | 5.37 | 3.62 | ok |  |
| Gemma-3n-E2B | 32K | q4_0 | off | 62.3 | 182.3 | 5.17 | 3.25 | ok |  |
| Gemma-3n-E2B | 32K | q4_0 | on | 62.0 | 180.7 | 5.17 | 3.25 | ok |  |
| Gemma-3n-E2B | 32K | q8_0 | off | 60.1 | 176.9 | 5.24 | 3.38 | ok |  |
| Gemma-3n-E2B | 32K | q8_0 | on | 60.0 | 173.0 | 5.24 | 3.38 | ok |  |
| Gemma-3n-E2B | 64K | f16 | off | 71.0 | 191.7 | 5.68 | 4.12 | ok |  |
| Gemma-3n-E2B | 64K | f16 | on | 71.3 | 188.2 | 5.68 | 4.12 | ok |  |
| Gemma-3n-E2B | 64K | q4_0 | off | 61.2 | 183.8 | 5.30 | 3.38 | ok |  |
| Gemma-3n-E2B | 64K | q4_0 | on | 61.6 | 182.3 | 5.30 | 3.38 | ok |  |
| Gemma-3n-E2B | 64K | q8_0 | off | 60.0 | 180.9 | 5.44 | 3.62 | ok |  |
| Gemma-3n-E2B | 64K | q8_0 | on | 59.7 | 180.3 | 5.44 | 3.62 | ok |  |
| Gemma-3n-E2B | 128K | f16 | off | 71.2 | 192.0 | 6.31 | 5.12 | ok |  |
| Gemma-3n-E2B | 128K | f16 | on | 71.1 | 189.5 | 6.31 | 5.12 | ok |  |
| Gemma-3n-E2B | 128K | q4_0 | off | 62.0 | 180.9 | 5.57 | 3.62 | ok |  |
| Gemma-3n-E2B | 128K | q4_0 | on | 61.5 | 183.4 | 5.57 | 3.62 | ok |  |
| Gemma-3n-E2B | 128K | q8_0 | off | 59.9 | 177.7 | 5.83 | 4.12 | ok |  |
| Gemma-3n-E2B | 128K | q8_0 | on | 60.1 | 180.0 | 5.83 | 4.12 | ok |  |