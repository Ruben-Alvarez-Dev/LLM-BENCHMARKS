#!/bin/bash
# L4: capture learning. Usage: post-learning-capture.sh "what happened" "learning" "rule"
ATL="$(cd "$(dirname "$0")/.." && pwd)"
L="$ATL/learnings.md"
if [ $# -lt 3 ]; then
  echo "[post-learning-capture] Anything learned this step? If yes:" >&2
  echo "  $0 \"what happened\" \"learning\" \"GRxx/PRxx\"" >&2
  exit 0
fi
LAST=$(grep -o 'LL-[0-9]\{3\}' "$L" | sort | tail -1 | tr -d 'LL-')
NEXT=$(printf "LL-%03d" $((10#${LAST:-0}+1)))
printf -- "- **%s** · %s · %s · **%s** · %s\n" "$NEXT" "$(date +%F)" "$1" "$2" "$3" >> "$L"
echo "[post-learning-capture] appended $NEXT" >&2
exit 0
