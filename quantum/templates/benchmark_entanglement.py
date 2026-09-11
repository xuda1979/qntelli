#!/usr/bin/env python3
"""
Example end-to-end quantum experiment (entanglement fidelity benchmark)
designed with the qntelli experiment-workflow template.

Pipeline: design -> transpile -> simulate -> measure -> analyse -> package.

Run:  python3 quantum/templates/benchmark_entanglement.py
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

# Stage 1+2: circuit design (Bell / GHZ building blocks)
def build_bell_circuit(qiskit: __import__("qiskit")):  # noqa: F821
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc


def simulate_circuit(qc, shots: int, seed: int):
    from qiskit_aer import AerSimulator
    sim = AerSimulator(seed_simulator=seed)
    job = sim.run(qc, shots=shots)
    return job.result().get_counts(qc)


def compute_fidelity(counts, shots: int) -> float:
    """Fraction of samples in the ideal Bell basis states (00 or 11)."""
    ideal = sum(counts.get(k, 0) for k in ("00", "11"))
    return ideal / shots


def run_experiment(shots: int, seed: int) -> dict:
    qc = build_bell_circuit(None)
    counts = simulate_circuit(qc, shots, seed)
    fidelity = compute_fidelity(counts, shots)
    return {
        "experiment_id": "entanglement-bell",
        "backend": "aer_simulator",
        "shots": shots,
        "seed": seed,
        "counts": counts,
        "fidelity": fidelity,
        "verdict": "PASS" if fidelity > 0.9 else "FAIL",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    random.seed(args.seed)
    result = run_experiment(args.shots, args.seed)
    print(json.dumps(result, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2))
        print(f"[save] wrote {args.out}")


if __name__ == "__main__":
    main()
