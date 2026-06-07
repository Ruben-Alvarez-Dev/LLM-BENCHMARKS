"""Import del inventario llm_catalogo.csv (FF_Files_and_Folders) al registry de modelos.

Best-effort: nombre, quant, formato, tamaño y ruta; los metadatos duros (capas,
kv_heads, ctx, rope) los completa gguf_reader cuando el fichero está en disco.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path


def parse_catalog(text: str) -> list[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        path = (r.get("path") or "").strip()
        name = (r.get("model") or "").strip()
        if not name:
            continue
        size = 0
        try:
            size = int(r.get("size_bytes") or 0)
        except ValueError:
            pass
        if not size:
            m = re.match(r"([\d.]+)\s*([GM])B", (r.get("size") or "").strip(), re.I)
            if m:
                size = int(float(m.group(1)) * (1024 ** 3 if m.group(2).upper() == "G"
                                                else 1024 ** 2))
        rows.append({
            "model_id": f"{(r.get('author') or '?').strip()}/{name}",
            "name": name,
            "quant": (r.get("tag_quant") or "?").strip(),
            "format": (r.get("format") or "?").strip(),
            "file_bytes": size,
            "file_path": path,
            "on_disk": bool(path) and Path(path).exists(),
            "redownload": (r.get("redownload") or "").strip(),
            "category": (r.get("categoria") or "").strip(),
        })
    return rows


def import_catalog(store, csv_path: str | Path) -> dict:
    rows = parse_catalog(Path(csv_path).read_text(errors="ignore"))
    n = 0
    for r in rows:
        store._conn.execute(
            """INSERT OR IGNORE INTO models
               (model_id,name,params_b,quant,file_bytes,arch,kv_profile_json,
                context_native,context_max,file_path)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (r["model_id"], r["name"], 0.0, r["quant"], r["file_bytes"],
             "pending_gguf_read", "{}", 0, 0, r["file_path"]))
        n += 1
    store._conn.commit()
    store.log_action("import_catalog", "imported",
                     {"source": str(csv_path), "rows": n,
                      "on_disk": sum(1 for r in rows if r["on_disk"])})
    return {"rows": n, "on_disk": sum(1 for r in rows if r["on_disk"])}
