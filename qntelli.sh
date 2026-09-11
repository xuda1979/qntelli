#!/usr/bin/env bash
set -uo pipefail
#
# qntelli.sh — the `qntelli` command for the qntelli quantum-computing
# engineering harness.
#
# Defaults to the same provider/endpoint/API key used by `claude -p huanxin
# -m dp4`: it reads HUANXIN_DP4_BASE_URL + HUANXIN_DP4_API_KEY from the huanxin
# secrets file, starts a local Anthropic->OpenAI proxy, and runs the
# source-built `qntelli` binary against it.
#
# Everything can be overridden via a local `qntelli.env` (created by
# install.sh) or env vars. No URLs or API keys are hardcoded in the binary.
#
# Usage:
#   qntelli --print "hi"     # headless one-shot
#   qntelli                  # interactive session
# --------------------------------------------------------------------------- #
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:$PATH"

# ─── Locate this folder even when invoked through a symlink on PATH ──────── #
resolve_symlink() {
  local target="$1" link
  while [[ -L "$target" ]]; do
    link="$(readlink "$target")"
    case "$link" in
      /*) target="$link" ;;
      *) target="$(dirname "$target")/$link" ;;
    esac
  done
  printf '%s\n' "$target"
}
SOURCE_FILE="$(resolve_symlink "${BASH_SOURCE[0]}")"
case "$SOURCE_FILE" in
  /*) ;;
  *) SOURCE_FILE="$PWD/$SOURCE_FILE" ;;
esac
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_FILE")" && pwd -P)"

# ─── 1. Defaults (huanxin dp4, mirroring `claude -p huanxin -m dp4`) ─────── #
HUANXIN_SECRET_FILE="${HUANXIN_SECRET_FILE:-$HOME/.codex/secrets/huanxin.env}"
HUANXIN_DP4_BASE_URL="${HUANXIN_DP4_BASE_URL:-https://aihuanxin.cn/kunlun/ingress/api/68b329/5c1bbb4620fc40eea9712a9771cece1b/ai-69be0918a51147689dc012f2d8b44fda/service-496501784fc44902b73b7bf90ddd88a4}"

# Allow a local qntelli.env to override everything (kept alongside the binary).
LOCAL_CONFIG="${QNTELLI_CONFIG_FILE:-${SCRIPT_DIR}/qntelli.env}"
if [[ -f "$LOCAL_CONFIG" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "$LOCAL_CONFIG"
  set -u
fi

# Load huanxin dp4 credentials (same secret file `claude -p huanxin` uses).
if [[ -f "$HUANXIN_SECRET_FILE" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "$HUANXIN_SECRET_FILE"
  set -u
fi

API_KEY="${QNTELLI_API_KEY:-${HUANXIN_DP4_API_KEY:-}}"
BASE_URL="${QNTELLI_BASE_URL:-${HUANXIN_DP4_BASE_URL:-}}"
MODEL="${QNTELLI_MODEL:-${HUANXIN_DP4_UPSTREAM_MODEL:-dp4}}"
APPCODE="${QNTELLI_APPCODE:-${HUANXIN_APPCODE:-}}"
MAX_INPUT_CHARS="${QNTELLI_MAX_INPUT_CHARS:-${HUANXIN_DP4_MAX_INPUT_CHARS:-440000}}"

if [[ -z "$API_KEY" ]]; then
  echo "error: no API key. Set QNTELLI_API_KEY (or HUANXIN_DP4_API_KEY in $HUANXIN_SECRET_FILE)." >&2
  exit 2
fi
if [[ -z "$BASE_URL" ]]; then
  echo "error: no base URL set. Set QNTELLI_BASE_URL or HUANXIN_DP4_BASE_URL." >&2
  exit 2
fi

# ─── 2. Find the source-built binary + proxy script ──────────────────────── #
BIN="${QNTELLI_BIN:-${SCRIPT_DIR}/qntelli}"
if [[ ! -x "$BIN" ]]; then
  echo "error: binary '$BIN' not found." >&2
  echo "       Run ./install.sh in $SCRIPT_DIR to build it." >&2
  exit 2
fi
PROXY_SCRIPT="${SCRIPT_DIR}/claude_huanxin_anthropic_proxy.py"
PROXY_PID=""
PROXY_PORT=""

cleanup_proxy() {
  [[ -n "$PROXY_PID" ]] && kill "$PROXY_PID" >/dev/null 2>&1 || true
}
trap cleanup_proxy EXIT INT TERM

free_local_port() {
  python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'
}

# ─── 3. Decide direct vs proxied and launch accordingly ──────────────────── #
# If the upstream is Anthropic-compatible (path ends in /anthropic), talk to
# it directly. Otherwise route through the local Anthropic->OpenAI proxy
# (e.g. huanxin deployments, which speak the OpenAI chat API).
DIRECT=0
case "$BASE_URL" in
  */anthropic) DIRECT=1 ;;
