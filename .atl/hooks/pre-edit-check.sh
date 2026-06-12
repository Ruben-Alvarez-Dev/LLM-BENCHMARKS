#!/bin/bash
# L2 gate: scope + approval before touching files.
# Usage: pre-edit-check.sh <file-about-to-edit>
F="${1:-}"
echo "[pre-edit-check] About to edit: ${F:-<unknown>}" >&2
echo " - Is this file inside the APPROVED scope? If not: STOP (GR13/GR14)." >&2
echo " - Mock/demo/fake data being introduced? If yes: STOP (GR11)." >&2
echo " - Claims based on a single source? Get a second one (GR08)." >&2
case "$F" in
  */data/*.db) echo " - WARNING: benchmark DB — results are append-only evidence." >&2 ;;
esac
exit 0
