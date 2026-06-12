#!/bin/bash
# L4 gate: recalculate after each step.
echo "[post-step-recalc] (GR15 recalc):" >&2
echo " - Evidence of error? -> STOP and re-plan." >&2
echo " - Founded suspicion? -> STOP and consult Rubén." >&2
echo " - Result verified with explicit proof (test green / beacon recall)? (GR10)" >&2
echo " - Memory guardrails respected during the step? (PR02)" >&2
echo " - Exactly ONE model on disk? (PR01)" >&2
exit 0
