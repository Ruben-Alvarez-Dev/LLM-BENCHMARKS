# Benchmark: DeepSeek-V2-Lite

| Model | Context | KV Format | Flash | tok/s | Prefill tok/s | RAM obs | RAM est | Status | Error |
|---|---|---|---|---|---|---|---|---|---|
| DeepSeek-V2-Lite | 16K | f16 | off | 97.5 | 110.4 | 14.22 | 4.19 | ok |  |
| DeepSeek-V2-Lite | 16K | f16 | on | 98.0 | 166.9 | 14.22 | 4.19 | ok |  |
| DeepSeek-V2-Lite | 16K | q4_0 | off | 84.7 | 178.6 | 11.19 | 4.19 | ok |  |
| DeepSeek-V2-Lite | 16K | q4_0 | on | 84.6 | 178.5 | 11.19 | 4.19 | ok |  |
| DeepSeek-V2-Lite | 16K | q8_0 | off | 86.8 | 179.7 | 12.25 | 4.19 | ok |  |
| DeepSeek-V2-Lite | 16K | q8_0 | on | 86.2 | 179.5 | 12.25 | 4.19 | ok |  |
| DeepSeek-V2-Lite | 32K | f16 | off | 72.7 | 22.8 | 18.47 | 5.04 | ok |  |
| DeepSeek-V2-Lite | 32K | f16 | on | 83.2 | 183.1 | 18.47 | 5.04 | ok |  |
| DeepSeek-V2-Lite | 32K | q4_0 | off | 84.2 | 178.5 | 12.41 | 5.04 | ok |  |
| DeepSeek-V2-Lite | 32K | q4_0 | on | 85.0 | 178.2 | 12.41 | 5.04 | ok |  |
| DeepSeek-V2-Lite | 32K | q8_0 | off | 85.6 | 179.9 | 14.52 | 5.04 | ok |  |
| DeepSeek-V2-Lite | 32K | q8_0 | on | 86.6 | 181.2 | 14.52 | 5.04 | ok |  |