#!/usr/bin/env bash
#
# build.sh — Build the standalone `qntelli` binary from this repo's source.
#
# Portable: works on macOS and Linux. Run it on the TARGET platform so Bun
# compiles a native binary for that platform (macOS -> Mach-O, Linux -> ELF).
#
# Requirements:
#   * Bun >= 1.2  (https://bun.sh — install with: curl -fsSL https://bun.sh/install | bash)
#
# Output: ./qntelli  (a standalone, self-contained executable)
#
# This build NEVER uses the installed `claude` binary — only this source.
#
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# 1. Ensure bun is available
if ! command -v bun >/dev/null 2>&1; then
  echo "error: 'bun' not found on PATH. Install it: curl -fsSL https://bun.sh/install | bash" >&2
  exit 2
fi
echo "==> Using bun: $(bun --version)"

# 2. Install dependencies (platform-correct native binaries for THIS machine)
echo "==> Installing dependencies (platform-correct for $(uname -s)/$(uname -m))..."
bun install

# 3. Compile the standalone agent from source
echo "==> Compiling qntelli from src/entrypoints/cli-bundle.ts ..."
bun build src/entrypoints/cli-bundle.ts \
  --compile \
  --outfile=qntelli \
  --target=bun

chmod +x qntelli
echo "==> Done."
echo "    Binary: $(pwd)/qntelli ($(file -b qntelli | cut -d, -f1-2))"
echo "    Verify: ./qntelli --version"
