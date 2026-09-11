#!/usr/bin/env python3
"""
qntelli onetimepass.py — one-time-pass comparative benchmark for quantum code.

Measures the first-attempt correctness rate for FULL quantum algorithm code on
a fixed question bank, and compares two generation modes on the same questions:
  * mode=base    — a single raw call to the base model (no qntelli persona/skills)
  * mode=qntelli — a single call to the model augmented with the qntelli quantum
                   persona + domain instructions (algorithm/validate skills)

"One-time pass" = the FIRST generated program compiles AND produces an output
that matches the analytic reference (all parts correct). No iterative fixing.

Usage:
  python3 onetimepass.py --offline            # run golden solutions only (self-test)
  python3 onetimepass.py --mode base          # base model, one call per question
  python3 onetimepass.py --mode qntelli       # qntelli-augmented, one call per question
  python3 onetimepass.py --compare            # both modes, print comparison table
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BANK = HERE / "questions" / "bank.json"
RESULTS = HERE / "results.json"

# Whether an endpoint is configured for actual model calls.
BASE_URL = os.environ.get("QNTELLI_BASE_URL") or os.environ.get("HUANXIN_DP4_BASE_URL") or ""
API_KEY = os.environ.get("QNTELLI_API_KEY") or os.environ.get("HUANXIN_DP4_API_KEY") or ""


# ────────────────────────── golden (reference) solutions ───────────────────
# Each returns executable Python that, when run, prints a JSON {"probs": {...}}
# or {"value": x} that the checker compares to the question's reference.
GOLDEN = {
    "bmk.bell": """
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import json
qc = QuantumCircuit(2, 2)
qc.h(0); qc.cx(0, 1)
qc.measure([0, 1], [0, 1])
counts = AerSimulator(seed_simulator=7).run(qc, shots=4000).result().get_counts()
probs = {k: v/4000 for k, v in counts.items()}
print(json.dumps({"probs": probs}))
""",
    "bmk.ghz3": """
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import json
qc = QuantumCircuit(3, 3)
qc.h(0); qc.cx(0, 1); qc.cx(0, 2)
qc.measure([0,1,2],[0,1,2])
counts = AerSimulator(seed_simulator=7).run(qc, shots=4000).result().get_counts()
probs = {k: v/4000 for k, v in counts.items()}
print(json.dumps({"probs": probs}))
""",
    "bmk.qft3_uniform": """
