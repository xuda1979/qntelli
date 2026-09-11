#!/usr/bin/env python3
"""
Tests for the QAS 智能体 (quantum.circuit search / 线路寻优).

Verifies the circuit-optimization harness ("search & evaluate candidate circuits
under precision/depth/resource constraints, select best") from the blueprint:
  * it generates distinct candidate circuits (baseline + transpile levels)
  * it evaluates depth, 2-qubit gate count, and simulated fidelity vs reference
  * it selects the best candidate that satisfies ALL hard constraints
  * it respects max_depth / max_2q filters

Run:  python3 quantum/tests/test_qas_agent.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qas_agent import qas_search

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def bell():
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(2, 2)
    qc.h(0); qc.cx(0, 1); qc.measure([0, 1], [0, 1])
    return qc


def qft3():
    import numpy as np
    from qiskit import QuantumCircuit, ClassicalRegister
    n = 3
    qc = QuantumCircuit(n)
    for j in range(n):
        qc.h(j)
        for k in range(j + 1, n):
            qc.cp(np.pi / 2 ** (k - j), k, j)
    for j in range(n // 2):
        qc.swap(j, n - 1 - j)
    qc.add_register(ClassicalRegister(n))
    qc.measure(range(n), range(n))
    return qc


def test_bell_selection():
    print("QAS-1 Bell: select correct Bell candidate under constraints")
    res = qas_search(circuit=bell(), ref={"00": 0.5, "11": 0.5}, tol=0.06,
                     max_depth=4, max_2q=2)
    check("has candidates", len(res["candidates"]) >= 1, str(len(res["candidates"])))
    check("some candidate satisfies", len(res["satisfying"]) >= 1,
          str(len(res["satisfying"])))
    check("selected exists", res["selected"] is not None, "")
    if res["selected"]:
        s = res["selected"]
        check("selected depth<=max_depth", s["depth"] <= 4, str(s["depth"]))
        check("selected 2q<=max_2q", s["n2q"] <= 2, str(s["n2q"]))
        check("selected high fidelity", s["fidelity"] > 0.9, str(s["fidelity"]))
    check("report is printable", isinstance(res["report"], str) and len(res["report"]) > 20, "")


def test_constraint_filter():
    print("QAS-2 constraint filter: tightening max_2q drops candidates / selects")
    res = qas_search(circuit=qft3(),
                     ref={f"{i:03b}": 0.125 for i in range(8)}, tol=0.30,
                     max_depth=20, max_2q=1)   # too tight for QFT (needs >=3 cx)
    check("tight 2q limit leaves no satisfying candidate",
          len(res["satisfying"]) == 0, str([c["n2q"] for c in res["candidates"]]))
    res2 = qas_search(circuit=qft3(),
                      ref={f"{i:03b}": 0.125 for i in range(8)}, tol=0.30,
                      max_depth=20, max_2q=10)
    check("relaxed constraint yields a satisfying candidate",
          len(res2["satisfying"]) >= 1, str([c["n2q"] for c in res2["satisfying"]]))


def test_qft_optimization_selects_lower_resources():
    print("QAS-3 QFT: optimization finds a lower-resource candidate and selects it")
    res = qas_search(circuit=qft3(),
                     ref={f"{i:03b}": 0.125 for i in range(8)}, tol=0.30,
                     max_depth=20, max_2q=10)
    check("multiple distinct candidates", len(res["candidates"]) >= 2,
          str([c["name"] for c in res["candidates"]]))
    if res["selected"]:
        # selected should be no worse on resources than baseline and still correct
        base = next((c for c in res["candidates"] if c["name"] == "baseline"), None)
        if base:
            check("selected uses <= baseline depth",
                  res["selected"]["depth"] <= base["depth"],
                  f"{res['selected']['name']} d={res['selected']['depth']} vs base {base['depth']}")
        check("selected fidelity within tol of target", res["selected"]["fidelity"] > (1 - 0.30),
              str(res["selected"]["fidelity"]))


def test_value_kind_qas():
    print("QAS-4 value-kind reference (QPE phase) finds + selects a valid candidate")
    import numpy as np
    from qiskit import QuantumCircuit

    def qpe():
        qc = QuantumCircuit(5, 4)
        qc.h(range(4)); qc.x(4)
        theta = 0.125
        for k in range(4):
            qc.cp(2 * np.pi * theta * (2 ** k), k, 4)
        for j in range(2):
            qc.swap(j, 3 - j)
        for i in range(4):
            for l in range(i):
                qc.cp(-np.pi / 2 ** (i - l), l, i)
            qc.h(i)
        qc.measure(range(4), range(4))
        return qc

    res = qas_search(circuit=qpe(), ref={"theta": 0.125}, tol=0.05,
                     ref_kind="value", value_key="phase",
                     max_depth=20, max_2q=20)
    check("value-kind has candidates", len(res["candidates"]) >= 1,
          str([c["name"] for c in res["candidates"]]))
    check("value-kind has a satisfying candidate", len(res["satisfying"]) >= 1,
          str([(c["name"], c["depth"], c["n2q"]) for c in res["satisfying"]]))
    if res["selected"]:
        s = res["selected"]
        check("value-kind selected is faithful", s["fidelity"] > 0.9, str(s["fidelity"]))
        check("value-kind selected depth<=baseline",
              s["depth"] <= res["candidates"][0]["depth"],
              f"{s['name']} d={s['depth']} vs base {res['candidates'][0]['depth']}")


def main():
    print("=== qntelli QAS 智能体 (circuit search) tests ===\n")
    test_bell_selection()
    test_constraint_filter()
    test_qft_optimization_selects_lower_resources()
    test_value_kind_qas()
    print(f"\n=== {PASS} passed, {FAIL} failed ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
