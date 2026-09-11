#!/usr/bin/env bash
# qntelli-solve — ONE-ENTER quantum-code solver, with an interactive mode.
# Ask a quantum algorithm coding question; get FULLY-CORRECT, ALREADY-TESTED,
# EFFICIENT code in one step — no back-and-forth. Internally it generates,
# runs the code against an analytic reference, and silently self-corrects if
# the first attempt is imperfect; only a verified (PASS) solution is returned.
#
#   qntelli-solve "write a 3-qubit GHZ and verify it"   # one-shot
#   qntelli-solve --interactive                          # multi-turn conversation
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# cli_oneshot.py wraps solve() for BOTH the one-shot and --interactive paths
# (and is the same entrypoint the frozen dist binary is built from), so
# delegate there for consistent behavior across all entry points.
exec python3 "$SCRIPT_DIR/quantum/cli_oneshot.py" "$@"
