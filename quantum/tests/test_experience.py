#!/usr/bin/env python3
"""
Tests for the experience / knowledge-harvesting module (⑤ 沉淀).

Verifies:
  * every solve outcome (success AND failure) is harvested into the knowledge log
  * the harvested record captures question/algorithm/sdk/ok/attempts/stage
  * stats/pass-rate aggregation works and is honest (failures counted)

Run:  python3 quantum/tests/test_experience.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import experience as E

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


def test_harvest_success_and_failure():
    print("EXP-1 harvest success + failure samples")
    # Isolate to a temp knowledge log so tests don't touch the real one.
    tmpdir = Path(tempfile.mkdtemp(prefix="qntelli-exp-"))
    orig_log = E._EXP_LOG
    E._EXP_LOG = tmpdir / "samples.jsonl"
    try:
        ok = E.harvest({"question": "write a Bell state circuit",
                        "algorithm": "bell", "ok": True, "attempts": 1,
                        "verification": {"stage": "probs"},
                        "attempt_log": [{"attempt": 1, "pass": True, "v": {"stage": "probs"}}],
                        "code": "print('hi')"}, sdk="qiskit")
        check("success sample recorded", ok, "")
        fail = E.harvest({"question": "some impossible circuit",
                          "algorithm": "unknown", "ok": False, "attempts": 4,
                          "verification": None, "attempt_log": [], "code": None},
                         sdk="cirq")
        check("failure sample recorded", fail, "")
        samples = E.load_samples()
        check("two samples in log", len(samples) == 2, str(len(samples)))
        # failure sample retained (blueprint: success AND failure samples)
        fails = [s for s in samples if not s.get("ok")]
        check("failure sample present", len(fails) == 1, str(len(fails)))
        # fields captured
        s = samples[0]
        check("captures algorithm+sdk+stage", s.get("algorithm") == "bell" and
              s.get("sdk") == "qiskit" and s.get("stage") == "probs",
              f"{s.get('algorithm')}/{s.get('sdk')}/{s.get('stage')}")
        check("captures code hash", s.get("code_hash") and len(s["code_hash"]) >= 8, s.get("code_hash"))
        # stats : 1 pass + 1 fail -> overall 50%
        st = E.stats(samples)
        t = st["total"]
        check("stats overall 1 pass 1 fail", t["pass"] == 1 and t["fail"] == 1,
              f"{t}")
    finally:
        E._EXP_LOG = orig_log
    check("restored real log path", str(E._EXP_LOG) != str(tmpdir), "")


def test_harvest_is_failure_safe():
    print("EXP-2 harvest never raises / writes lazily")
    orig_log = E._EXP_LOG
    E._EXP_LOG = Path("/nonexistent_dir_xyz/sub/samples.jsonl")
    try:
        r = E.harvest({"question": "q", "algorithm": "bell", "ok": True,
                       "attempts": 1, "verification": None})
        check("harvest returns False when it cannot write (no exception)", r is False, str(r))
    finally:
        E._EXP_LOG = orig_log


def main():
    print("=== qntelli experience/knowledge-harvest tests ===\n")
    test_harvest_success_and_failure()
    test_harvest_is_failure_safe()
    print(f"\n=== {PASS} passed, {FAIL} failed ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