import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
import json
def qft(n):
    qc = QuantumCircuit(n)
    for j in range(n):
        qc.h(j)
        for k in range(j+1, n):
            qc.cp(np.pi/2**(k-j), k, j)
    for j in range(n//2):
        qc.swap(j, n-1-j)
    return qc
amp = Statevector(qft(3)).data
probs = {format(i,'03b'): abs(amp[i])**2 for i in range(8)}
print(json.dumps({"probs": probs}))
""",
    "bmk.dj_balanced": """
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import json
n = 3
qc = QuantumCircuit(n+1, n)
qc.h(range(n)); qc.x(n); qc.h(n)
for i in range(n):
    qc.cx(i, n)          # balanced oracle: parity -> ancilla
qc.h(range(n))
qc.measure(range(n), range(n))
counts = AerSimulator(seed_simulator=7).run(qc, shots=4000).result().get_counts()
nonzero = any(k != '0'*n and c > 0 for k, c in counts.items())
print(json.dumps({"balanced_nonzero": bool(nonzero)}))
""",
    "bmk.grover1": """
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import json
n, marked = 3, 5
qc = QuantumCircuit(n, n)
qc.h(range(n))
zero = [i for i in range(n) if not ((marked>>i)&1)]
qc.x(zero); qc.h(n-1); qc.mcx(list(range(n-1)), n-1); qc.h(n-1); qc.x(zero)
qc.h(range(n)); qc.x(range(n)); qc.h(n-1); qc.mcx(list(range(n-1)), n-1); qc.h(n-1); qc.x(range(n)); qc.h(range(n))
qc.measure(range(n), range(n))
counts = AerSimulator(seed_simulator=7).run(qc, shots=4000).result().get_counts()
probs = {k: v/4000 for k, v in counts.items()}
print(json.dumps({"probs": probs}))
""",
    "bmk.grover_011": """
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import json, math
_N = 3
marked = int("011", 2)   # Grover |011>
qc = QuantumCircuit(_N, _N)
qc.h(range(_N))
def it(q):
    zero=[i for i in range(_N) if not ((marked>>i)&1)]
    q.x(zero); q.h(_N-1); q.mcx(list(range(_N-1)),_N-1); q.h(_N-1); q.x(zero)
    q.h(range(_N)); q.x(range(_N)); q.h(_N-1); q.mcx(list(range(_N-1)),_N-1); q.h(_N-1); q.x(range(_N)); q.h(range(_N))
it(qc)
qc.measure(range(_N), range(_N))
counts = AerSimulator(seed_simulator=7).run(qc, shots=4000).result().get_counts()
print(json.dumps({"probs": {k: v/4000 for k,v in counts.items()}}))
""",
    "bmk.qft4_uniform": """
import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
import json
_N = 4
def qft(n):
    qc = QuantumCircuit(n)
    for j in range(n):
        qc.h(j)
        for k in range(j+1, n):
            qc.cp(np.pi/2**(k-j), k, j)
    for j in range(n//2):
        qc.swap(j, n-1-j)
    return qc
amp = Statevector(qft(_N)).data
probs = {format(i, ('0%db' % _N)): abs(amp[i])**2 for i in range(2**_N)}
print(json.dumps({"probs": probs}))
""",
    "bmk.bell_pennylane": """import pennylane as qml
import json
dev = qml.device("default.qubit", wires=2, shots=4000)
@qml.qnode(dev)
def circuit():
    qml.Hadamard(0); qml.CNOT(wires=[0,1])
    return qml.sample(qml.PauliZ(0)), qml.sample(qml.PauliZ(1))
s0, s1 = circuit()
bits = [("0" if a==1 else "1")+("0" if b==1 else "1") for a,b in zip(s0.tolist(), s1.tolist())]
probs = {b: bits.count(b)/len(bits) for b in set(bits)}
print(json.dumps({"probs": probs}))
""",
    "bmk.ghz_cirq": """import cirq
import json
q = cirq.LineQubit.range(3)
c = cirq.Circuit([cirq.H(q[0]), cirq.CNOT(q[0],q[1]), cirq.CNOT(q[0],q[2]), cirq.measure(*q, key='m')])
counts = cirq.Simulator().run(c, repetitions=4000).histogram(key='m')
probs={format(k,'03b'): v/4000 for k,v in counts.items()}
print(json.dumps({"probs": probs}))
""",
    "bmk.bell_cirq": """import cirq
import json
q = cirq.LineQubit.range(2)
c = cirq.Circuit([cirq.H(q[0]), cirq.CNOT(q[0],q[1]), cirq.measure(*q, key='m')])
counts = cirq.Simulator().run(c, repetitions=4000).histogram(key='m')
probs={format(k,'02b'): v/4000 for k,v in counts.items()}
print(json.dumps({"probs": probs}))
""",
    "bmk.ghz_pennylane": """import pennylane as qml
import json
dev = qml.device("default.qubit", wires=3, shots=4000)
@qml.qnode(dev)
def circuit():
    qml.Hadamard(0); qml.CNOT(wires=[0,1]); qml.CNOT(wires=[0,2])
    return qml.sample(qml.PauliZ(0)), qml.sample(qml.PauliZ(1)), qml.sample(qml.PauliZ(2))
s0, s1, s2 = circuit()
bits = [("0" if a==1 else "1")+("0" if b==1 else "1")+("0" if c==1 else "1")
        for a,b,c in zip(s0.tolist(), s1.tolist(), s2.tolist())]
probs={b: bits.count(b)/len(bits) for b in set(bits)}
print(json.dumps({"probs": probs}))
""",
    "bmk.expectation_z": """
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp
import json
from qiskit_aer.primitives import EstimatorV2
qc = QuantumCircuit(1); qc.h(0)
op = SparsePauliOp(["Z"])
evs = EstimatorV2().run([(qc, [op])]).result()[0].data.evs
print(json.dumps({"value": float(evs[0].real)}))
""",
    "bmk.bernstein_vazirani": """
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import json
secret = "101"
n = len(secret)
qc = QuantumCircuit(n+1, n)
qc.h(range(n)); qc.x(n); qc.h(n)
for i, b in enumerate(secret):
    if b == "1":
        qc.cx(i, n)
qc.h(range(n))
qc.measure(range(n), range(n))
counts = AerSimulator(seed_simulator=7).run(qc, shots=4000).result().get_counts()
probs = {k: v/4000 for k, v in counts.items()}
print(json.dumps({"probs": probs}))
""",
    "bmk.swap_test": """
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import json
equal = True
qc = QuantumCircuit(3, 1)
qc.h(0); qc.h(1); qc.h(2)
qc.cswap(0, 1, 2); qc.h(0)
qc.measure(0, 0)
counts = AerSimulator(seed_simulator=7).run(qc, shots=4000).result().get_counts()
print(json.dumps({"prob1": counts.get("1", 0)/4000}))
""",
    "bmk.qpe": """
import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import json
theta = 0.125
t = 4
qc = QuantumCircuit(t+1, t)
qc.h(range(t)); qc.x(t)
for k in range(t):
    qc.cp(2*np.pi*theta*(2**k), k, t)
for j in range(t//2):
    qc.swap(j, t-1-j)
for i in range(t):
    for l in range(i):
        qc.cp(-np.pi/2**(i-l), l, i)
    qc.h(i)
qc.measure(range(t), range(t))
counts = AerSimulator(seed_simulator=7).run(qc, shots=4000).result().get_counts()
est = int(max(counts, key=lambda k: counts[k]), 2)/(2**t)
print(json.dumps({"phase": est}))
""",
    "bmk.vqe": """
from qiskit.quantum_info import SparsePauliOp
from qiskit_algorithms import NumPyMinimumEigensolver
import json
H = SparsePauliOp(["X"])
res = NumPyMinimumEigensolver().compute_minimum_eigenvalue(H)
print(json.dumps({"energy": float(res.eigenvalue.real)}))
""",
}


# ────────────────────────── checkers ────────────────────────────────────────
def extract_first_json(out: str):
    start = out.find("{")
    while start != -1:
        depth = 0; in_str = False; esc = False
        for i in range(start, len(out)):
            c = out[i]
            if in_str:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == '"': in_str = False
                continue
            if c == '"': in_str = True
            elif c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try: return json.loads(out[start:i+1])
                    except Exception: break
        start = out.find("{", start+1)
    return None


def check_result(data, q):
    ref = q.get("reference")
    cond = q.get("reference_condition")
    tol = q.get("tolerance")
    if cond == "balanced_measure_nonzero":
        v = data.get("balanced_nonzero")
        if v is None:
            # fallback: from probs/counts, any non-000 with mass
            probs = data.get("probs", {})
            v = any(k != "000" and p > 0.01 for k, p in probs.items())
        return bool(v), {"observed": v, "expected": True}
    if cond == "expectation_abs_lt_0.1":
        v = abs(data.get("value", 1.0))
        return v < 0.1, {"observed": data.get("value"), "expected": "|v|<0.1"}
    if cond == "bv_secret":
        # Bernstein-Vazirani: top measured bitstring == hidden secret.
        probs = data.get("probs", {})
        if not probs:
            return False, {"error": "no probs"}
        top = max(probs, key=lambda k: probs[k])
        secret = (ref or {}).get("secret", "101")
        ok = probs[top] > 0.3 and top == secret
        return ok, {"observed": f"top={top} p={probs[top]:.3f}", "expected": secret}
    if cond == "swap_equal":
        # Swap test on two EQUAL states: P(ancilla=1) -> ~0.
        p1 = data.get("prob1", data.get("probs", {}).get("1", None))
        if p1 is None:
            return False, {"error": "missing prob1"}
        tol = q.get("tolerance", 0.06)
        return p1 < tol, {"observed": p1, "expected": "P1<%.2f" % tol}
    if cond == "qpe_theta":
        # QPE: estimated phase in [0,1) matches target theta within tolerance.
        est = data.get("phase")
        if est is None:
            return False, {"error": "missing phase"}
        theta = (ref or {}).get("theta", 0.125)
        tol = q.get("tolerance", 0.05)
        err = abs((est - theta + 0.5) % 1.0 - 0.5)
        return err < tol, {"observed": est, "expected": theta, "err": round(err, 4)}
    if cond == "vqe_energy":
        # VQE: converged energy must be close to the exact ground-state energy.
        e = data.get("energy")
        if e is None:
            return False, {"error": "missing energy"}
        target = (ref or {}).get("energy", -1.0)
        tol = q.get("tolerance", 0.25)
        err = abs(e - target)
        return err < tol, {"observed": e, "expected": target, "err": round(err, 4)}
    if cond == "grover_top_marked":
        # Grover: the requested marked state must be the TOP measured outcome
        # and clearly amplified (peak > 0.5). Supports any marked bitstring.
        probs = data.get("probs", {})
        if not probs:
            return False, {"error": "no probs"}
        marked = (ref or {}).get("marked", "101")
        top = max(probs, key=lambda k: probs[k])
        ok = probs[top] > 0.5 and top == marked
        return ok, {"observed": f"top={top} p={probs[top]:.3f}", "expected": marked}
    # default prob comparison
    probs = data.get("probs", {})
    if not probs:
        return False, {"error": "no probs"}
    msgs = []
    ok = True
    for k, e in (ref or {}).items():
        a = probs.get(k, 0.0)
        if abs(a - e) > tol:
            ok = False; msgs.append(f"{k}: exp {e:.4f} got {a:.4f}")
    return ok, {"actual": probs, "expected": ref, "detail": "; ".join(msgs[:4]) or "ok"}


def run_code(code, workdir):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=workdir) as f:
        f.write(code); path = f.name
    try:
        r = subprocess.run([sys.executable, path], capture_output=True, text=True,
                           cwd=workdir, env=dict(os.environ), timeout=120)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    finally:
        try: os.unlink(path)
        except Exception: pass


def evaluate_solution(code, q):
    """One evaluation: compile+run+check. Returns (pass_bool, detail)."""
    workdir = Path(tempfile.mkdtemp(prefix="qntelli-otp-"))
    rc, out = run_code(code, workdir)
    if rc != 0:
        return False, {"stage": "compile/run", "detail": out[-1500:]}
    data = extract_first_json(out)
    if data is None:
        return False, {"stage": "parse", "detail": out[-1500:]}
    ok, detail = check_result(data, q)
    detail["stage"] = "result"
    return ok, detail


# ────────────────────────── model calls ─────────────────────────────────────
QNTELLI_PERSONA = (
    "You are qntelli, an intelligent agent for quantum-computing science and "
    "technology. Write COMPLETE, CORRECT, RUNNABLE quantum algorithm code in "
    "Qiskit. Output ONLY the python code inside a single code block. It must "
    "compile and, when run, print a JSON object with key 'probs' (dict of "
    "bitstring->probability) or 'value' (float). First-attempt correctness is "
    "essential. Use canonical building blocks (H, CX, CP, MCX, transpile). "
    "For circuits, finish by measuring and sampling via AerSimulator."
)


def call_model(prompt, mode):
    """Single one-shot model call via the OpenAI-compatible endpoint (huanxin).
    Returns generated code text, or None on failure."""
    if not BASE_URL or not API_KEY:
        return None
    system = QNTELLI_PERSONA if mode == "qntelli" else "You are a helpful assistant that writes Python code."
    model = os.environ.get("QNTELLI_MODEL") or os.environ.get("HUANXIN_DP4_UPSTREAM_MODEL") or "deepseek_v4"
    body = {
        "model": model,
        "max_tokens": 3000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    url = BASE_URL.rstrip("/")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}",
               "x-api-key": API_KEY}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            out = json.loads(resp.read().decode())
    except Exception:
        return None
    try:
        text = out["choices"][0]["message"]["content"]
    except Exception:
        return None
    return extract_code(text)


def extract_code(text):
    if "```" in text:
        parts = text.split("```")
        # prefer a fenced block not starting with 'json'
        for i in range(1, len(parts), 2):
            seg = parts[i].lstrip()
            first = seg.splitlines()[0] if seg else ""
            body = seg[len(first):] if first.lower() in ("python", "py", "qiskit") else seg
            if first.lower() not in ("python", "py", "qiskit", "json"):
                body = seg
            return body.strip()
    return text.strip()


# ────────────────────────── driver ──────────────────────────────────────────
def load_bank():
    return json.loads(BANK.read_text())["questions"]


def run_mode(mode, questions, offline=False):
    results = []
    for q in questions:
        qid = q["id"]
        if offline:
            code = GOLDEN[qid]
        else:
            code = call_model(q["prompt"], mode)
            if code is None:
                results.append({"id": qid, "pass": None, "mode": mode, "error": "no-endpoint"})
                continue
        ok, detail = evaluate_solution(code, q)
        results.append({"id": qid, "pass": ok, "mode": mode, "detail": detail})
    return results


def summarize(results):
    evals = [r for r in results if r.get("pass") is not None]
    passes = sum(1 for r in evals if r["pass"])
    total = len(evals)
    rate = passes / total if total else 0.0
    return {"passes": passes, "total": total, "rate": rate}


def print_report(tag, results):
    s = summarize(results)
    print(f"\n=== {tag} ===")
    for r in results:
        note = "PASS" if r.get("pass") else ("SKIP" if r.get("pass") is None else "FAIL")
        d = r.get("detail")
        brief = ""
        if isinstance(d, dict):
            brief = d.get("detail", d.get("stage", ""))
        print(f"  [{note}] {r['id']}  {brief}")
    print(f"ONE-TIME PASS RATE: {s['passes']}/{s['total']} = {s['rate']*100:.1f}%  (target >= 50%)")
    return s


def main():
    ap = argparse.ArgumentParser(description="qntelli one-time-pass comparative benchmark")
    ap.add_argument("--offline", action="store_true", help="evaluate built-in golden solutions (self-test of harness)")
    ap.add_argument("--mode", choices=["base", "qntelli"], default=None)
    ap.add_argument("--compare", action="store_true", help="run both modes and print comparison")
    ap.add_argument("--out", default=str(RESULTS))
    args = ap.parse_args()

    questions = load_bank()
    if args.offline:
        res = run_mode("golden", questions, offline=True)
        print_report("GOLDEN SELF-TEST", res)
        Path(args.out).write_text(json.dumps(res, indent=2))
        return

    if not BASE_URL or not API_KEY:
        print("No model endpoint configured. Set QNTELLI_BASE_URL and QNTELLI_API_KEY "
              "(or HUANXIN_DP4_* defaults) to run model comparison. Running offline self-test instead.")
        res = run_mode("golden", questions, offline=True)
        print_report("GOLDEN SELF-TEST", res)
        Path(args.out).write_text(json.dumps(res, indent=2))
        return

    if args.mode:
        res = run_mode(args.mode, questions)
        print_report(f"mode={args.mode}", res)
        Path(args.out).write_text(json.dumps(res, indent=2))
    elif args.compare:
        r_base = run_mode("base", questions)
        s_base = print_report("BASE MODEL (one call)", r_base)
        r_q = run_mode("qntelli", questions)
        s_q = print_report("QNTELLI (persona + skills)", r_q)
        print("\n=== COMPARISON ===")
        print(f"  base   : {s_base['passes']}/{s_base['total']} = {s_base['rate']*100:.1f}%")
        print(f"  qntelli: {s_q['passes']}/{s_q['total']} = {s_q['rate']*100:.1f}%  (target >= 50%)")
        print(f"  qntelli > base: {'YES' if s_q['rate'] > s_base['rate'] else 'NO'}")
        Path(args.out).write_text(json.dumps({"base": r_base, "qntelli": r_q}, indent=2))


if __name__ == "__main__":
    main()
