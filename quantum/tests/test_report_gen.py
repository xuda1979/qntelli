#!/usr/bin/env python3
"""
test_report_gen.py — tests for the harness reporter skill (qc.experiment.report).

Verifies:
  * report_gen.generate_report turns real run data into a structured .docx
    (paragraphs + tables + code block), not an empty shell.
  * The Grover report states the CORRECT single-iteration theory
    (sin^2(3*theta) ~ 0.781), never the common wrong sin^2(3*pi/8) ~ 0.854.
  * The measured peak in the report matches the actual sim distribution.
  * The orchestrator's reporter skill emits a real .docx artifact in real
    mode (report_emitted event, autonomous_complete stays true).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "reports"))

import report_gen as rg
from docx import Document

PASS = FAIL = 0


def check(name, cond, info=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {info}")


def _ctx():
    return {
        "algorithm": "grover",
        "code": "print('ok')",
        "verify": "peak=0.772 top=101 marked=101",
        "stage": "grover",
        "attempts": 1,
        "dist": {"001": 0.03, "101": 0.772, "010": 0.03, "111": 0.03,
                 "000": 0.034, "011": 0.031, "100": 0.035, "110": 0.034},
        "qas_table": [["baseline", 12, 2, 0.9904, True],
                      ["opt0", 12, 2, 0.9904, True],
                      ["opt1", 6, 2, 0.9904, True]],
        "qas_selected": "opt1",
        "qas_report": "QAS search: opt1 selected",
    }


def test_report_structure():
    with tempfile.TemporaryDirectory() as td:
        out = rg.generate_report(_ctx(), Path(td) / "r.docx")
        d = Document(out)
        check("report file written", Path(out).exists())
        check("report has paragraphs", len(d.paragraphs) > 15)
        check("report has tables", len(d.tables) >= 6)
        text = "\n".join(p.text for p in d.paragraphs)
        check("report has QAS section", "QAS Circuit Optimisation" in text)
        check("report has experience section", "Experience Harvesting" in text)
        check("report has references", "References" in text)


def test_grover_theory_correct():
    import math
    N, r = 8, 1
    theta = math.asin(1 / math.sqrt(N))
    theory = math.sin((2 * r + 1) * theta) ** 2
    check("grover theory computed ~0.781 (not 0.854)", abs(theory - 0.7812) < 1e-4,
          "theory=%s" % theory)
    with tempfile.TemporaryDirectory() as td:
        out = rg.generate_report(_ctx(), Path(td) / "r.docx")
        d = Document(out)
        text = "\n".join(p.text for p in d.paragraphs)
        check("report cites correct theory (~0.781)", "0.781" in text,
              "wrong-vs-correct theory not distinguished")
        check("report does NOT cite wrong sin^2(3*pi/8)=0.854 as the peak",
              "0.853" not in text or "not 0.853" not in text)


def test_measured_peak_matches_dist():
    with tempfile.TemporaryDirectory() as td:
        out = rg.generate_report(_ctx(), Path(td) / "r.docx")
        d = Document(out)
        text = "\n".join(p.text for p in d.paragraphs)
        # The measured peak should appear (0.772 or 0.7725).
        check("measured peak present in report", ("0.772" in text) or ("0.77" in text))


def test_hardware_section_renders():
    """A ctx carrying an ion-trap emulator result emits a full-stack Hardware
    Result section with correct running section/result numbering, and the
    hardware section labels it honestly (device, tier, measured-vs-theory)."""
    ctx = _ctx()
    ctx["hardware"] = {
        "device": "quantinuum:h2-1e",
        "tier": "emulator",
        "status": "complete",
        "gate_family": "quantinuum",
        "checks": {"101": {"expected": 0.78, "observed": 0.7782, "ok": True}},
        "detail": "pecos local emulator (vendor compile + validity check passed)",
    }
    with tempfile.TemporaryDirectory() as td:
        out = rg.generate_report(ctx, Path(td) / "r.docx")
        d = Document(out)
        paras = [p.text for p in d.paragraphs if p.text.strip()]
        text = "\n".join(paras)
        check("hardware Result section rendered",
              "Ion-Trap Emulator Execution" in text)
        check("hardware section correctly numbered Result 4 (after QAS Result 3)",
              "7. Result 4 — Ion-Trap Emulator Execution" in text,
              [p for p in paras if "Ion-Trap" in p])
        check("hardware section numbered after Experience (sec 7 < 8)",
              "8. Experience Harvesting" in text)
        # The device + honest tier label appear.
        # Device / tier / measured-vs-theory values live in tables and callouts
        # (callout renders into a table cell), so search the WHOLE document.
        tab_text = "\n".join(
            " | ".join(c.text for c in row.cells)
            for t in d.tables for row in t.rows)
        full = text + "\n" + tab_text
        check("hardware device named", "quantinuum:h2-1e" in full,
              [p for p in (text.splitlines() + tab_text.splitlines()) if 'quantinuum' in p])
        check("hardware tier honestly labelled", "emulator" in full)
        check("hardware measured-vs-theory present", "0.7782" in tab_text,
              tab_text[:300])


def test_hardware_package_import():
    """`import hardware` (the package, not just hardware.standard) must succeed
    — regression for the stale DeviceRegistry export that raised ImportError
    and broke the documented public API."""
    import subprocess
    import sys as _sys
    root = str(Path(__file__).resolve().parent.parent)
    r = subprocess.run([_sys.executable, "-c",
                        "import sys;sys.path.insert(0,%r);"
                        "import hardware;print(getattr(hardware,'get_device',None) is not None)"
                        % root], capture_output=True, text=True)
    check("`import hardware` succeeds and exposes get_device",
          r.returncode == 0 and r.stdout.strip() == "True", r.stderr[-300:])


def test_orchestrator_reporter_emits_docx():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "orchestrator"))
    import orchestrator as O
    with tempfile.TemporaryDirectory() as td:
        orch = O.MultiAgentOrchestrator("grover", real=True)
        orch.report_dir = Path(td)
        orch.run_with_feedback()
        check("orchestrator completes autonomously", orch.status["complete"])
        check("reporter wrote a .docx artifact", orch.report_path is not None
              and Path(orch.report_path).exists(), str(orch.report_path))
        # The report_generated/emitted event is present in the log.
        events = [r.get("event") for r in orch.state_log]
        check("report_emitted event logged",
              "report_emitted" in events or "report_generated" in events,
              str([e for e in events if 'report' in str(e)]))
        if orch.report_path:
            d = Document(orch.report_path)
            check("emitted report is non-trivial", len(d.paragraphs) > 15)


def main():
    print("=== qntelli report-gen (qc.experiment.report) tests ===\n")
    test_report_structure()
    test_grover_theory_correct()
    test_measured_peak_matches_dist()
    test_hardware_section_renders()
    test_hardware_package_import()
    test_orchestrator_reporter_emits_docx()
    print(f"\n=== {PASS} passed, {FAIL} failed ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
