#!/usr/bin/env python3
"""
qntelli_validate.py — quantum code validation & pass-rate harness.

Validates quantum algorithm code produced by the qntelli agent against
known-analytic references and tracks the one-time code-generation pass rate
(target >= 50% first-attempt correct).

Primitives supported across Qiskit, PennyLane, and Cirq:
  * statevector simulation (exact) for correctness checks
  * shot-based sampling for statistical verification
  * expectation-value checks

Usage:
  python3 qntelli_validate.py run <file.py> [--sdk qiskit|pennylane|cirq] [--task bell]
  python3 qntelli_validate.py bench [--out results.json]      # run the built-in benchmark suite
  python3 qntelli_validate.py report [--db results.json]      # show tracked pass rate
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

RESULTS_DB = Path(__file__).resolve().parent.parent / "benchmarks" / "harness_results.json"


# ────────────────────────── analytic references ──────────────────────────── #
def bell_expected():
    """|00> + |11> / sqrt(2) -> P(00)=0.5, P(11)=0.5."""
    return {"00": 0.5, "11": 0.5}


def ghz_expected(n):
    """|0...0> + |1...1> / sqrt(2)."""
    z0 = "0" * n
    z1 = "1" * n
    return {z0: 0.5, z1: 0.5}


def deutsch_jozsa_constant_expected(n, constant):
    """All 0 for constant, balanced gives 0 with prob 1."""
    return {"0" * n: 1.0}


def qft_uniform_amplitudes(n):
    """QFT of |0...0>: uniform |amplitude| = 1/sqrt(2^n), characteristic phase."""
    N = 2 ** n
    return N, 1.0 / math.sqrt(N)


def grover_amplitude_after_one_iter(M, N):
    """Amplitude amplification of M marked states among N after one Grover iteration."""
    theta = math.asin(math.sqrt(M / N))
    return math.sin(3 * theta)


# ────────────────────────── execution shims ──────────────────────────────── #
_BENCH_TASKS = {}


def _task(fn):
    _BENCH_TASKS[fn.__name__] = fn
    return fn


@_task
def bell_qiskit():
    return {
        "sdk": "qiskit",
        "code": """
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit.quantum_info import Statevector

qc = QuantumCircuit(2, 2)
qc.h(0)
qc.cx(0, 1)
qc.measure([0, 1], [0, 1])
sv = Statevector(qc.remove_final_measurements(inplace=False))
probs = sv.probabilities_dict()
import json
print(json.dumps({"probs": probs}))
""",
        "reference": bell_expected(),
        "tolerance": 0.05,
    }


@_task
def ghz3_qiskit():
    return {
        "sdk": "qiskit",
        "code": """
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
import json
qc = QuantumCircuit(3)
qc.h(0)
qc.cx(0, 1)
qc.cx(0, 2)
probs = Statevector(qc).probabilities_dict()
print(json.dumps({"probs": probs}))
""",
        "reference": ghz_expected(3),
        "tolerance": 0.05,
    }


@_task
def bell_pennylane():
    return {
        "sdk": "pennylane",
        "code": """
import pennylane as qml
import numpy as np
import json
dev = qml.device("default.qubit", wires=2, shots=4000)
@qml.qnode(dev)
def circuit():
    qml.Hadamard(0)
    qml.CNOT(wires=[0, 1])
    return qml.sample(qml.PauliZ(0)), qml.sample(qml.PauliZ(1))
samples = circuit()
# map (-1,1) -> bit, P(00),P(11)
bits = [("0" if a == 1 else "1") + ("0" if b == 1 else "1") for a, b in zip(samples[0], samples[1], strict=False)]
probs = {b: bits.count(b) / len(bits) for b in set(bits)}
print(json.dumps({"probs": probs}))
""",
        "reference": {"00": 0.5, "11": 0.5},
        "tolerance": 0.08,
    }


# ────────────────────────── reference checkers ───────────────────────────── #
def check_probs(actual, ref, tol):
    # actual: {bitstring: prob/amplitude-normalized}, ref: {bitstring: prob}
    if not actual:
        return False, {}, "no probability output"
    # normalize
    keys = set(actual) | set(ref)
    msgs = []
    for k in ref:
        a = actual.get(k, 0.0)
        if abs(a - ref[k]) > tol:
            msgs.append(f"{k}: expected {ref[k]:.4f}, got {a:.4f}")
    return (not msgs), {"actual": actual, "expected": ref}, "; ".join(msgs[:5]) or "ok"


def run_python_file(code: str, workdir: Path) -> tuple[int, str]:
    """Run a code snippet, capturing stdout. Returns (returncode, output)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=workdir) as f:
        f.write(code)
        path = f.name
    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(workdir) + os.pathsep + env.get("PYTHONPATH", "")
        r = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, cwd=workdir, env=env, timeout=120,
        )
        return r.returncode, (r.stdout + "\n" + r.stderr)
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    finally:
        os.unlink(path)


