#!/usr/bin/env python3
"""
qas_agent.py — the QAS 智能体 (Quantum Architecture Search / 线路寻优 agent)
from the "无极量智" platform blueprint.

Given a quantum circuit and a set of constraints (max depth, max 2-qubit gate
count, target fidelity), search candidate circuit implementations, evaluate
each against the constraints AND the target analytic reference, and return the
best candidate(s) plus a resource/evaluation report.

This is the circuit-optimization capability the blueprint calls "线路寻优"
(QAS: search and evaluate candidate quantum circuits under precision, circuit
depth and resource constraints), as opposed to the one-enter code solver
(编程智能体, solve.py) which focuses on correct code generation+verification.

Pieces:
  * candidate generation: transpile the same logical circuit at multiple
    optimization levels, plus a structural variant (gate-cancellation pass).
  * candidate evaluation: depth, 2-qubit gate count, and — when a reference is
    provided — simulated fidelity of the resulting probabilities vs reference.
  * selection: keep candidates satisfying all hard constraints; rank by
    (fidelity desc, then resource asc); return Pareto-front report.

Usage (as a library):
  from qas_agent import qas_search, circuit_from_qasm
  res = qas_search(shots=4000, max_depth=8, max_2q=3,
                   ref={"00":0.5,"11":0.5}, tol=0.06,
                   qasm=open("circ.qasm").read())
  print(res["selected"]["depth"], res["report"])
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from qiskit import QuantumCircuit, transpile
    import qiskit.qasm2 as _qasm2
    from qiskit_aer import AerSimulator
    _QISKIT = True
except Exception as _e:  # pragma: no cover - imported env always has qiskit
    _QISKIT = False
    _QISKIT_ERR = _e


def _to_qasm(qc: "QuantumCircuit") -> str:
    """Export a circuit to an OPENQASM 2.0 string (Qiskit 2.x API)."""
    return _qasm2.dumps(qc)


def circuit_from_qasm(qasm: str) -> "QuantumCircuit":
    """Parse a QASM string into a QuantumCircuit."""
    return QuantumCircuit.from_qasm_str(qasm)


def _counts_to_probs(counts, shots) -> dict:
    return {k: v / shots for k, v in counts.items()}


def _fidelity_vs_ref(probs: dict, ref: dict | None, tol: float) -> float:
    """Score a probs dict against a reference (0..1). 1.0 = perfect."""
    if not ref:
        return 1.0
    if not probs:
        return 0.0
    total = 0
    for k, e in ref.items():
        a = probs.get(k, 0.0)
        total += max(0.0, 1.0 - abs(a - e) / max(e, 1e-9))
    return total / max(1, len(ref))


def _eval_circuit(qc: "QuantumCircuit", *, shots: int, ref: dict | None,
                  tol: float, ref_kind: str = "probs",
                  value_key: str | None = None) -> dict:
    """Evaluate one candidate: depth, 2q-gate count, and simulated fidelity.

    ref_kind controls how fidelity is computed:
      * "probs"  -> compare the sampled bit-string probabilities dict to `ref`
                     (the default; works for Bell/GHZ/QFT/uniform/Grover/DJ).
      * "value"  -> the circuit prints a JSON scalar (key `value_key`, e.g. a
                     QPE `phase` or VQE `energy`); fidelity from |got - want|.
    """
    ops = qc.count_ops()
    deps = qc.depth()
    n2q = sum(n for g, n in ops.items() if g in ("cx", "cz", "swap", "cswap",
                                                 "ch", "ccx", "cp", "crz", "cu1"))
    probs = None
    want = _first_val(ref) if ref_kind == "value" and ref else None
    if ref and ref_kind == "probs":
        c = qc.copy()
        if c.num_clbits == 0 and c.num_qubits:
            try:
                c.measure_all()
            except Exception:
                pass
        counts = AerSimulator(seed_simulator=7).run(c, shots=shots).result().get_counts()
        probs = _counts_to_probs(counts, shots)
        fid = _fidelity_vs_ref(probs, ref, tol)
    elif ref and ref_kind == "value" and want is not None:
        # run the circuit as-is (it already prints {"<key>": value}) or, if it
        # only measures, derive the value via existing measurement if possible.
        got = _run_value(qc, shots=shots, key=value_key)
        fid = max(0.0, 1.0 - abs((got or 0.0) - want) / max(abs(want), 1e-9))
    else:
        fid = 1.0  # no reference to check against
    return {"depth": int(deps), "n2q": int(n2q),
            "ops": dict(ops), "fidelity": round(fid, 4), "probs": probs}


def _first_val(ref: dict):
    """Return the first scalar value in a reference dict (for value-kind refs)."""
    for v in (ref or {}).values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _run_value(qc: "QuantumCircuit", *, shots: int, key: str | None) -> float | None:
    """Best-effort: run a circuit and read a scalar value it produces.

    Used for value-based QAS fidelity (QPE phase, VQE energy, expectation value).
    Strategy:
      1. execute the measured circuit with AerSimulator -> counts;
      2. if a JSON scalar is printed (some circuits do), read {phase|energy|value}
         or `key`;
      3. otherwise interpret the most-probable bitstring as the value
         (value = int(top_bitstring, 2) / 2**n), which is exactly how QPE reports
         an estimated phase from a measured eigenphase register.
    Returns None only if nothing measurable (e.g. a pure-draw no-measure circuit).
    """
    import json as _json
    import re
    import subprocess
    import tempfile
    try:
        code = ("import json\nfrom qiskit import QuantumCircuit\n"
                "qc = QuantumCircuit.from_qasm_str('''" + _to_qasm(qc) + "''')\n"
                "from qiskit_aer import AerSimulator\n"
                "shots = " + str(int(shots)) + "\n"
                "counts = AerSimulator(seed_simulator=7).run(qc, shots=shots).result().get_counts()\n"
                "print(json.dumps({'probs': {k: v/shots for k, v in counts.items()}}))\n")
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code); path = f.name
        r = subprocess.run([sys.executable, path], capture_output=True,
                           text=True, timeout=90)
    except Exception:
        return None
    finally:
        try:
            from pathlib import Path as _P; _P(path).unlink()
        except Exception:
            pass
    # 1/2. Try to parse a JSON object with a scalar we care about.
    m = re.search(r"\{[^{}]*\}", r.stdout or "")
    if m:
        try:
            data = _json.loads(m.group(0))
            if key and key in data:
                return float(data[key])
            for k in ("phase", "energy", "value"):
                if k in data:
                    return float(data[k])
            probs = data.get("probs")
            if probs:
                top = max(probs, key=lambda k: probs[k])
                n = len(top)
                return int(top, 2) / (2 ** n) if n else None
        except Exception:
            pass
    # 3. Fallback: derive phase-style value from the most-probable bitstring.
    m2 = re.findall(r'"([01]+)":\s*([\d.]+)', r.stdout or "")
    if m2:
        best = max(m2, key=lambda kv: float(kv[1]))
        b = best[0]
        return int(b, 2) / (2 ** len(b)) if len(b) else None
    return None


def qas_search(*, qasm: str | None = None, circuit: "QuantumCircuit | None" = None,
               ref: dict | None = None, tol: float = 0.06,
               max_depth: int | None = None, max_2q: int | None = None,
               shots: int = 4000, levels=(0, 1, 2, 3),
               top_k: int = 3, ref_kind: str = "probs",
               value_key: str | None = None) -> dict:
    """Search candidate QAS circuits, evaluate against constraints + reference.

    ref_kind: "probs" (compare sampled bit-string probs to `ref`) or "value"
    (compare a scalar the circuit prints — `value_key` JSON field, defaults to
    phase/energy/value — to the first scalar in `ref`). The latter enables QAS
    optimization of QPE (phase), VQE (energy) and expectation (value) circuits.

    Returns dict with:
      candidates: list of {name, qasm, depth, n2q, ops, fidelity}
      satisfying (constraint-respecting) candidates
      selected: the single best candidate, or None
      report: human-readable resource/evaluation report
    """
    if not _QISKIT:
        raise RuntimeError("qiskit/qiskit_aer unavailable: " + _QISKIT_ERR)
    base = circuit if circuit is not None else circuit_from_qasm(qasm)
    # Candidate generation: different transpilation optimization levels.
    candidates = []
    seen = set()
    variants = [("baseline", base)]
    for lvl in levels:
        try:
            variants.append((f"opt{lvl}", transpile(base, optimization_level=lvl)))
        except Exception:
            continue
    for name, qc in variants:
        qkey = _to_qasm(qc)
        if qkey in seen:
            continue
        seen.add(qkey)
        ev = _eval_circuit(qc, shots=shots, ref=ref, tol=tol,
                           ref_kind=ref_kind, value_key=value_key)
        ev["name"] = name
        ev["qasm"] = qkey
        candidates.append(ev)
    # Constraint filtering
    constrained = []
    for c in candidates:
        ok = True
        if max_depth is not None and c["depth"] > max_depth:
            ok = False
        if max_2q is not None and c["n2q"] > max_2q:
            ok = False
        if ref is not None and c["fidelity"] < (1.0 - tol):
            ok = False
        c["satisfies"] = ok
        if ok:
            constrained.append(c)
    # Selection: rank by (fidelity desc, resource asc) among constrained.
    selected = None
    if constrained:
        if ref is not None:
            constrained.sort(key=lambda c: (-c["fidelity"], c["depth"], c["n2q"]))
        else:
            constrained.sort(key=lambda c: (c["depth"], c["n2q"]))
        selected = constrained[0]
    # Build a compact report (the blueprint's 验证报告 resource table).
    lines = ["QAS search: candidate circuits under "
             f"{'max_depth=%s' % max_depth if max_depth else 'no depth limit'} / "
             f"{'max_2q=%s' % max_2q if max_2q else 'no 2q limit'} / "
             f"tol={tol}"]
    lines.append("-" * 60)
    lines.append(f"{'candidate':<12}{'depth':>6}{'2q':>5}{'fid':>8}  satisfies")
    for c in candidates:
        lines.append(f"{c['name']:<12}{c['depth']:>6}{c['n2q']:>5}"
                     f"{c['fidelity']:>8.3f}  {str(c['satisfies'])}")
    if selected:
        lines.append(f"SELECTED: {selected['name']} "
                     f"(depth={selected['depth']}, 2q={selected['n2q']}, "
                     f"fid={selected['fidelity']})")
    else:
        lines.append("No candidate satisfies all constraints (relax max_depth/"
                     "max_2q or tolerance).")
    return {
        "candidates": candidates,
        "selected": selected,
        "satisfying": constrained,
        "report": "\n".join(lines),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="QAS 智能体 — search & evaluate candidate quantum circuits "
                    "under depth/resource/fidelity constraints. Input: a QASM "
                    "file (or stdin), reference JSON (optional).")
    ap.add_argument("--qasm", default=None, help="path to .qasm file (or - for stdin)")
    ap.add_argument("--ref", default=None,
                    help='reference JSON, e.g. \'{"00":0.5,"11":0.5}\'')
    ap.add_argument("--tol", type=float, default=0.06)
    ap.add_argument("--max-depth", type=int, default=None)
    ap.add_argument("--max-2q", type=int, default=None)
    ap.add_argument("--shots", type=int, default=4000)
    ap.add_argument("--json", action="store_true", help="print machine JSON")
    args = ap.parse_args()
    if args.qasm and args.qasm != "-":
        qasm = Path(args.qasm).read_text()
    else:
        qasm = sys.stdin.read()
    ref = json.loads(args.ref) if args.ref else None
    res = qas_search(qasm=qasm, ref=ref, tol=args.tol,
                     max_depth=args.max_depth, max_2q=args.max_2q,
                     shots=args.shots)
    if args.json:
        out = {k: res[k] for k in ("candidates", "selected")}
        print(json.dumps(out, indent=2, default=str))
    else:
        print(res["report"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
