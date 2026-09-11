#!/usr/bin/env bash
# qntelli harness GUI launcher
#
# Endpoint config for the on-line Solve button: mirrors bin/qntelli-solve and
# qntelli.sh so general/custom questions (e.g. a bespoke XOR gate with a
# required xor_gate(a,b) signature) can reach a real model. A default base URL
# is provided and the standard huanxin secrets file supplies the API key; the
# GUI server also runs envcfg auto-config as a fallback, so launching
# directly via `python3 quantum/gui/gui_app.py` works too.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

# Bypass the (sometimes-dead) system proxy for the huanxin endpoint only.
export no_proxy="${no_proxy:-},aihuanxin.cn"
export NO_PROXY="${NO_PROXY:-},aihuanxin.cn"

# Same public default as bin/qntelli-solve / qntelli.sh.
export HUANXIN_DP4_BASE_URL="${HUANXIN_DP4_BASE_URL:-https://aihuanxin.cn/kunlun/ingress/api/68b329/5c1bbb4620fc40eea9712a9771cece1b/ai-69be0918a51147689dc012f2d8b44fda/service-496501784fc44902b73b7bf90ddd88a4}"
if [[ -z "${QNTELLI_API_KEY:-}" && -f "$HOME/.codex/secrets/huanxin.env" ]]; then
  set +u; source "$HOME/.codex/secrets/huanxin.env"; set -u
  export QNTELLI_API_KEY="${HUANXIN_DP4_API_KEY:-}"
fi
export QNTELLI_BASE_URL="${QNTELLI_BASE_URL:-$HUANXIN_DP4_BASE_URL}"

PORT="${QNTELLI_GUI_PORT:-8090}"
echo "qntelli harness GUI -> http://127.0.0.1:${PORT}"
exec python3 quantum/gui/gui_app.py --port "${PORT}" "$@"
