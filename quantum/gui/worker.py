#!/usr/bin/env python3
"""
qntelli GUI worker - runs harness operations in an isolated subprocess so that
a crash (e.g. a C-extension segfault in quantum simulation) cannot take down
the GUI server. Called by gui_app.py via subprocess with a JSON payload on
stdin; writes a JSON result on stdout.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUANTUM = HERE.parent
sys.path.insert(0, str(QUANTUM))

# Ensure the model-endpoint env (base URL + API key) is populated exactly like
# the CLI launchers. When spawned by gui_app.py the env is already inherited and
# this is a no-op (idempotent); when run standalone this lets the online solve
# reach a real model for general/custom questions. Idempotent + respects
# caller-set env; QNTELLI_GUI_NO_AUTOCONFIG=1 opts out.
sys.path.insert(0, str(HERE))
import envcfg  # noqa: E402
envcfg.configure_endpoint()


def op_qas(experiment: str) -> dict:
    import qas_agent
    from orchestrator.orchestrator import _build_circuit, _REFERENCE
    qc = _build_circuit(experiment)
    ref = _REFERENCE.get(experiment)
    res = qas_agent.qas_search(circuit=qc, ref=ref, tol=0.08, shots=2000,
                               max_depth=None, max_2q=None)
    return {"rc": 0, "result": res}


def op_solve(question: str, online: bool) -> dict:
    """Run the one-enter solver in this isolated subprocess. The model-backed
    (online) path for general questions RUNS generated quantum code (importing
    qiskit/qiskit_aer C-extensions) — a segfault there must never take down the
    GUI server, so it runs here, crash-isolated from the server.

    Mirrors gui_app.api.solver_solve: related-family questions always use the
    offline golden (never require a model); general/custom questions use the
    online path when requested AND an endpoint is configured, else a clear
    no-endpoint error."""
    import solve
    try:
        cls = solve.classify(question)
        has_golden = cls.get("ref_type") is not None
    except Exception:
        has_golden = False
    if has_golden:
        # Supported family → always offline golden (no model needed).
        res = solve.solve(question, mode="qntelli", offline=True)
        res["solve_mode"] = "offline-golden"
        return {"rc": 0, "result": res}
    # GENERAL / CUSTOM question → auto-online when an endpoint is configured
    # (so clicking Solve in the GUI actually produces code), else a clear,
    # non-silent error. `online` still forces/permits this even if the caller
    # didn't explicitly request it.
    if not solve.BASE_URL or not solve.API_KEY:
        return {"rc": 0, "result": {
            "ok": False, "attempts": 0, "stage": "no-endpoint",
            "detail": ("no model endpoint configured (set QNTELLI_BASE_URL + "
                       "QNTELLI_API_KEY) — cannot produce code for this custom "
                       "question offline.")}}
    res = solve.solve(question, mode="qntelli", offline=False)
    res["solve_mode"] = "online"
    return {"rc": 0, "result": res}


def main():
    payload = json.loads(sys.stdin.read() or "{}")
    op = payload.get("op")
    args = payload.get("args", {})
    try:
        if op == "qas":
            out = op_qas(args.get("experiment", "bell"))
        elif op == "solve":
            out = op_solve(args.get("question", ""),
                           bool(args.get("online", False)))
        else:
            out = {"rc": 1, "error": "unknown op " + str(op)}
        print(json.dumps({"ok": True, "result": out}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e),
                          "type": type(e).__name__}))


if __name__ == "__main__":
    main()
