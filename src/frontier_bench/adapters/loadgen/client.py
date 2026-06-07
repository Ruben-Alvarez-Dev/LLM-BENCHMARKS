"""Cliente OpenAI-compatible con streaming SSE — stdlib puro (urllib), un hilo por stream.

Mide TTFT real (primer chunk con contenido) y tokens generados; captura el objeto
`timings` que llama-server adjunta (prompt_n procesados → detector de reprefill).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from ...domain.loadmetrics import RequestResult


def chat_request(base_url: str, prompt: str, stream_id: int, max_tokens: int = 128,
                 system: str = "", timeout_s: float = 300.0,
                 prompt_total_hint: int = 0) -> RequestResult:
    """POST /v1/chat/completions con stream=true. Bloqueante (usar desde hilos)."""
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
    body = json.dumps({"model": "default", "messages": messages,
                       "max_tokens": max_tokens, "temperature": 0,
                       "stream": True}).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    ttft_ms, tokens, prompt_n = 0.0, 0, 0
    text_parts: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    if ttft_ms == 0.0:
                        ttft_ms = (time.time() - t0) * 1000
                    tokens += 1          # 1 chunk ≈ 1 token en llama-server
                    text_parts.append(content)
                t = chunk.get("timings")
                if t and t.get("prompt_n"):
                    prompt_n = int(t["prompt_n"])
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        return RequestResult(stream_id=stream_id, t_start=t0, ttft_ms=0.0,
                             total_ms=(time.time() - t0) * 1000, tokens_out=tokens,
                             prompt_total=prompt_total_hint, error=str(e)[:200])
    result = RequestResult(
        stream_id=stream_id, t_start=t0, ttft_ms=ttft_ms,
        total_ms=(time.time() - t0) * 1000, tokens_out=tokens,
        prompt_tokens=prompt_n, prompt_total=prompt_total_hint)
    # el texto se devuelve aparte para los gates de calidad (perfil E)
    result_text = "".join(text_parts)
    object.__setattr__(result, "_text", result_text)  # frozen: anexo controlado
    return result


def text_of(result: RequestResult) -> str:
    return getattr(result, "_text", "")
