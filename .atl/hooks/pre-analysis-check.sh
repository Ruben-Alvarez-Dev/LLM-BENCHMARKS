#!/bin/bash
# L0.5 gate: was the plan analyzed? (options, trade-offs, learnings consulted)
ATL="$(cd "$(dirname "$0")/.." && pwd)"
echo "[pre-analysis-check] Confirm before executing (GR15):" >&2
echo " - Consequences foreseen? Options A/B/C analyzed and valued?" >&2
echo " - Decision justified? Rubén's OK received?" >&2
if [ -f "$ATL/learnings.md" ]; then
  N=$(grep -c '^- \*\*LL-' "$ATL/learnings.md")
  echo " - learnings.md consulted ($N entries). Read the relevant ones." >&2
fi
exit 0