esac

if [[ "$DIRECT" -eq 0 ]]; then
  if [[ ! -f "$PROXY_SCRIPT" ]]; then
    echo "error: proxy script not found at $PROXY_SCRIPT" >&2
    exit 2
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 is required to proxy the OpenAI-compatible endpoint" >&2
    exit 2
  fi
  PROXY_PORT="$(free_local_port)"
  LOG_FILE="${TMPDIR:-/tmp}/qntelli-proxy-${PROXY_PORT}.log"
  AUTH="Bearer"
  if [[ -n "$APPCODE" ]]; then
    APPCODE_ARG=(--appcode "$APPCODE")
  else
    APPCODE_ARG=()
  fi
  echo "qntelli: starting local proxy on port $PROXY_PORT (log: $LOG_FILE)" >&2
  python3 "$PROXY_SCRIPT" \
    --host 127.0.0.1 --port "$PROXY_PORT" \
    --upstream-url "$BASE_URL" \
    --upstream-token "$AUTH $API_KEY" \
    --model-name "$MODEL" \
    --max-input-chars "$MAX_INPUT_CHARS" \
    "${APPCODE_ARG[@]+"${APPCODE_ARG[@]}"}" >"$LOG_FILE" 2>&1 &
  PROXY_PID=$!
  ENDPOINT="http://127.0.0.1:${PROXY_PORT}"
  local_key="qntelli-local-proxy"
  echo "qntelli: waiting for proxy to be ready..." >&2
  ready=0
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${PROXY_PORT}/health" >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "$PROXY_PID" 2>/dev/null; then
      break
    fi
    sleep 0.2
  done
  if [[ "$ready" -eq 0 ]]; then
    echo "error: local proxy did not become ready (see $LOG_FILE)" >&2
    exit 1
  fi
  echo "qntelli: proxy ready on $ENDPOINT" >&2
else
  ENDPOINT="$BASE_URL"
  local_key="$API_KEY"
  echo "qntelli: connecting directly to $ENDPOINT" >&2
fi

echo "qntelli: binary=$BIN model=$MODEL" >&2

# ─── 4. Launch the binary ────────────────────────────────────────────────── #
export CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="${CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC:-1}"
export DISABLE_TELEMETRY="${DISABLE_TELEMETRY:-1}"
export ANTHROPIC_BASE_URL="$ENDPOINT"
export ANTHROPIC_API_KEY="$local_key"
export ANTHROPIC_AUTH_TOKEN="$local_key"
export ANTHROPIC_MODEL="$MODEL"
export ANTHROPIC_SMALL_FAST_MODEL="$MODEL"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="$MODEL"
export ANTHROPIC_DEFAULT_SONNET_MODEL="$MODEL"
export ANTHROPIC_DEFAULT_OPUS_MODEL="$MODEL"
export CLAUDE_CODE_SUBAGENT_MODEL="$MODEL"
export CLAUDE_CODE_EFFORT_LEVEL="max"
exec "$BIN" --model "$MODEL" --effort max "$@"
