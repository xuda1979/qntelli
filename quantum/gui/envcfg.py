#!/usr/bin/env python3
"""
Endpoint configuration bootstrap for the qntelli harness GUI.

The GUI's Solve button must reach a real model endpoint for general/custom
questions that have no analytic golden (e.g. a bespoke "XOR gate" circuit with
a required `xor_gate(a, b)` signature). Like the CLI launchers
(`bin/qntelli-solve`, `qntelli.sh`), this loads the huanxin DP4 endpoint
credentials BEFORE `solve.py` is imported (solve reads its env at import time).

It is idempotent and respectful of anything the caller has already exported:
  * never overwrites an already-set env var,
  * uses the public default base-URL only when none is configured,
  * reads the standard huanxin secrets file only when the API key is absent,
  * bypasses the (sometimes-dead) system proxy for the huanxin ingress only.

Tests launch the server without these credentials and set
QNTELLI_GUI_NO_AUTOCONFIG=1 so the deterministic no-endpoint fallback (and the
offline golden path) is exercised without any live network traffic.
"""
from __future__ import annotations

import os
from pathlib import Path

# Same public default the CLI launchers use (bin/qntelli-solve / qntelli.sh).
DEFAULT_HUANXIN_DP4_BASE_URL = (
    "https://aihuanxin.cn/kunlun/ingress/api/68b329/"
    "5c1bbb4620fc40eea9712a9771cece1b/"
    "ai-69be0918a51147689dc012f2d8b44fda/"
    "service-496501784fc44902b73b7bf90ddd88a4"
)


def configure_endpoint() -> None:
    """Populate the huanxin DP4 model-endpoint env vars (base URL + API key),
    exactly as the CLI launchers do, so solver/general questions can reach a
    real model. Safe to call multiple times; honours anything already set."""
    if os.environ.get("QNTELLI_GUI_NO_AUTOCONFIG") == "1":
        return

    # Only bypass the system proxy for the huanxin ingress host (a known flaky
    # system-proxy target), mirroring bin/qntelli-solve.
    if "aihuanxin.cn" not in os.environ.get("no_proxy", ""):
        np = (os.environ.get("no_proxy", "") + ",aihuanxin.cn").strip(",")
        os.environ["no_proxy"] = np
        os.environ["NO_PROXY"] = np

    # Default base URL only when none is configured (public constant, not a
    # secret — it is the same default the CLI launchers ship).
    if not (os.environ.get("QNTELLI_BASE_URL") or os.environ.get("HUANXIN_DP4_BASE_URL")):
        os.environ["HUANXIN_DP4_BASE_URL"] = DEFAULT_HUANXIN_DP4_BASE_URL
    os.environ.setdefault("QNTELLI_BASE_URL", os.environ["HUANXIN_DP4_BASE_URL"])

    # Load the standard huanxin secrets file for the API key only when the key
    # is not already supplied by the caller.
    if not (os.environ.get("QNTELLI_API_KEY") or os.environ.get("HUANXIN_DP4_API_KEY")):
        secret = Path(os.environ.get("HUANXIN_SECRET_FILE",
                                     "~/.codex/secrets/huanxin.env")).expanduser()
        if secret.exists():
            try:
                for line in secret.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("export ") and "=" in line:
                        k, _, v = line[7:].partition("=")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and v:
                            os.environ.setdefault(k, v)
            except Exception:
                pass
    os.environ.setdefault("QNTELLI_API_KEY", os.environ.get("HUANXIN_DP4_API_KEY", ""))
