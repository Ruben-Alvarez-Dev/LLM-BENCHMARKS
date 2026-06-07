"""Perfiles de carga A-E (specs/05 absorbida) — hilos + cliente OpenAI stdlib.

Cada perfil devuelve (results, wall_s, texts) y el dominio (loadmetrics) computa.
Parámetros pequeños por defecto para pruebas en seco; la campaña real los sube.
"""
from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass

from ...domain.loadmetrics import RequestResult
from .client import chat_request, text_of


@dataclass
class ProfileParams:
    n_streams: int = 4
    requests_per_stream: int = 3
    max_tokens: int = 64
    arrival_rate_per_s: float = 2.0      # Poisson (perfil A)
    shared_prefix: str = ""              # perfil B
    turns: int = 4                       # perfil B
    long_prompt: str = ""                # perfil C
    duration_s: float = 0.0              # perfil D (0 => por nº de requests)
    seed: int = 1234


def _worker(results: list, texts: list, lock: threading.Lock, **kw):
    r = chat_request(**kw)
    with lock:
        results.append(r)
        texts.append(text_of(r))


def profile_A(base_url: str, prompts: list[str], p: ProfileParams):
    """Agentes: N streams, llegadas Poisson, prompts cortos variados."""
    rng = random.Random(p.seed)
    results: list[RequestResult] = []
    texts: list[str] = []
    lock = threading.Lock()
    threads: list[threading.Thread] = []
    t0 = time.time()
    for i in range(p.n_streams * p.requests_per_stream):
        time.sleep(rng.expovariate(p.arrival_rate_per_s))
        th = threading.Thread(target=_worker, args=(results, texts, lock), kwargs=dict(
            base_url=base_url, prompt=prompts[i % len(prompts)],
            stream_id=i % p.n_streams, max_tokens=p.max_tokens))
        th.start()
        threads.append(th)
    for th in threads:
        th.join()
    return results, time.time() - t0, texts


def profile_B(base_url: str, p: ProfileParams):
    """Multi-turno con prefijo compartido: detecta reprefill (#20225/#24055).
    Cada turno reenvía el prefijo + historial; si el server reprocesa el prefijo
    entero cada vez, reprefill_pct se dispara."""
    results: list[RequestResult] = []
    texts: list[str] = []
    lock = threading.Lock()
    prefix_tokens = max(1, len(p.shared_prefix.split()))
    t0 = time.time()

    def conversation(stream_id: int):
        history = ""
        for turn in range(p.turns):
            prompt = f"{p.shared_prefix}\n{history}\nTurno {turn}: continúa."
            r = chat_request(base_url=base_url, prompt=prompt, stream_id=stream_id,
                             max_tokens=p.max_tokens,
                             prompt_total_hint=prefix_tokens if turn > 0 else 0)
            with lock:
                results.append(r)
                texts.append(text_of(r))
            history += f" t{turn}ok"

    threads = [threading.Thread(target=conversation, args=(i,))
               for i in range(p.n_streams)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    return results, time.time() - t0, texts


def profile_C(base_url: str, p: ProfileParams):
    """Asimétrico: 1 stream con prompt largo, el resto cortos intermitentes
    (detecta degradación por slots ocupados/idle, #19523)."""
    results: list[RequestResult] = []
    texts: list[str] = []
    lock = threading.Lock()
    t0 = time.time()
    threads = [threading.Thread(target=_worker, args=(results, texts, lock), kwargs=dict(
        base_url=base_url, prompt=p.long_prompt or ("contexto " * 500),
        stream_id=0, max_tokens=p.max_tokens))]
    for i in range(1, p.n_streams):
        threads.append(threading.Thread(target=_worker, args=(results, texts, lock),
                       kwargs=dict(base_url=base_url, prompt=f"ping corto {i}",
                                   stream_id=i, max_tokens=16)))
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    return results, time.time() - t0, texts


def profile_D(base_url: str, prompts: list[str], p: ProfileParams):
    """Soak: perfil A en bucle durante duration_s (térmico/leaks/crashes)."""
    all_results: list[RequestResult] = []
    all_texts: list[str] = []
    t0 = time.time()
    while time.time() - t0 < p.duration_s:
        r, _, tx = profile_A(base_url, prompts, p)
        all_results += r
        all_texts += tx
    return all_results, time.time() - t0, all_texts


TOOL_PROMPT = ("Devuelve SOLO un JSON válido con esta forma exacta: "
               '{"tool": "buscar", "args": {"query": "<texto>", "limit": <numero>}}. '
               "Petición: busca '%s' con límite %d.")


def profile_E(base_url: str, p: ProfileParams):
    """Calidad bajo carga: tool-calls JSON concurrentes; el dominio valida después."""
    rng = random.Random(p.seed)
    prompts = [TOOL_PROMPT % (f"tema-{rng.randint(1, 99)}", rng.randint(1, 20))
               for _ in range(p.n_streams * p.requests_per_stream)]
    return profile_A(base_url, prompts, p)


def json_tool_validity(texts: list[str]) -> float:
    """% de respuestas con JSON parseable que contiene tool+args."""
    if not texts:
        return 0.0
    ok = 0
    for t in texts:
        start, end = t.find("{"), t.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            obj = json.loads(t[start:end + 1])
            if isinstance(obj, dict) and "tool" in obj and "args" in obj:
                ok += 1
        except json.JSONDecodeError:
            continue
    return 100.0 * ok / len(texts)
