#!/usr/bin/env python3
"""
experience.py — 成果交付与经验沉淀 (experience/knowledge harvesting).

Implements the blueprint's "⑤ 成果交付与经验沉淀" (delivery & experience
harvesting): every one-enter solve outcome — success OR failure — is appended
to an append-only experience log (the "成功/失败样本" that enter the knowledge
base and training pool).

Why: a world-best agent harness should learn from its own outcomes. This module
gives qntelli a durable, queryable record of:
  * what question was asked (algorithm family + SDK),
  * whether it converged to a VERIFIED solution, attempts used,
  * which verification stage it reached,
  * a payload/code hash (so samples can later feed RAG / model fine-tuning).

Harvesting is failure-safe: it never raises into or slows down the solver. If
the log cannot be written the solve still succeeds; only a warning is emitted.

Usage:
  from experience import harvest
  harvest({...result...})          # record one outcome (safe, best-effort)
  python3 experience.py --report   # print pass-rate/experience stats
  python3 experience.py --tail 5   # show last N raw samples
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_EXP_DIR = Path(__file__).resolve().parent / "experience"
_EXP_LOG = _EXP_DIR / "samples.jsonl"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _user_question(q: str, maxlen: int = 300) -> str:
    q = (q or "").strip().replace("\n", " ")
    return q[:maxlen]


def _code_hash(code: str) -> str:
    return hashlib.sha256((code or "").encode()).hexdigest()[:16]


def _compact_attempts(attempt_log) -> list:
    if not attempt_log:
        return []
    out = []
    for a in attempt_log[-5:]:
        v = a.get("v") or {}
        out.append({"attempt": a.get("attempt"),
                    "pass": bool(a.get("pass")),
                    "stage": v.get("stage")})
    return out


def harvest(result: dict, *, sdk: str | None = None, quiet: bool = True) -> bool:
    """Best-effort append a solve result to the experience log. Never raises.
    Returns True if recorded, False if not (e.g. no payload / write failed)."""
    try:
        if not isinstance(result, dict) or not result.get("question"):
            return False
    except Exception:
        return False
    try:
        _EXP_DIR.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": _iso(),
            "question": _user_question(result.get("question")),
            "algorithm": result.get("algorithm"),
            "sdk": sdk or "qiskit",
            "ok": bool(result.get("ok")),
            "attempts": result.get("attempts"),
            "stage": (result.get("verification") or {}).get("stage")
                     if isinstance(result.get("verification"), dict) else None,
            "code_hash": _code_hash(result.get("code")),
            "attempt_trace": _compact_attempts(result.get("attempt_log")),
            "payload": result.get("payload"),
        }
        with open(_EXP_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        if not quiet:
            print("experience.harvest: could not record (ignored)", file=sys.stderr)
        return False


def load_samples(limit: int | None = None) -> list:
    """Read all recorded experience samples (newest-last)."""
    if not _EXP_LOG.exists():
        return []
    rows = []
    with open(_EXP_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[-limit:] if limit else rows


def stats(samples: list | None = None) -> dict:
    """Aggregate pass-rate by (algorithm, sdk) and overall."""
    samples = load_samples() if samples is None else samples
    from collections import defaultdict
    groups = defaultdict(lambda: {"pass": 0, "fail": 0})
    for s in samples:
        k = f"{s.get('algorithm','?')}/{s.get('sdk','?')}"
        groups[k]["pass" if s.get("ok") else "fail"] += 1
    total = {"pass": sum(g["pass"] for g in groups.values()),
             "fail": sum(g["fail"] for g in groups.values())}
    return {"total": total, "groups": dict(groups)}


def _print_report(samples) -> None:
    st = stats(samples)
    t = st["total"]
    n = t["pass"] + t["fail"]
    rate = 100.0 * t["pass"] / n if n else 0.0
    print(f"EXPERIENCE HARVEST REPORT: {n} sample(s) in knowledge base")
    print(f"  overall one-enter pass rate: {rate:.1f}% ({t['pass']}/{n})")
    print("  per (algorithm / sdk):")
    for k in sorted(st["groups"]):
        g = st["groups"][k]
        gn = g["pass"] + g["fail"]
        gr = 100.0 * g["pass"] / gn if gn else 0.0
        print(f"    {k:34s} {g['pass']:2d}/{gn:2d}  ({gr:5.1f}%)")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="experience/knowledge-harvest reporting")
    ap.add_argument("--report", action="store_true", help="print aggregated pass-rate report")
    ap.add_argument("--tail", type=int, default=0, help="print last N raw samples")
    args = ap.parse_args()
    samples = load_samples()
    if not samples:
        print("no experience samples yet (run a solve; every outcome is harvested).")
        return 0
    if args.report or not args.tail:
        _print_report(samples)
    if args.tail:
        for s in samples[-args.tail:]:
            print(json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
