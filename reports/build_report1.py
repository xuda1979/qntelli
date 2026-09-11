#!/usr/bin/env python3
"""Thin adapter (legacy entry point) -> harness report_gen (single renderer).
Builds the QPE run context from the cached run artifacts and lets the harness
library emit the top-quality case-study report. No rendering logic lives here."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quantum"))
import report_gen as rg

def status():
    ART = json.load(open('/tmp/rich_artifacts.json'))
    q = ART["qpe"]
    ctx = {"algorithm": "qpe", "code": q["code"], "verify": q["verify"],
           "stage": q["stage"], "attempts": q["attempts"], "dist": q["dist"],
           "qas_table": q["qas_table"], "qas_selected": q["qas_selected"],
           "qas_report": q["qas_report"], "code_sdk": "qiskit"}
    out = rg.generate_report(ctx, os.path.join(HERE, "Case_Study_1_QPE.docx"),
                             title="Case Study 1 — Quantum Phase Estimation (QPE)")
    print("WROTE", out)

if __name__ == "__main__":
    status()
