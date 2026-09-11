#!/usr/bin/env python3
"""
qntelli metrics.py — objective-metric tracker for the qntelli quantum harness.

Computes the five objective metrics declared in quantum/skills/registry.json
from real, replayable run logs produced by orchestrator.py:

  * reusable_core_skills          : count of distinct verifiable core skills used
  * workflow_skill_coverage       : distinct skills used across runs / total skills
  * autonomous_completion         : fraction of task-chain steps that completed
                                    autonomously (no manual intervention / failed retry)
  * manual_step_reduction         : reduction factor vs a fully-manual baseline
                                    (manual steps required when skills do NOT fire)
  * experiment_types_end_to_end   : distinct experiments with a log that reached
                                    a `report_generated` event (completed end-to-end)

Data sources (in priority order):
  * explicit --logs glob(s) of orchestrator state_log.jsonl files
  * if none given, the repo's exemplar logs: ../../state_log.jsonl.* and
    ./state_log.jsonl.*

Exits 0 with a JSON objective-metrics report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGISTRY = HERE.parent / "skills" / "registry.json"

TOTAL_SKILLS = 9
# A fully-manual baseline for the same experiment types: each experiment would
# require one manual step per stage with no reusable skill. Used as the
# denominator for manual_step_reduction.
MANUAL_STEPS_PER_EXP = 8  # metadata, design, transpile, exec, measure, analyse, package, review
TERMINAL_EVENT = "report_generated"
FAIL_EVENTS = {"anomaly_retry", "task_retry_end"}


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {}


def parse_log(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def experiment_name(path: Path) -> str:
    # state_log.jsonl.<exp> or state_log.jsonl
    stem = path.name
    parts = stem.split(".")
    if len(parts) >= 3 and parts[0] == "state_log":
        return parts[1]
    if path.parent.name and path.parent.name != "orchestrator":
        return path.parent.name
    return "unnamed"


def summarize_log(rows: list[dict], name: str) -> dict:
    used = {r.get("skill") for r in rows if r.get("skill")}
    used.discard(None)
    completed = any(r.get("event") == TERMINAL_EVENT for r in rows)
    failed = any(r.get("event") in FAIL_EVENTS for r in rows)
    total_steps = len(rows)
    auto_steps = sum(1 for r in rows if r.get("event") != "anomaly_retry")
    return {
        "experiment": name,
        "steps": total_steps,
        "skills_used": sorted(used),
        "skills_used_count": len(used),
        "completed_end_to_end": completed,
        "had_failure_retry": failed,
        "autonomous_steps": auto_steps,
    }


def collect_logs(globs: list[str], cwd: Path) -> list[tuple[Path, str]]:
    candidates: set[Path] = set()
    if globs:
        for g in globs:
            p = Path(g)
            if not p.is_absolute():
                p = cwd / p
            if p.exists():
                candidates.add(p)
            else:
                for m in list(p.parent.glob(p.name)) if p.parent.exists() else []:
                    candidates.add(m)
    else:
        # exemplars shipped with the repo
        for base in (cwd.parent, cwd):
            for gp in base.glob("state_log.jsonl*"):
                if gp.is_file():
                    candidates.add(gp)
        for gp in cwd.glob("*.jsonl"):
            if gp.is_file():
                candidates.add(gp)
    return [(p, experiment_name(p)) for p in sorted(candidates)]


def compute(globs: list[str], cwd: Path) -> dict:
    logs = collect_logs(globs, cwd)
    if not logs:
        return {
            "error": "no state logs found",
            "hint": "run orchestrator.py first, or pass --logs state_log.jsonl.<exp>",
            "metrics": {},
        }

    per = [summarize_log(parse_log(p), name) for p, name in logs]
    all_skills: set[str] = set()
    for s in per:
        all_skills |= set(s["skills_used"])

    completed_exps = [s for s in per if s["completed_end_to_end"]]
    total_steps = sum(s["steps"] for s in per)
    auto_steps = sum(s["autonomous_steps"] for s in per)
    # a step is "manual" if it required a failure-retry intervention (i.e. the
    # agent could not self-complete it on the first attempt).
    manual_steps = sum(1 for p, _ in logs for r in parse_log(p)
                       if r.get("event") == "anomaly_retry")

    reusable_core = all_skills
    skill_coverage = len(all_skills) / TOTAL_SKILLS
    autonomous_completion = (auto_steps / total_steps) if total_steps else 0.0
    # Manual baseline: without skills, each experiment type would need
    # MANUAL_STEPS_PER_EXP steps done by hand. With skills, only the manual
    # failure-retry steps remain.
    exp_types = len({s["experiment"] for s in per})
    manual_reduction = 1.0 - (manual_steps / (MANUAL_STEPS_PER_EXP * exp_types)
                              if (MANUAL_STEPS_PER_EXP * exp_types) else 0.0)

    metrics = {
        "reusable_core_skills": {"value": len(reusable_core), "target": 5, "ok": len(reusable_core) >= 5, "skills": sorted(reusable_core)},
        "workflow_skill_coverage": {"value": round(skill_coverage, 3), "target": 0.5, "ok": skill_coverage >= 0.5},
        "autonomous_completion": {"value": round(autonomous_completion, 3), "target": 0.6, "ok": autonomous_completion >= 0.6},
        "manual_step_reduction": {"value": round(manual_reduction, 3), "target": 0.6, "ok": manual_reduction >= 0.6, "manual_steps": manual_steps},
        "experiment_types_end_to_end": {"value": len(completed_exps), "target": 2, "ok": len(completed_exps) >= 2, "experiments": [s["experiment"] for s in completed_exps]},
    }

    ok_all = all(m["ok"] for m in metrics.values())
    return {
        "logs_analyzed": len(per),
        "experiments": per,
        "metrics": metrics,
        "all_objectives_met": ok_all,
    }


def main():
    ap = argparse.ArgumentParser(description="qntelli objective-metric tracker")
    ap.add_argument("--logs", nargs="*", default=[], help="state_log.jsonl files to analyze")
    ap.add_argument("--json", action="store_true", help="raw JSON output")
    args = ap.parse_args()

    report = compute(args.logs, Path.cwd())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=== qntelli OBJECTIVE METRICS ===")
        if "error" in report:
            print(" ", report["error"])
            print(" ", report["hint"])
            return 1
        print(f"logs analyzed: {report['logs_analyzed']}")
        for m, v in report["metrics"].items():
            mark = "OK " if v["ok"] else "BELOW"
            print(f"  [{mark}] {m:35s} {v['value']:.3f} (target {v['target']})")
            if m == "reusable_core_skills":
                print(f"           skills: {', '.join(v['skills'])}")
        print(f"\nALL OBJECTIVES MET: {report['all_objectives_met']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
