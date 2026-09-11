#!/usr/bin/env python3
"""
LIVE one-enter harness guarantee tests (require a configured endpoint).

Skips cleanly (exit 0, reported SKIP) when no QNTELLI/HUANXIN base URL+key is
available in the environment峦. Confirms the guarantee holds against a real model.

Run:  python3 quantum/tests/test_solve_live.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import solve as S

# NOTE: moving the module-level early-exit into main() so this file is
# import-safe (pytest collects it). When run via `python3 test_solve_live.py`
# it still skips cleanly (exit 0) with no endpoint configured.
CASES = [
    ("Bell", "Write a Qiskit Bell state circuit, P(00)=P(11)=0.5 on a simulator (4000 shots)."),
    ("4-qubit GHZ", "Build a 4-qubit GHZ state in Qiskit; only |0000> and |1111> equally likely."),
    ("2-qubit Deutsch-Jozsa", "Implement balanced Deutsch-Jozsa on 2 qubits in Qiskit; result must be non-zero."),
    ("Grover |101>", "Implement Grover's algorithm in Qiskit marking |101>, one iteration; top result is 101 with elevated probability."),
    # Sprint-17 extended live coverage: multi-SDK + new n-aware/marked/secret
    # capabilities through the REAL model (validates the offline fixes also hold
    # when genuine LLM-generated code must be verified).
    ("4q GHZ PennyLane", "Write a 4-qubit GHZ in PennyLane; P(0000)=P(1111)=0.5."),
    ("QFT 4q", "Write a 4-qubit Quantum Fourier Transform in Qiskit from |0>; uniform probabilities."),
    ("Grover |011>", "Implement Grover marking |011> in Qiskit; top result is 011."),
    ("BV secret 110", "Implement Bernstein-Vazirani with secret 110 in Qiskit; top measured = 110."),
    ("Grover 4q |1011>", "Grover on 4 qubits marking |1011>; top result 1011."),
]

def main() -> int:
    if not S.BASE_URL or not S.API_KEY:
        print("SKIP: no endpoint configured (set QNTELLI_BASE_URL + QNTELLI_API_KEY)")
        return 0
    fails = 0
    print(f"=== LIVE one-enter tests (model={S.MODEL}) ===")
    for name, q in CASES:
        r = S.solve(q, max_attempts=10)
        ok = r["ok"]
        v = (r.get("verification") or {}).get("detail", "")
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:22s} attempts={r.get('attempts')} verify={v}")
        if not ok:
            fails += 1
    print(f"=== {'ALL PASS' if not fails else f'{fails} FAILED'} ===")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
