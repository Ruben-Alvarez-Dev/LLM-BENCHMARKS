# Benchmark: Ministral-3-8B

| Model | Context | KV Format | Flash | tok/s | Prefill tok/s | RAM obs | RAM est | Status | Error |
|---|---|---|---|---|---|---|---|---|---|
| Ministral-3-8B | 16K | f16 | off | 42.2 | 366.8 | 7.54 | 7.25 | ok |  |
| Ministral-3-8B | 16K | f16 | on | 42.3 | 463.6 | 7.54 | 7.25 | ok |  |
| Ministral-3-8B | 16K | q4_0 | off | 37.8 | 409.7 | 6.02 | 6.69 | ok |  |
| Ministral-3-8B | 16K | q4_0 | on | 37.9 | 450.0 | 6.02 | 6.69 | ok |  |
| Ministral-3-8B | 16K | q8_0 | off | 37.1 | 410.8 | 6.55 | 6.88 | ok |  |
| Ministral-3-8B | 16K | q8_0 | on | 37.2 | 451.1 | 6.55 | 6.88 | ok |  |
| Ministral-3-8B | 32K | f16 | off | 42.2 | 462.7 | 9.70 | 8.00 | ok |  |
| Ministral-3-8B | 32K | f16 | on | 42.2 | 463.9 | 9.70 | 8.00 | ok |  |
| Ministral-3-8B | 32K | q4_0 | off | 37.6 | 439.5 | 6.65 | 6.88 | ok |  |
| Ministral-3-8B | 32K | q4_0 | on | 37.8 | 450.4 | 6.65 | 6.88 | ok |  |
| Ministral-3-8B | 32K | q8_0 | off | 37.1 | 451.1 | 7.71 | 7.25 | ok |  |
| Ministral-3-8B | 32K | q8_0 | on | 28.8 | 450.9 | 7.71 | 7.25 | ok |  |
| Ministral-3-8B | 64K | f16 | off | 42.1 | 454.0 | 14.01 | 9.50 | ok |  |
| Ministral-3-8B | 64K | f16 | on | 29.3 | 465.2 | 14.01 | 9.50 | ok |  |
| Ministral-3-8B | 64K | q4_0 | off | 38.1 | 452.1 | 7.90 | 7.25 | ok |  |
| Ministral-3-8B | 64K | q4_0 | on | 38.0 | 452.2 | 7.90 | 7.25 | ok |  |
| Ministral-3-8B | 64K | q8_0 | off | 37.4 | 453.4 | 10.03 | 8.00 | ok |  |
| Ministral-3-8B | 64K | q8_0 | on | 28.1 | 453.5 | 10.03 | 8.00 | ok |  |
| Ministral-3-8B | 128K | q4_0 | off | 38.1 | 430.0 | 10.55 | 8.00 | ok |  |
| Ministral-3-8B | 128K | q4_0 | on | 38.0 | 452.5 | 10.55 | 8.00 | ok |  |
| Ministral-3-8B | 128K | q8_0 | off | 28.8 | 450.2 | 14.80 | 9.50 | ok |  |
| Ministral-3-8B | 128K | q8_0 | on | 37.4 | 453.9 | 14.80 | 9.50 | ok |  |