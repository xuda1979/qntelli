#!/usr/bin/env python3
"""Thin adapter (legacy entry point) -> harness report_gen (single renderer)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quantum"))
import report_gen as rg

def go():
    ART = json.load(open('/tmp/rich_artifacts.json'))
    b = ART["bv_pl"]
    ctx = {"algorithm": "bv_pl", "code": b["code"], "verify": b["verify"],
           "stage": b["stage"], "attempts": b["attempts"], "dist": b["dist"],
           "code_sdk": b.get("code_sdk", "pennylane")}
    out = rg.generate_report(ctx, os.path.join(HERE, "Case_Study_3_BernsteinVazirani_PennyLane.docx"),
                             title="Case Study 3 — Bernstein-Vazirani in PennyLane (Multi-SDK)")
    print("WROTE", out)

if __name__ == "__main__":
    go()
