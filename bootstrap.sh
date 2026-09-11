#!/usr/bin/env bash
#
# bootstrap.sh — compatibility alias for install.sh (the ONE installation
# script). Everything happens in install.sh: Bun + dependencies + qntelli
# binary + `qntelli` wrapper + huanxin dp4 config check.
#
# Run:  ./bootstrap.sh     (same as ./install.sh)
#
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/install.sh"
