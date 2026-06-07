"""Parser mínimo del subconjunto YAML que usa techniques.yaml (sin dependencia PyYAML).

Soporta: lista de bloques '- key: value', escalares, dicts inline {a: b, c: d},
listas inline [a, b], strings con comillas y comentarios (#). Suficiente y testeado
para nuestro registro; si el fichero crece en complejidad, se cambia a PyYAML (extra).
"""
from __future__ import annotations

import re


def _scalar(s: str):
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s == "true":
        return True
    if s == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _strip_comment(line: str) -> str:
    # quita comentarios fuera de comillas (suficiente para nuestro formato)
    out, in_q = [], None
    for ch in line:
        if in_q:
            if ch == in_q:
                in_q = None
        elif ch in "\"'":
            in_q = ch
        elif ch == "#":
            break
        out.append(ch)
    return "".join(out).rstrip()


def _value(s: str):
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1].strip()
        if not inner:
            return {}
        d = {}
        for part in _split_top(inner):
            k, _, v = part.partition(":")
            d[k.strip()] = _value(v)
        return d
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_value(p) for p in _split_top(inner)] if inner else []
    return _scalar(s)


def _split_top(s: str) -> list[str]:
    """Divide por comas a nivel superior (respeta {} [] y comillas)."""
    parts, depth, in_q, cur = [], 0, None, []
    for ch in s:
        if in_q:
            if ch == in_q:
                in_q = None
        elif ch in "\"'":
            in_q = ch
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return [p for p in (x.strip() for x in parts) if p]


def load_blocks(text: str) -> list[dict]:
    """Lista de bloques '- key: value\\n  key2: value2 ...'.
    Soporta UN nivel de anidación: 'key:' sin valor abre un sub-dict que recoge
    las líneas siguientes con indentación mayor (p.ej. suggest:/evidence: en
    tuning_rules.yaml)."""
    blocks: list[dict] = []
    cur: dict | None = None
    nested: tuple[str, int] | None = None   # (clave abierta, su indent)
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        m = re.match(r"^- (\w[\w-]*):\s*(.*)$", line)
        if m:
            cur = {m.group(1): _value(m.group(2))}
            blocks.append(cur)
            nested = None
            continue
        m = re.match(r"^(\s+)(\w[\w-]*):\s*(.*)$", line)
        if m and cur is not None:
            indent, key, val = len(m.group(1)), m.group(2), m.group(3)
            if nested and indent > nested[1]:
                cur[nested[0]][key] = _value(val)       # dentro del sub-dict
                continue
            if val == "":
                cur[key] = {}
                nested = (key, indent)                  # abre sub-dict
            else:
                cur[key] = _value(val)
                nested = None
            continue
        # ítem de lista anidada '  - valor' bajo clave abierta
        m = re.match(r"^(\s+)-\s+(.*)$", line)
        if m and cur is not None and nested and len(m.group(1)) > nested[1]:
            holder = cur[nested[0]]
            if isinstance(holder, dict) and not holder:
                cur[nested[0]] = holder = []
            if isinstance(holder, list):
                holder.append(_value(m.group(2)))
    return blocks
