#!/usr/bin/env bash
#
# install.sh — THE one installation script for `qntelli`, the quantum-
# computing science & engineering agent harness.
#
#   1. installs Bun (if needed)
#   2. installs platform-correct dependencies
#   3. compiles the standalone `qntelli` binary from this repo's source
#   4. installs the `qntelli` wrapper onto PATH
#
# Default connection settings come from the same source as `claude -p huanxin
# -m dp4` (HUANXIN_DP4_BASE_URL + HUANXIN_DP4_API_KEY in ~/.codex/secrets/
# huanxin.env). Any of these can be overridden by creating a `qntelli.env` in
# this folder (the wrapper reads it next to itself).
#
# The configuration written to qntelli.env is chmod 600 — it may hold a live
# secret. No credentials are baked into the binary or committed anywhere.
#
# Run on the target machine inside this folder:
#
#   ./install.sh
#
# Idempotent — safe to re-run (reuses an existing Bun, rebuilds in place).
#
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> qntelli installer"
echo "==> Platform: $(uname -s)/$(uname -m)"

# ─── 0. Prerequisites ────────────────────────────────────────────────────── #
if ! command -v curl >/dev/null 2>&1 && ! command -v bun >/dev/null 2>&1; then
  echo "error: 'curl' is required (the Bun installer needs it). Install it first." >&2
  exit 2
fi

# ─── 1. Bun ──────────────────────────────────────────────────────────────── #
if ! command -v bun >/dev/null 2>&1; then
  echo "==> Installing Bun..."
  curl -fsSL https://bun.sh/install | bash
  export PATH="$HOME/.bun/bin:$PATH"
fi
command -v bun >/dev/null 2>&1 || { echo "error: bun not available after install" >&2; exit 2; }
echo "==> bun: $(bun --version)"

# ─── 2. Dependencies ─────────────────────────────────────────────────────── #
echo "==> Installing dependencies (platform-correct for $(uname -s)/$(uname -m))..."
bun install

# ─── 3. Optional: write a qntelli.env override from the huanxin dp4 config ─
# If the user has not created one, seed it from the same defaults the wrapper
# uses (huanxin dp4). The wrapper will still source ~/.codex/secrets/huanxin.env
# for the live API key, so no secret is baked here.
CONFIG_FILE="${PWD}/qntelli.env"
if [[ ! -f "$CONFIG_FILE" ]]; then
  HUANXIN_SECRET_FILE="${HUANXIN_SECRET_FILE:-$HOME/.codex/secrets/huanxin.env}"
  if [[ -f "$HUANXIN_SECRET_FILE" ]]; then
    set +u; source "$HUANXIN_SECRET_FILE"; set -u
  fi
  DEF_URL="${QNTELLI_BASE_URL:-${HUANXIN_DP4_BASE_URL:-https://aihuanxin.cn/kunlun/ingress/api/68b329/5c1bbb4620fc40eea9712a9771cece1b/ai-69be0918a51147689dc012f2d8b44fda/service-496501784fc44902b73b7bf90ddd88a4}}"
  DEF_MODEL="${QNTELLI_MODEL:-${HUANXIN_DP4_UPSTREAM_MODEL:-dp4}}"
  umask 077
  cat > "$CONFIG_FILE" <<CFGEOF
# qntelli connection config — created by install.sh on $(date '+%Y-%m-%d %H:%M').
# Keep this file private (chmod 600) and out of any shared repository.
# The live API key is read from ~/.codex/secrets/huanxin.env (HUANXIN_DP4_API_KEY).
QNTELLI_BASE_URL=${DEF_URL}
QNTELLI_MODEL=${DEF_MODEL}
CFGEOF
  chmod 600 "$CONFIG_FILE"
  echo "==> Wrote default ${CONFIG_FILE} (chmod 600)."
fi

# ─── 4. Compile the qntelli binary ──────────────────────────────────────── #
echo "==> Compiling qntelli from src/entrypoints/cli-bundle.ts ..."
bun build src/entrypoints/cli-bundle.ts \
  --compile \
  --outfile=qntelli \
  --target=bun

chmod +x qntelli
echo "==> Built: $(pwd)/qntelli"
./qntelli --version || true

# ─── 4b. ripgrep (the Grep tool uses the system `rg` on plain-bun builds) ─ #
if ! command -v rg >/dev/null 2>&1; then
  echo "==> warning: 'rg' (ripgrep) not found — the Grep tool will not work." >&2
  if [[ "$(id -u)" -eq 0 ]] && command -v apt-get >/dev/null 2>&1; then
    apt-get install -y ripgrep || true
  elif [[ "$(id -u)" -eq 0 ]] && command -v dnf >/dev/null 2>&1; then
    dnf install -y ripgrep || true
  elif [[ "$(id -u)" -eq 0 ]] && command -v yum >/dev/null 2>&1; then
    yum install -y ripgrep || true
  else
    echo "==> (install ripgrep: apt-get/dnf install ripgrep)" >&2
  fi
fi

# ─── 5. Install the `qntelli` wrapper onto PATH ──────────────────────────── #
if [[ "$(id -u)" -eq 0 ]]; then
  BIN_DIR="/usr/local/bin"      # root: system-wide
else
  BIN_DIR="$HOME/.local/bin"    # non-root: user-local
fi
mkdir -p "$BIN_DIR"

chmod +x "$PWD/qntelli.sh"
ln -sf "$PWD/qntelli.sh" "$BIN_DIR/qntelli"
ln -sf "$PWD/qntelli"    "$BIN_DIR/qntelli-bin"

# Make sure $BIN_DIR is on PATH for future shells (non-root case).
if [[ "$(id -u)" -ne 0 ]]; then
  PROFILE_LINE="export PATH=\"$BIN_DIR:\$PATH\""
  for profile in "$HOME/.bashrc" "$HOME/.profile"; do
    if [[ -f "$profile" ]] && ! grep -qF "$BIN_DIR" "$profile"; then
      echo "$PROFILE_LINE" >> "$profile"
      echo "==> Added '$BIN_DIR' to PATH in $profile"
    fi
  done
fi

echo ""
echo "==> Done."
echo "    Binary:   $(pwd)/qntelli"
echo "    Wrapper:  $BIN_DIR/qntelli  (reads $(pwd)/qntelli.env + ~/.codex/secrets/huanxin.env)"
echo ""
echo "    Usage:"
echo "      qntelli --print \"hi\"   # headless one-shot"
echo "      qntelli                 # interactive session"
if [[ "$(id -u)" -ne 0 ]]; then
  echo ""
  echo "    Note: open a new shell (or log out/in) if '$BIN_DIR' was not on PATH yet."
fi
