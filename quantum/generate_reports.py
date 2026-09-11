#!/usr/bin/env python3
"""
generate_reports.py — harness-driven generation of the top-quality case-study reports.

This is the SINGLE harness entry point that DELIVERS the three case-study
research reports (QPE, Grover, Bernstein-Vazirani/PennyLane). It does the work
entirely through harness components — no hand-written build scripts:

    solve()          -> one-enter verified code, measured outcome, verify detail
    qas_agent        -> QAS 线路寻优 circuit optimisation (depth/2q/fidelity report)
    experience       -> live knowledge-base pass-rate stats
    report_gen       -> data-driven top-quality .docx report emission

Usage:
  python3 quantum/generate_reports.py --out-dir reports            # live one-enter solves
  python3 quantum/generate_reports.py --out-dir reports --offline  # goldens (no endpoint)
  python3 quantum/generate_reports.py --only grover                # just one case study

Every numeric figure in the emitted reports comes from the run above; report_gen
computes the correct analytic theory values from first principles.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "reports"))

import solve as _solve
import qas_agent as _qas
import report_gen as _report_gen

# (id, report title, classified question for the one-enter solver)
CASE_STUDIES = [
    ("qpe", None, "Write a complete Qiskit program using Quantum Phase Estimation (QPE) "
                  "to estimate the phase theta=0.125 of a unitary U with U|1>=exp(2*pi*i*theta)|1>, "
                  "using a 4-qubit phase register. Report the estimated theta in [0,1)."),
    ("grover", None, "Write a complete Qiskit program implementing Grover's algorithm on 3 qubits "
                     "marking |101> with one iteration. The top measured bitstring must be 101 with "
                     "elevated probability (~0.78). Print JSON probs."),
    ("bv_pl", None, "Write a complete PennyLane program implementing Bernstein-Vazirani with secret 101 "
                    "on 3 data wires using default.qubit (4000 shots). Measure each data wire with "
                    "qml.sample(qml.PauliZ) and report the recovered secret bitstring as the most probable "
                    "outcome. Print JSON probs."),
]

# QAS optimisation configuration per case study (from the harness blueprint ②).
_QAS_CFG = {
    "qpe": {"ref_kind": "value", "value_key": "phase", "tol": 0.05, "ref": {"theta": 0.125}},
    "grover": {"ref_kind": "probs", "tol": 0.35, "ref": {"101": 0.78}},
    "bv_pl": None,   # BV report does not carry a QAS optimisation stage
}


def _solve_case(algo_id: str, question: str, offline: bool):
    """Run the one-enter solver; return (ok_verdict, cls_dict)."""
    cls = _solve.classify(question)
    if offline:
        verdict = _solve.solve(question, mode="qntelli", offline=True)
    else:
        verdict = _solve.solve(question, mode="qntelli", offline=False)
    return verdict, cls


def _run_qas(algo_id: str, cls, sdk):
    """Run the QAS 线路寻优 agent; return a dict with qas_table/selected/report or {}."""
    cfg = _QAS_CFG.get(algo_id)
    if cfg is None:
        return {}
    try:
        from qiskit import QuantumCircuit, ClassicalRegister
        qc = QuantumCircuit(4, 4) if algo_id == "qpe" else QuantumCircuit(3, 3)
        if algo_id == "qpe":
            # Controlled-U^(2^k) QPE for theta=0.125, 4 phase qubits + 1 eigenstate qubit.
            import numpy as np
            t = 4
            qc = QuantumCircuit(t + 1, t)
            qc.h(range(t)); qc.x(t)
            for k in range(t):
                qc.cp(2 * np.pi * 0.125 * (2 ** k), k, t)
            for j in range(t // 2):
                qc.swap(j, t - 1 - j)
            for i in range(t):
                for l in range(i):
                    qc.cp(-np.pi / 2 ** (i - l), l, i)
                qc.h(i)
            qc.measure(range(t), range(t))
        elif algo_id == "grover":
            n, marked = 3, 5
            qc = QuantumCircuit(n, n); qc.h(range(n))
            zero = [i for i in range(n) if not ((marked >> i) & 1)]
            qc.x(zero); qc.h(n - 1); qc.mcx(list(range(n - 1)), n - 1); qc.h(n - 1); qc.x(zero)
            qc.h(range(n)); qc.x(range(n)); qc.h(n - 1); qc.mcx(list(range(n - 1)), n - 1); qc.h(n - 1); qc.x(range(n)); qc.h(range(n))
            qc.measure(range(n), range(n))
        res = _qas.qas_search(circuit=qc, ref=cfg.get("ref"), tol=cfg.get("tol", 0.06),
                              max_depth=None, max_2q=None, shots=4000,
                              ref_kind=cfg.get("ref_kind", "probs"),
                              value_key=cfg.get("value_key"))
        cands = res.get("candidates") or []
        sel = res.get("selected") or {}
        return {
            "qas_table": [[c.get("name"), c.get("depth"), c.get("n2q"),
                           round(c.get("fidelity", 1.0), 4), c.get("satisfies", True)] for c in cands],
            "qas_selected": sel.get("name"),
            "qas_report": (res.get("report") or "")[:1500],
        }
    except Exception as e:  # QAS is best-effort: a failure must not block the report
        print(f"  [warn] QAS skipped for {algo_id}: {e}", file=sys.stderr)
        return {}


def _run_hardware(algo_id: str, verdict: dict, cls: dict) -> dict:
    """Run the case-study circuit through the Model Hardware Standard emulator
    tier (real vendor compiler + offline physics sampling) so the report covers
    the full stack: code -> QAS -> simulation -> hardware -> verification.

    Returns a {'hardware': {...}} context fragment, or {} on any failure (the
    hardware stage is best-effort and must never block report emission). Only
    the OFFLINE emulator/simulation tiers are used — a QPU submission is
    credential- AND opt-in gated and never happens implicitly here.
    """
    if algo_id not in ("qpe", "grover", "bv_pl"):
        return {}
    try:
        from qiskit import QuantumCircuit
        import hardware.standard as _hw
    except Exception as e:
        print(f"  [warn] hardware import skipped for {algo_id}: {e}", file=sys.stderr)
        return {}

    # Build the same Qiskit reference circuit each case study solved for.
    try:
        if algo_id == "grover":
            n, marked = 3, 5
            qc = QuantumCircuit(n, n); qc.h(range(n))
            zero = [i for i in range(n) if not ((marked >> i) & 1)]
            qc.x(zero); qc.h(n - 1); qc.mcx(list(range(n - 1)), n - 1); qc.h(n - 1); qc.x(zero)
            qc.h(range(n)); qc.x(range(n)); qc.h(n - 1); qc.mcx(list(range(n - 1)), n - 1); qc.h(n - 1); qc.x(range(n)); qc.h(range(n))
            qc.measure(range(n), range(n))
            checks_ref = {"101": 0.78}
        elif algo_id == "qpe":
            import numpy as np
            t = 4
            qc = QuantumCircuit(t + 1, t)
            qc.h(range(t)); qc.x(t)
            for k in range(t):
                qc.cp(2 * np.pi * 0.125 * (2 ** k), k, t)
            for j in range(t // 2):
                qc.swap(j, t - 1 - j)
            for i in range(t):
                for l in range(i):
                    qc.cp(-np.pi / 2 ** (i - l), l, i)
                qc.h(i)
            qc.measure(range(t), range(t))
            checks_ref = None  # QPE returns a scalar phase; report states only
        else:  # bv_pl uses PennyLane; map to the equivalent Qiskit BV oracle
            # Mirror the harness's verified BV golden exactly: ancilla in |->,
            # CX controls in REVERSED qubit order so the MSB-first measured key
            # equals the secret (Qiskit counts are MSB-first, q[n-1]..q[0]).
            n_bits = 3
            secret = "101"
            qc = QuantumCircuit(n_bits + 1, n_bits)
            qc.h(range(n_bits)); qc.x(n_bits); qc.h(n_bits)   # ancilla -> |->
            for i, b in zip(reversed(range(n_bits)), secret):
                if b == "1":
                    qc.cx(i, n_bits)
            qc.h(range(n_bits))
            qc.measure(range(n_bits), range(n_bits))
            checks_ref = {"101": 1.0}

        device = "quantinuum:h2-1e"     # best offline emulator (pecos + vendor compile)
        rec = _hw.submit_job(qc, device, shots=4000, seed=7, algorithm=algo_id)
        total = sum(rec.counts.values()) or 1
        probs = {k: v / total for k, v in rec.counts.items()}
        checks = {}
        if checks_ref:
            for state, expect in checks_ref.items():
                got = probs.get(state, 0.0)
                # pick a tolerance matched to each family's analytic precision
                tol = 0.02 if algo_id == "bv_pl" else 0.06
                checks[state] = {"expected": float(expect),
                                 "observed": round(got, 4),
                                 "ok": abs(got - expect) <= tol}
        hw = {"device": device, "tier": rec.tier, "status": rec.status,
              "checks": checks, "detail": rec.detail,
              "gate_family": getattr(rec, "gate_family", "native ion-trap")}
        # Honest label on the tier; never conflate emulator with real QPU.
        return {"hardware": hw}
    except Exception as e:  # best-effort: a hardware failure must not block the report
        print(f"  [warn] hardware emulator skipped for {algo_id}: {e}", file=sys.stderr)
        return {}


def _build_ctx(algo_id, verdict, cls, sdk):
    """Assemble the report_gen run context from the harness solve verdict."""
    v = verdict.get("verification") or {}
    ctx = {
        "algorithm": algo_id,
        "code": verdict.get("code", ""),
        "verify": v.get("detail", ""),
        "stage": v.get("stage", algo_id),
        "attempts": verdict.get("attempts", 1),
        "code_sdk": sdk,
    }
    # Measured distribution retained by the harness verify step.
    probs = v.get("probs")
    if probs:
        ctx["dist"] = probs
    elif algo_id == "qpe" and v.get("phase") is not None:
        # QPE produces a scalar phase, not a bit-string distribution.
        ctx["dist"] = {"phase": v.get("phase")}
    return ctx


def generate_all(out_dir: str, offline: bool, only: str | None) -> int:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    for algo_id, _title, question in CASE_STUDIES:
        if only and algo_id != only:
            continue
        print(f"=== Case study: {algo_id} ({'offline golden' if offline else 'live one-enter'}) ===")
        try:
            verdict, cls = _solve_case(algo_id, question, offline)
        except Exception as e:
            print(f"  [FAIL] solve raised: {e}"); continue
        if not verdict.get("ok"):
            print(f"  [FAIL] solve did not verify ({verdict.get('stage')}): {verdict.get('detail','')[:120]}"); continue
        sdk = cls.get("sdk", "qiskit")
        ctx = _build_ctx(algo_id, verdict, cls, sdk)
        # Attach the measured distribution from the solve output when the
        # solve provides it (probs for grover/bv, phase for qpe).
        if v := verdict.get("verification") or {}:
            pass
        # QAS optimization (when applicable).
        ctx.update(_run_qas(algo_id, cls, sdk))
        # Model hardware standard (ion-trap emulator) — full-stack coverage.
        ctx.update(_run_hardware(algo_id, verdict, cls))
        # Rewrite title via report_gen (uses meta name).
        out_path = out_dir / f"Case_Study_{['QPE', 'Grover', 'BernsteinVazirani_PennyLane'][['qpe','grover','bv_pl'].index(algo_id)]}.docx"
        try:
            emitted = _report_gen.generate_report(ctx, out_path, title=None)
            n_ok += 1
            print(f"  [OK] wrote {emitted}")
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  [FAIL] report generation: {e}")
    return n_ok


def main() -> int:
    ap = argparse.ArgumentParser(description="harness-driven case-study report generation")
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--offline", action="store_true",
                    help="use solver offline goldens (no model endpoint); deterministic")
    ap.add_argument("--only", choices=[a for a, _, _ in CASE_STUDIES], default=None)
    args = ap.parse_args()
    n = generate_all(args.out_dir, args.offline, args.only)
    print(f"\nGenerated {n}/{3 if not args.only else 1} case-study report(s).")
    return 0 if n > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
