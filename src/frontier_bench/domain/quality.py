"""Calidad operativa — funciones PURAS sobre texto generado (fallo A8 de v1).

Un modelo puede "rendir" 60 t/s generando basura. Estos analizadores convierten
el texto generado en métricas: degeneración (repetición/colapso) y recall de
needles insertados en el prefill (memoria efectiva a profundidad).
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


# ───────────── degeneración ─────────────

@dataclass(frozen=True)
class DegenerationReport:
    repeated_ngram: bool        # algún 8-grama repetido ≥4 veces
    max_ngram_repeats: int
    distinct_ratio: float       # tokens únicos / totales (colapso si ≪)
    degenerate: bool


def degeneration(text: str, n: int = 8, repeat_threshold: int = 4,
                 distinct_floor: float = 0.15) -> DegenerationReport:
    words = text.split()
    if len(words) < n * 2:
        return DegenerationReport(False, 0, 1.0, False)
    counts: dict[tuple, int] = {}
    for i in range(len(words) - n + 1):
        gram = tuple(words[i:i + n])
        counts[gram] = counts.get(gram, 0) + 1
    max_rep = max(counts.values())
    distinct = len(set(words)) / len(words)
    repeated = max_rep >= repeat_threshold
    return DegenerationReport(
        repeated_ngram=repeated,
        max_ngram_repeats=max_rep,
        distinct_ratio=round(distinct, 4),
        degenerate=repeated or distinct < distinct_floor,
    )


# ───────────── needles ─────────────

@dataclass(frozen=True)
class Needle:
    key: str
    value: str

    @property
    def sentence(self) -> str:
        return f"\n[DATO IMPORTANTE] La clave {self.key} tiene el valor «{self.value}».\n"


def make_needles(seed: int, count: int = 3) -> list[Needle]:
    rng = random.Random(seed)
    needles = []
    for i in range(count):
        key = f"KW-{rng.randint(1000, 9999)}"
        value = "-".join(rng.choice(("lince", "cobalto", "brisa", "fractal", "ámbar",
                                     "vector", "granito", "pulsar")) for _ in range(2))
        needles.append(Needle(key=key, value=f"{value}-{rng.randint(10, 99)}"))
    return needles


def insert_needles(text: str, needles: list[Needle],
                   positions: tuple[float, ...] = (0.1, 0.5, 0.9)) -> str:
    """Inserta cada needle en su posición relativa del texto (en límites de línea)."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return text
    out = list(lines)
    # insertar de atrás hacia delante para no desplazar índices
    pairs = sorted(zip(positions, needles), key=lambda p: -p[0])
    for pos, needle in pairs:
        idx = min(len(out) - 1, max(0, int(len(out) * pos)))
        out.insert(idx, needle.sentence)
    return "".join(out)


def needle_recall(answer: str, needles: list[Needle]) -> int:
    """Cuántos values aparecen en la respuesta (0..len)."""
    low = answer.lower()
    return sum(1 for n in needles if n.value.lower() in low)


def needle_question(needles: list[Needle]) -> str:
    keys = ", ".join(n.key for n in needles)
    return (f"\n\nPregunta: ¿qué valores tienen las claves {keys}? "
            f"Responde SOLO los valores, separados por comas.\nRespuesta:")


def corpus_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
