"""Lector de metadatos GGUF — la verdad sale del FICHERO, no de suposiciones.

Lee solo la cabecera KV (sin tensores): arquitectura, capas, kv_heads, head_dim,
context_length nativo, y TODO lo de rope/YaRN. Con eso: (a) KvProfile automático
en vez de parámetros a mano, (b) detector de extensibilidad YaRN — si un contexto
pedido supera el nativo, el pipeline EXIGE rope-scaling y pruebas de consistencia.

Formato GGUF v2/v3: magic 'GGUF' + version u32 + n_tensors u64 + n_kv u64 + pares KV.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

_T_U8, _T_I8, _T_U16, _T_I16, _T_U32, _T_I32, _T_F32, _T_BOOL, _T_STR, _T_ARR, \
    _T_U64, _T_I64, _T_F64 = range(13)

_SCALAR_FMT = {_T_U8: "<B", _T_I8: "<b", _T_U16: "<H", _T_I16: "<h",
               _T_U32: "<I", _T_I32: "<i", _T_F32: "<f", _T_BOOL: "<B",
               _T_U64: "<Q", _T_I64: "<q", _T_F64: "<d"}


class GGUFError(Exception):
    pass


def _read(fmt: str, f) -> int | float:
    size = struct.calcsize(fmt)
    data = f.read(size)
    if len(data) != size:
        raise GGUFError("EOF inesperado en cabecera GGUF")
    return struct.unpack(fmt, data)[0]


def _read_string(f) -> str:
    n = _read("<Q", f)
    if n > 1 << 20:
        raise GGUFError(f"string de cabecera sospechosamente grande ({n})")
    return f.read(n).decode("utf-8", "replace")


def _read_value(f, vtype: int):
    if vtype in _SCALAR_FMT:
        v = _read(_SCALAR_FMT[vtype], f)
        return bool(v) if vtype == _T_BOOL else v
    if vtype == _T_STR:
        return _read_string(f)
    if vtype == _T_ARR:
        item_type = _read("<I", f)
        count = _read("<Q", f)
        if count > 1 << 22:
            raise GGUFError(f"array de cabecera enorme ({count})")
        return [_read_value(f, item_type) for _ in range(count)]
    raise GGUFError(f"tipo GGUF desconocido: {vtype}")


def read_metadata(path: str | Path, max_keys: int = 4096) -> dict:
    """Todos los pares KV de la cabecera (sin tensores)."""
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise GGUFError("no es un fichero GGUF")
        version = _read("<I", f)
        if version < 2:
            raise GGUFError(f"GGUF v{version} no soportado")
        _n_tensors = _read("<Q", f)
        n_kv = _read("<Q", f)
        meta: dict = {"_gguf_version": version}
        for _ in range(min(n_kv, max_keys)):
            key = _read_string(f)
            vtype = _read("<I", f)
            meta[key] = _read_value(f, vtype)
        return meta


@dataclass
class GgufFacts:
    """Hechos derivados, con TODO lo no verificable marcado."""
    arch: str
    n_layers: int
    kv_heads: int
    head_dim: int
    context_native: int
    rope_scaling_type: str        # "none" | "linear" | "yarn" | "?"
    rope_orig_ctx: int            # original_context_length si el modelo YA viene extendido
    rope_freq_base: float
    yarn_extendable: bool         # heurística: rope estándar => extensible vía YaRN
    warnings: list[str] = field(default_factory=list)
    raw_keys: dict = field(default_factory=dict)


def facts_from_metadata(meta: dict) -> GgufFacts:
    arch = str(meta.get("general.architecture", "?"))
    g = lambda k, d=0: meta.get(f"{arch}.{k}", d)

    n_layers = int(g("block_count", 0))
    kv_heads_v = g("attention.head_count_kv", 0)
    # algunos archs lo publican por-capa (array): en híbridos, las capas lineales llevan 0
    if isinstance(kv_heads_v, list):
        nonzero = [int(x) for x in kv_heads_v if int(x) > 0]
        kv_heads = max(nonzero) if nonzero else 0
        full_attn_layers = len(nonzero)
    else:
        kv_heads = int(kv_heads_v)
        full_attn_layers = None

    head_dim = int(g("attention.key_length", 0))
    if not head_dim:
        emb, heads = int(g("embedding_length", 0)), int(g("attention.head_count", 0) or 1)
        head_dim = emb // heads if emb and heads else 0

    ctx = int(g("context_length", 0))
    scaling = str(g("rope.scaling.type", "") or "none")
    orig = int(g("rope.scaling.original_context_length", 0))
    freq_base = float(g("rope.freq_base", 0.0))

    warnings = []
    if not n_layers or not ctx:
        warnings.append("metadatos incompletos: verificar a mano")
    if isinstance(kv_heads_v, list):
        warnings.append(f"kv_heads por capa (híbrido probable): "
                        f"{full_attn_layers}/{n_layers} capas con KV")
    if scaling == "yarn" and orig:
        warnings.append(f"YA viene extendido por YaRN desde {orig} — "
                        f"consistencia a >{orig} tokens OBLIGATORIA")

    facts = GgufFacts(
        arch=arch, n_layers=n_layers, kv_heads=kv_heads, head_dim=head_dim,
        context_native=ctx, rope_scaling_type=scaling, rope_orig_ctx=orig,
        rope_freq_base=freq_base,
        yarn_extendable=bool(freq_base) and scaling in ("none", "linear", "yarn"),
        warnings=warnings,
        raw_keys={k: v for k, v in meta.items()
                  if isinstance(v, (int, float, str, bool))})
    if full_attn_layers is not None:
        facts.raw_keys["_derived.full_attn_layers"] = full_attn_layers
    return facts


def read_facts(path: str | Path) -> GgufFacts:
    return facts_from_metadata(read_metadata(path))
