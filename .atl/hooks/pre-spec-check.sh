#!/bin/bash
# L0 gate: is there a spec/plan for the task at hand?
# Claude Code hook convention: exit 0 = pass, exit 2 = block (stderr shown to the agent).
ATL="$(cd "$(dirname "$0")/.." && pwd)"
TASK="${1:-}"
if [ -z "$TASK" ]; then
  echo "[pre-spec-check] No task id given. Checklist:" >&2
  echo " - Does a spec exist for this work? (specs/ or batteries.yaml or docs/research/)" >&2
  echo " - If NO: write the spec FIRST. No code before spec (GR15)." >&2
  exit 0
fi
grep -rqs "$TASK" "$ATL/../specs" "$ATL/../batteries.yaml" 2>/dev/null && exit 0
echo "[pre-spec-check] BLOCK: no spec found mentioning '$TASK'. Write spec first (GR15)." >&2
exit 2
