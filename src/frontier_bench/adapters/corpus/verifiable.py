"""Contexto VERIFICABLE al 100% — balizas deterministas en posiciones conocidas.

Mejora sobre los 3 needles: el texto lleva una BALIZA cada `interval` tokens con un
código sha256(seed, idx) imposible de adivinar. Cualquier posición es comprobable:
"¿qué código tiene la baliza N?" → o el modelo la recuperó del contexto o no.
Eso permite (a) verificar consistencia en TODA la ventana (obligatorio con YaRN),
(b) cazar fallos rápido por BISECCIÓN del primer fallo (find_effective_context).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

WORDS_PER_TOKEN = 0.75   # aprox; las posiciones reales las confirma el tokenizador del engine


def beacon_code(seed: int, idx: int) -> str:
    return hashlib.sha256(f"fb-{seed}-{idx}".encode()).hexdigest()[:10]


def beacon_text(seed: int, idx: int) -> str:
    return f"\n<<BALIZA {idx} codigo={beacon_code(seed, idx)}>>\n"


@dataclass(frozen=True)
class Beacon:
    idx: int
    code: str
    approx_token_pos: int


def build_verifiable(base_text: str, n_tokens: int, seed: int,
                     interval_tokens: int = 1024) -> tuple[str, list[Beacon]]:
    """Intercala balizas cada ~interval_tokens en el texto base (corpus real)."""
    words = base_text.split()
    words_needed = int(n_tokens * WORDS_PER_TOKEN)
    while len(words) < words_needed:
        words = words + words   # el corpus base ya es largo; esto es red de seguridad
    words = words[:words_needed]

    interval_words = max(1, int(interval_tokens * WORDS_PER_TOKEN))
    out: list[str] = []
    beacons: list[Beacon] = []
    idx = 0
    for i in range(0, len(words), interval_words):
        beacons.append(Beacon(idx=idx, code=beacon_code(seed, idx),
                              approx_token_pos=int(i / WORDS_PER_TOKEN)))
        out.append(beacon_text(seed, idx).strip())
        out.extend(words[i:i + interval_words])
        idx += 1
    return " ".join(out), beacons


def question_for(beacons: list[Beacon], idxs: list[int]) -> str:
    asked = ", ".join(str(i) for i in idxs)
    return (f"\n\nPregunta: escribe el campo codigo de las balizas {asked}, "
            f"en orden, separados por comas. Solo los códigos.\nRespuesta:")


def check_answer(answer: str, beacons: list[Beacon], idxs: list[int]) -> dict[int, bool]:
    """Por baliza preguntada: ¿aparece su código exacto en la respuesta?"""
    found = set(re.findall(r"[0-9a-f]{10}", answer.lower()))
    by_idx = {b.idx: b.code for b in beacons}
    return {i: by_idx.get(i, "") in found for i in idxs}


def probe_positions(beacons: list[Beacon]) -> list[int]:
    """Posiciones relevantes por defecto: inicio, 25%, 50%, 75%, 90%, última."""
    if not beacons:
        return []
    n = len(beacons)
    picks = {0, n // 4, n // 2, (3 * n) // 4, int(n * 0.9), n - 1}
    return sorted(i for i in picks if 0 <= i < n)


class MasterContext:
    """Extracto maestro ÚNICO (p.ej. 1M tokens) del que toda la escalera toma
    PREFIJOS EXACTOS (700K, 512K, 256K...). Requisito de Rubén 2026-06-06:

    1) Comparabilidad: el peldaño de 256K es literalmente el prefijo del de 512K —
       las diferencias entre contextos son atribuibles a la LONGITUD, no al contenido.
    2) Anti-memorización: el relleno sale del corpus privado (no está en ningún
       training set), el orden lo fija el seed, y cada párrafo lleva una SAL única
       seeded (frag:<hex>) que hace el texto globalmente irrepetible. Las preguntas
       SOLO interrogan códigos de baliza (sha256, inadivinables) — nunca el relleno,
       así que ni un modelo que hubiera visto fragmentos podría responder sin
       atender de verdad al contexto.
    3) Eficiencia: prefijos anidados ⇒ el prefix-cache del server reutiliza el
       prefijo común entre peldaños (el extracto se procesa una vez, no diez).
    """

    def __init__(self, base_text: str, max_tokens: int, seed: int,
                 interval_tokens: int = 1024):
        self.seed = seed
        self.interval_tokens = interval_tokens
        # sal por párrafo: hace único cada fragmento frente a cualquier corpus público
        salted: list[str] = []
        for i, para in enumerate(base_text.split("\n\n")):
            salt = hashlib.sha256(f"salt-{seed}-{i}".encode()).hexdigest()[:8]
            salted.append(f"(frag:{salt}) {para}")
        self.text, self.beacons = build_verifiable(
            "\n\n".join(salted), max_tokens, seed, interval_tokens)
        self._char_per_token = len(self.text) / max(1, max_tokens)

    def prefix(self, n_tokens: int) -> tuple[str, list[Beacon]]:
        """Prefijo EXACTO de n_tokens (aprox por chars; el engine reporta el real)
        con las balizas que caen dentro. prefix(A) es prefijo literal de prefix(B)
        para todo A<B — propiedad testeada."""
        n_chars = int(n_tokens * self._char_per_token)
        text = self.text[:n_chars]
        inside = [b for b in self.beacons if b.approx_token_pos < n_tokens * 0.98]
        return text, inside

    def fingerprint(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:16]


def find_effective_context(recalls_at, lo_tokens: int, hi_tokens: int,
                           resolution: int = 4096, max_probes: int = 12) -> int:
    """Bisección del contexto EFECTIVO: mayor profundidad donde el modelo aún
    recupera la baliza. `recalls_at(depth_tokens) -> bool` (cada llamada es un
    run real; por eso max_probes acota el coste). Devuelve el último OK."""
    if not recalls_at(lo_tokens):
        return 0
    if recalls_at(hi_tokens):
        return hi_tokens
    ok, bad = lo_tokens, hi_tokens
    probes = 0
    while bad - ok > resolution and probes < max_probes:
        mid = (ok + bad) // 2
        if recalls_at(mid):
            ok = mid
        else:
            bad = mid
        probes += 1
    return ok
