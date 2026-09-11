#!/usr/bin/env python3
"""Thin adapter (legacy entry point) -> harness report_gen (single renderer)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quantum"))
import report_gen as rg

def go():
    ART = json.load(open('/tmp/rich_artifacts.json'))
    g = ART["grover"]
    ctx = {"algorithm": "grover", "code": g["code"], "verify": g["verify"],
           "stage": g["stage"], "attempts": g["attempts"], "dist": g["dist"],
           "qas_table": g["qas_table"], "qas_selected": g["qas_selected"],
           "qas_report": g["qas_report"], "code_sdk": "qiskit"}
    out = rg.generate_report(ctx, os.path.join(HERE, "Case_Study_2_Grover.docx"),
                             title="Case Study 2 — Grover's Search with QAS 线路寻优")
    print("WROTE", out)

if __name__ == "__main__":
    go()
