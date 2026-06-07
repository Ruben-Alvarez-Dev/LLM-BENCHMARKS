"""Mantenimiento — dos políticas de Rubén (2026-06-06):

1) ACTUALIZAR ANTES DE PROBAR, SIEMPRE CON APROBACIÓN: antes de una campaña se
   comprueba si hay updates de engines (brew, pip). Se PROPONE al usuario con
   versión actual→nueva y el comando exacto; nada se ejecuta sin su sí explícito.
   Todo queda en action_log (propuesto, aprobado/rechazado, versión antes/después).

2) LIMPIEZA IMPOLUTA POR BATERÍA: cada adapter registra los ficheros que crea
   (prompts, JSONs temporales, caches, slots guardados). Al terminar la batería
   de UN modelo se borra todo lo registrado — EXCEPTO los crudos (raw_ref), que
   son evidencia, se comprimen y se conservan. Verificación post-borrado.
"""
from __future__ import annotations

import gzip
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path


# ───────────── 1. updates con aprobación ─────────────

@dataclass(frozen=True)
class UpdateProposal:
    component: str        # "llama.cpp" | "mlx-lm" | ...
    current: str
    latest: str
    command: str          # comando exacto que se ejecutaría
    source: str           # "brew" | "pip"


def parse_brew_outdated(raw_json: str,
                        watch: tuple[str, ...] = ("llama.cpp", "ggml")) -> list[UpdateProposal]:
    """Parsea `brew outdated --json=v2` y filtra los componentes que nos importan."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    out = []
    for f in data.get("formulae", []):
        name = f.get("name", "")
        if any(w in name for w in watch):
            out.append(UpdateProposal(
                component=name,
                current=(f.get("installed_versions") or ["?"])[0],
                latest=f.get("current_version", "?"),
                command=f"brew upgrade {name}",
                source="brew"))
    return out


def check_updates(runner) -> list[UpdateProposal]:
    """Consulta updates disponibles vía el runner (local o remoto). NO ejecuta nada."""
    res = runner.exec_shell(
        "export PATH=$PATH:/opt/homebrew/bin:/usr/local/bin; "
        "brew outdated --json=v2 2>/dev/null || echo '{}'", timeout_s=120)
    return parse_brew_outdated(res.stdout)


# ───────────── 2. limpieza por batería ─────────────

@dataclass
class CleanupReport:
    deleted: list[str] = field(default_factory=list)
    kept_evidence: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def pristine(self) -> bool:
        return not self.failed


@dataclass
class CleanupManifest:
    """Registro de todo lo que una batería crea. Nada se borra si no está aquí;
    todo lo que está aquí se borra al cerrar la batería (salvo evidencia)."""
    battery_id: str
    _temp: list[Path] = field(default_factory=list)
    _evidence: list[Path] = field(default_factory=list)

    def register_temp(self, path: str | Path) -> None:
        self._temp.append(Path(path))

    def register_evidence(self, path: str | Path) -> None:
        """Crudos: se conservan comprimidos, no se borran."""
        self._evidence.append(Path(path))

    def cleanup(self) -> CleanupReport:
        report = CleanupReport()
        # comprimir evidencia (raw logs) in-place
        for p in self._evidence:
            if p.exists() and p.suffix != ".gz":
                gz = p.with_suffix(p.suffix + ".gz")
                with open(p, "rb") as fin, gzip.open(gz, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
                p.unlink()
                report.kept_evidence.append(str(gz))
            elif p.exists():
                report.kept_evidence.append(str(p))
        # borrar temporales
        for p in self._temp:
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                elif p.exists():
                    p.unlink()
                if p.exists():
                    report.failed.append(str(p))
                else:
                    report.deleted.append(str(p))
            except OSError:
                report.failed.append(str(p))
        self._temp.clear()
        return report