def extract_json_from_output(out: str):
    """Find the first balanced JSON object in program output and parse it."""
    start = out.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(out)):
            c = out[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = out[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
        start = out.find("{", start + 1)
    return None


def validate_code(code: str, reference: dict, tolerance: float, workdir: Path):
    """Run the code, extract probs, compare to analytic reference."""
    rc, out = run_python_file(code, workdir)
    if rc != 0:
        return {"pass": False, "stage": "exec", "detail": out[-2000:]}
    data = extract_json_from_output(out)
    if data is None or "probs" not in data:
        return {"pass": False, "stage": "parse", "detail": out[-2000:]}
    ok, detail, msg = check_probs(data["probs"], reference, tolerance)
    detail["stage"] = "check"
    detail["pass"] = ok
    detail["detail"] = msg
    return detail


# ────────────────────────── pass-rate tracking ───────────────────────────── #


@_task
def qft3_qiskit():
    # QFT(3) of |000> -> uniform amplitudes |a|=1/sqrt(8); check probs (not energy)
    return {
        "sdk": "qiskit",
        "code": """
import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
import json
def qft(n):
    qc = QuantumCircuit(n)
    for j in range(n):
        qc.h(j)
        for k in range(j + 1, n):
            qc.cp(np.pi / 2 ** (k - j), k, j)
    for j in range(n // 2):
        qc.swap(j, n - 1 - j)
    return qc
qc = qft(3)
amp = Statevector(qc).data
N = 8
probs = {format(i, "03b"): abs(amp[i])**2 for i in range(N)}
print(json.dumps({"probs": probs}))
""",
        "reference": {format(i,"03b"): 1.0/8.0 for i in range(8)},
        "tolerance": 1e-3,
    }


@_task
def deutsch_jozsa_single_qiskit():
    # Deutscher-Jozsa: 1 query qubit, balanced oracle flips phase -> P(|0>)=0
    return {
        "sdk": "qiskit",
        "code": """
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import json
qc = QuantumCircuit(2, 1)
# query |+>, ancilla |->
qc.h(0); qc.x(1); qc.h(1)
# balanced 1-bit oracle f(0)=0,f(1)=1: CNOT(query, ancilla); DJ then measures |1>.
qc.cx(0, 1)
qc.h(0)
qc.measure(0, 0)
counts = AerSimulator(seed_simulator=7).run(qc, shots=4000).result().get_counts()
probs = {k: v/4000 for k,v in counts.items()}
print(json.dumps({"probs": probs}))
""",
        "reference": {"1": 1.0},   # balanced 1-bit DJ -> measures |1> with P=1
        "tolerance": 0.05,
    }


def load_results():
    if RESULTS_DB.exists():
        return json.loads(RESULTS_DB.read_text())
    return {"runs": [], "summary": {"passes": 0, "total": 0, "rate": 0.0}}


def save_results(db):
    tot = db["summary"]["total"]
    passe = db["summary"]["passes"]
    db["summary"]["rate"] = (passe / tot) if tot else 0.0
    RESULTS_DB.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_DB.write_text(json.dumps(db, indent=2))
    return db


def record_result(task, verdict, detail):
    db = load_results()
    db["runs"].append({"task": task, "pass": verdict, "detail": detail})
    db["summary"]["total"] = len(db["runs"])
    db["summary"]["passes"] = sum(1 for r in db["runs"] if r["pass"])
    save_results(db)
    return db


def bench():
    db = load_results()
    workdir = Path(tempfile.mkdtemp(prefix="qntelli-bench-"))
    for name, task_fn in _BENCH_TASKS.items():
        print(f"[bench] running {name} ...")
        spec = task_fn()
        result = validate_code(spec["code"], spec["reference"], spec["tolerance"], workdir)
        verdict = result.get("pass", False)
        print(f"        -> {'PASS' if verdict else 'FAIL'}   {result.get('detail','')[:80]}")
        db = record_result(name, verdict, result)
    print(f"\nPASS RATE: {db['summary']['passes']}/{db['summary']['total']} "
          f"({db['summary']['rate']*100:.1f}%)")
    return db


def bench_with_db(db_path: Path):
    """Run the benchmark suite, writing results to a chosen database path."""
    global RESULTS_DB
    RESULTS_DB = db_path
    bench()


def main():
    global RESULTS_DB  # so `report --db <path>` (and `bench --out`) rebind the default
    ap = argparse.ArgumentParser(description="qntelli quantum code validation harness")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="validate a generated quantum code file")
    r.add_argument("file")
    r.add_argument("--sdk", default="qiskit")
    r.add_argument("--reference-json", default=None, help="analytic reference JSON")

    b = sub.add_parser("bench", help="run built-in benchmark suite")
    b.add_argument("--out", default=str(RESULTS_DB))

    f = sub.add_parser("report", help="show tracked pass rate")
    f.add_argument("--db", default=str(RESULTS_DB))

    args = ap.parse_args()

    if args.cmd == "bench":
        bench_with_db(Path(args.out))
    elif args.cmd == "run":
        code = Path(args.file).read_text()
        ref = json.loads(args.reference_json) if args.reference_json else bell_expected()
        workdir = Path(tempfile.mkdtemp(prefix="qntelli-run-"))
        res = validate_code(code, ref, 0.08, workdir)
        print(json.dumps(res, indent=2))
        print("PASS" if res.get("pass") else "FAIL")
    elif args.cmd == "report":
        # Honor --db so users can report on an arbitrary results file (e.g. the
        # one produced by `bench --out <path>`), not just the default DB.
        RESULTS_DB = Path(args.db)
        db = load_results()
        print(f"PASS RATE: {db['summary']['passes']}/{db['summary']['total']} "
              f"({db['summary']['rate']*100:.1f}%) target >= 50%")


if __name__ == "__main__":
    main()
