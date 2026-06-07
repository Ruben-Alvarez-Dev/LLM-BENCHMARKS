"""Corpus real determinista (corrige el fallo A2: nada de relleno repetido).

Cosecha texto REAL de directorios locales (código .py/.js/.swift, docs .md, prosa),
trocea en párrafos, los baraja con seed fija y concatena hasta el objetivo de tokens.
Mismo seed + mismos ficheros => mismo corpus (fingerprint sha256 en provenance).
"""
from __future__ import annotations

import random
from pathlib import Path

from ...domain.quality import corpus_fingerprint

CODE_EXT = {".py", ".js", ".ts", ".swift", ".c", ".cpp", ".go", ".rs", ".sh"}
DOC_EXT = {".md", ".txt", ".rst"}
CHARS_PER_TOKEN = 3.4   # aproximación mixta código+prosa; el run registra tokens REALES


class RealCorpus:
    """Implementa CorpusPort.text_tokens(n_tokens, seed)."""

    def __init__(self, roots: list[str | Path], max_file_kb: int = 256,
                 max_files: int = 400):
        self._paragraphs: list[str] = []
        files = []
        for root in roots:
            root = Path(root).expanduser()
            if not root.exists():
                continue
            for p in sorted(root.rglob("*")):
                if (p.is_file() and p.suffix.lower() in CODE_EXT | DOC_EXT
                        and p.stat().st_size < max_file_kb * 1024
                        and "__pycache__" not in str(p) and "/.git/" not in str(p)
                        and "node_modules" not in str(p)):
                    files.append(p)
        for p in files[:max_files]:
            try:
                text = p.read_text(errors="ignore")
            except OSError:
                continue
            for block in text.split("\n\n"):
                block = block.strip()
                if 80 <= len(block) <= 4000:
                    self._paragraphs.append(block)
        if not self._paragraphs:
            raise RuntimeError(f"Corpus vacío: ningún texto cosechable en {roots}")

    @property
    def n_paragraphs(self) -> int:
        return len(self._paragraphs)

    def text_tokens(self, n_tokens: int, seed: int) -> str:
        """Texto de ~n_tokens (aprox por chars; el token count real lo reporta el engine)."""
        if n_tokens <= 0:
            return ""
        target_chars = int(n_tokens * CHARS_PER_TOKEN)
        rng = random.Random(seed)
        order = list(range(len(self._paragraphs)))
        rng.shuffle(order)
        out: list[str] = []
        size = 0
        i = 0
        while size < target_chars:
            block = self._paragraphs[order[i % len(order)]]
            out.append(block)
            size += len(block) + 2
            i += 1
        text = "\n\n".join(out)
        return text[:target_chars]

    def fingerprint(self, n_tokens: int, seed: int) -> str:
        return corpus_fingerprint(self.text_tokens(n_tokens, seed))
