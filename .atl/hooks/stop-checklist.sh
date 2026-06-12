#!/bin/bash
# Final gate before declaring a stage done.
ATL="$(cd "$(dirname "$0")/.." && pwd)"
echo "[stop-checklist] A stage is DONE only if ALL are true (GR10/GR16/GR17):" >&2
echo " - Explicit passing proof exists (test/bench/beacon), recorded in DB + docs." >&2
echo " - Result shown to Rubén." >&2
echo " - Learning captured (post-learning-capture.sh)." >&2
echo " - Granular conventional commit done (+push if remote)." >&2
echo " - Model deleted from disk if its line is finished (PR01)." >&2
echo " - Next stage returns to L0 (spec)." >&2
echo " - Ralph Loop: stop only on <promise>COMPLETED</promise>." >&2
exit 0
