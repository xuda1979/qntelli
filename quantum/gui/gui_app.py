
#!/usr/bin/env python3
"""
qntelli GUI - a beautiful, dependency-free web control center for the qntelli
quantum-computing harness.

This server uses ONLY the Python standard library (http.server, json,
subprocess, threading, urllib) so it runs anywhere Python 3.9+ runs with
zero pip installs. It wraps every harness component (orchestrator, validator
bench, one-enter solver, QAS agent, model-hardware standard, experience
knowledge base, report generation, and the full test suite) behind a clean
JSON API and serves a single-page dark-themed dashboard.

Run:
    python3 quantum/gui/gui_app.py [--port 8090] [--host 127.0.0.1]
Then open http://127.0.0.1:8090 in a browser.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---- paths ----------------------------------------------------------------
HERE = Path(__file__).resolve().parent
QUANTUM = HERE.parent
PROJECT = QUANTUM.parent
PY = sys.executable
REPORTS_DIR = PROJECT / "reports"

# Populate the model-endpoint env (base URL + API key) exactly like the CLI
# launchers so the on-line solve path can reach a real model for
# general/custom questions (no analytic golden). Must happen before any
# `import solve` reads its env. Respects caller-set env; tests can opt out
# with QNTELLI_GUI_NO_AUTOCONFIG=1 to keep the deterministic no-endpoint
# fallback offline.
sys.path.insert(0, str(HERE))
import envcfg  # noqa: E402
envcfg.configure_endpoint()

# shared mutable runtime state (guarded by a lock)
_STATE_LOCK = threading.Lock()
_ACTIVE_JOBS = {}  # job_id -> {kind, status, logs, result, ...}

_job_counter = 0


def _next_job_id() -> str:
    global _job_counter
    _job_counter += 1
    return f"job-{int(time.time())}-{_job_counter}"


def _sh(cmd, timeout=300, cwd=None):
    """Run a command, return (returncode, stdout_text, stderr_text)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd=str(cwd or PROJECT))
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"


def _read_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _read_json_array(path):
    """Read a JSONL file into a list of dicts, skipping malformed lines."""
    p = Path(path)
    rows = []
    if not p.exists():
        return rows
    try:
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return rows


def _extract_first_json(text):
    """Parse the first balanced JSON object in a text blob (handles nested
    braces and pretty-printed output). Returns dict or None."""
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def _safe_str(x):
    return x if isinstance(x, str) else json.dumps(x)


def _latest_iso_epoch(ts) -> int | None:
    """Return the UNIX epoch (seconds) for a timestamp that may be an ISO-8601
    string (e.g. '2026-08-30T13:18:47+0800'), an integer epoch, or a float
    epoch. Returns None if it cannot be parsed. Robust to the non-standard
    '+0800' offset (no colon) that JS Date can mis-parse."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        # treat large values as epoch seconds, or millis if absurdly large
        return int(ts) if ts < 1e12 else int(ts) // 1000
    if not isinstance(ts, str):
        return None
    s = ts.strip()
    if not s:
        return None
    # numeric string -> epoch
    try:
        if s.replace(".", "", 1).isdigit() or s.lstrip("-").replace(".", "", 1).isdigit():
            f = float(s)
            return int(f) if f < 1e12 else int(f) // 1000
    except ValueError:
        pass
    # ISO string: splice a ':' into a bare +HHMM / -HHMM zone (non-standard)
    m = re.match(r"^(.*?)([+-]\d{2})(\d{2})$", s)
    if m:
        s = m.group(1) + m.group(2) + ":" + m.group(3)
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return None


def _top_outcome(counts) -> str | None:
    """Return the most-frequent outcome label for a {bitstring: count} dict,
    or None if a representative outcome cannot be determined."""
    if not isinstance(counts, dict) or not counts:
        return None
    try:
        best = max(counts.items(), key=lambda kv: int(kv[1]))
        return best[0]
    except (ValueError, TypeError):
        return None


class HarnessAPI:
    """Stateless, import-safe wrappers around every harness CLI."""

    # ---- status / overview ------------------------------------------------
    def status(self):
        bench = _read_json(QUANTUM / "benchmarks" / "harness_results.json") or {}
        odb = _read_json(QUANTUM / "benchmarks" / "results.json") or []
        return {
            "python": sys.version.split()[0],
            "harness_ready": self._modules_importable(),
            "bench": bench.get("summary", {}),
            "runs_total": len(bench.get("runs", [])),
            "onetimepass_total": len(odb) if isinstance(odb, list) else 0,
            "jobs_total": self._count_jobs(),
            "reports": self._list_reports(),
            "experience_total": self._experience_total(),
            "ts": int(time.time()),
        }

    def _modules_importable(self):
        probes = [
            ("qiskit", "qiskit"),
            ("pennylane", "pennylane"),
            ("cirq", "cirq"),
        ]
        out = {}
        for name, mod in probes:
            try:
                __import__(mod)
                out[name] = True
            except Exception:
                out[name] = False
        return out

    def _count_jobs(self):
        p = QUANTUM / "hardware" / "jobs.jsonl"
        if not p.exists():
            return 0
        n = 0
        try:
            with p.open() as f:
                for _ in f:
                    n += 1
        except Exception:
            pass
        return n

    def _list_reports(self):
        out = []
        if REPORTS_DIR.exists():
            for f in sorted(REPORTS_DIR.glob("*_case_study.docx"))[-10:]:
                out.append({"name": f.name, "mtime": int(f.stat().st_mtime)})
        return out

    def _experience_total(self):
        p = QUANTUM / "experience" / "samples.jsonl"
        if not p.exists():
            return 0
        n = 0
        try:
            with p.open() as f:
                for _ in f:
                    n += 1
        except Exception:
            pass
        return n

    # ---- validator bench --------------------------------------------------
    def bench_report(self):
        return _read_json(QUANTUM / "benchmarks" / "harness_results.json")

    def bench_run(self):
        rc, out, err = _sh([PY, str(QUANTUM / "harness" / "qntelli_validate.py"),
                            "bench"])
        return {"rc": rc, "output": out + err}

    # ---- onetimepass ------------------------------------------------------
    def onetimepass(self):
        rc, out, err = _sh([PY, str(QUANTUM / "benchmarks" / "onetimepass.py"),
                            "--offline"])
        return {"rc": rc, "output": out + err}

    # ---- orchestrator -----------------------------------------------------
    def orchestrator_run(self, experiment, report_dir=None):
        cmd = [PY, str(QUANTUM / "orchestrator" / "orchestrator.py"),
               "--design-start", experiment]
        if report_dir:
            cmd += ["--report-dir", report_dir]
        rc, out, err = _sh(cmd, timeout=300)
        summary = _extract_first_json(out)
        return {"rc": rc, "stdout": out, "stderr": err, "summary": summary}

    def orchestrator_replay(self, log_path):
        lp = Path(log_path)
        if not lp.is_absolute():
            cand = QUANTUM / log_path
            if cand.exists():
                lp = cand
        if not lp.exists():
            return {"rc": 1, "error": f"log not found: {log_path}"}
        rc, out, err = _sh([PY, str(QUANTUM / "orchestrator" / "orchestrator.py"),
                            "--replay", str(lp)])
        return {"rc": rc, "output": out + err, "file": str(lp)}

    def orchestrator_logs(self):
        out = []
        for f in sorted(PROJECT.glob("state_log*.jsonl")):
            out.append({"name": f.name, "mtime": int(f.stat().st_mtime),
                        "lines": self._log_lines(f)})
        return out

    def _log_lines(self, p):
        try:
            return len(p.read_text().splitlines())
        except Exception:
            return 0

    # ---- solver (offline goldens) -----------------------------------------
    def solver_selftest(self):
        rc, out, err = _sh([PY, str(QUANTUM / "solve.py"), "--self-test"],
                           timeout=180)
        return {"rc": rc, "output": out + err}

    def solver_solve(self, question, sdk="qiskit", online=False):
        """Run the one-enter solver.

        * Default (online=False): OFFLINE golden mode only — no model calls, so
          it is deterministic and testable in CI. Supported-family questions
          (Bell/GHZ/QFT/Grover/...) return their verified golden; general/custom
          questions (no analytic golden) return a clear `ok:false` + `detail`.
        * online=True: allow a MODEL-backed general solve for custom questions
          (e.g. a bespoke XOR circuit with a required signature). Falls back to
          the offline golden for supported families; for general questions it
          calls the configured model, verifies the code RUNS, and self-corrects.
          If no model endpoint is configured it returns a clear error."""
        q = (question or "").strip()
        if not q:
            return {"rc": 1, "error": "empty question"}
        try:
            sys.path.insert(0, str(QUANTUM))
            import solve as _solve
        except Exception as e:
            return {"rc": 1, "error": f"solve import failed: {e}"}
        # A related-family question can always be answered offline with its
        # verified golden — never require the model for those.
        try:
            cls = _solve.classify(q)
            has_golden = cls.get("ref_type") is not None
        except Exception:
            has_golden = False
        if has_golden:
            # OFFLINE golden path (in-process — never executes generated code).
            try:
                res = _solve.solve(q, mode="qntelli", offline=True)
                res["solve_mode"] = "offline-golden"
                return {"rc": 0, "result": res}
            except Exception as e:
                return {"rc": 1, "error": f"solve failed: {e}"}
        # GENERAL / CUSTOM question (no analytics golden): resolve it online —
        # when a model endpoint is configured (auto-online so clicking Solve
        # "just works"), else return a clear, non-silent error.
        try:
            payload = json.dumps({"op": "solve",
                                  "args": {"question": q,
                                           "online": bool(online)}})
            p = subprocess.run([PY, str(HERE / "worker.py")],
                               input=payload, capture_output=True,
                               text=True, timeout=600)
            if p.returncode != 0:
                return {"rc": p.returncode,
                        "error": (p.stderr or p.stdout)[-500:]}
            data = json.loads(p.stdout or "{}")
            if not data.get("ok"):
                return {"rc": 1, "error": data.get("error", "worker error")}
            return {"rc": 0, "result": data["result"].get("result")}
        except Exception as e:
            return {"rc": 1, "error": f"solve failed: {e}"}

    # ---- qas agent --------------------------------------------------------
    def qas_run(self, experiment):
        """Run the QAS circuit-search. Executed in an ISOLATED subprocess
        (gui/worker.py) so a C-extension crash in quantum simulation can never
        take down the GUI server."""
        try:
            payload = json.dumps({"op": "qas",
                                  "args": {"experiment": experiment}})
            p = subprocess.run([PY, str(HERE / "worker.py")], input=payload,
                               capture_output=True, text=True, timeout=180)
            if p.returncode != 0:
                return {"rc": p.returncode,
                        "error": (p.stderr or p.stdout)[-500:]}
            data = json.loads(p.stdout or "{}")
            if not data.get("ok"):
                return {"rc": 1, "error": data.get("error", "worker error")}
            return {"rc": 0, "result": data["result"].get("result")}
        except Exception as e:
            return {"rc": 1, "error": f"qas failed: {e}"}

    # ---- hardware ---------------------------------------------------------
    def hardware_devices(self):
        try:
            sys.path.insert(0, str(QUANTUM / "hardware"))
            import standard as hw
            return {"rc": 0, "devices": hw.list_devices()}
        except Exception as e:
            return {"rc": 1, "error": f"hardware import failed: {e}"}

    def hardware_jobs(self, limit=50):
        p = QUANTUM / "hardware" / "jobs.jsonl"
        rows = []
        if p.exists():
            for line in reversed(p.read_text().splitlines()):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                # Normalise fields for the frontend so it never has to guess:
                # provide a reliable epoch and the top measured outcome.
                rec["_epoch"] = _latest_iso_epoch(rec.get("ts"))
                if "counts_top" not in rec or rec.get("counts_top") is None:
                    rec["counts_top"] = _top_outcome(rec.get("counts"))
                rows.append(rec)
                if len(rows) >= limit:
                    break
        return {"jobs": rows, "total": self._count_jobs()}

    # ---- experience -------------------------------------------------------
    def experience_stats(self):
        try:
            sys.path.insert(0, str(QUANTUM))
            import experience as _exp
            samples = _exp.load_samples()
            return {"rc": 0, "stats": _exp.stats(samples),
                    "samples": samples[-30:]}
        except Exception as e:
            return {"rc": 1, "error": f"experience failed: {e}"}

    # ---- charts / aggregate data -----------------------------------------
    def charts(self):
        """Aggregate lightweight data for the dashboard's visualisations:
        hardware tier distribution, hardware job status, bench pass-rate
        history, and experience per-algorithm pass-rate bars. Pure reads from
        the append-only ledgers; never fabricates values."""
        out = {"hardware_tiers": {}, "hardware_status": {},
               "experience_groups": [], "experience_total": {"pass": 0, "fail": 0}}

        # hardware ledger
        p = QUANTUM / "hardware" / "jobs.jsonl"
        if p.exists():
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                tier = str(rec.get("tier") or "unknown")
                status = str(rec.get("status") or "unknown")
                out["hardware_tiers"][tier] = out["hardware_tiers"].get(tier, 0) + 1
                out["hardware_status"][status] = out["hardware_status"].get(status, 0) + 1

        # experience ledger
        exp = _read_json_array(QUANTUM / "experience" / "samples.jsonl")
        groups = {}
        for s in exp:
            algo = str(s.get("algorithm") or s.get("family") or "unknown")
            sdk = str(s.get("sdk") or "unknown")
            key = f"{algo}/{sdk}"
            g = groups.setdefault(key, {"pass": 0, "fail": 0})
            # the experience ledger records the verdict in the `ok` field
            if s.get("ok"):
                g["pass"] += 1
                out["experience_total"]["pass"] += 1
            else:
                g["fail"] += 1
                out["experience_total"]["fail"] += 1
        out["experience_groups"] = [{"key": k, **v} for k, v in groups.items()]

        # bench pass-rate history: the runs array is a flat list of per-task
        # pass/fail records, so aggregate into a bucketed line for the chart.
        bench = _read_json(QUANTUM / "benchmarks" / "harness_results.json") or {}
        runs = bench.get("runs", [])
        hist = []
        if isinstance(runs, list) and runs:
            bucket = 20
            for i in range(0, len(runs), bucket):
                chunk = [r for r in runs[i:i + bucket] if isinstance(r, dict)]
                if not chunk:
                    continue
                passed = sum(1 for r in chunk if r.get("pass"))
                # true per-run totals are unknown (array is already condensed);
                # use bucket size as the denominator for a stable rate.
                hist.append({"pass": passed, "total": len(chunk),
                             "rate": round(passed / len(chunk), 3)})
        out["bench_history"] = hist
        return out

    # ---- full test suite -------------------------------------------------
    def tests_run(self, include_live=False):
        log = []
        results = {}

        def line(msg):
            log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

        line("starting harness test campaign")
        tests = [
            ("compile", [PY, "-m", "py_compile",
                         str(QUANTUM/"solve.py"),
                         str(QUANTUM/"report_gen.py"),
                         str(QUANTUM/"qas_agent.py"),
                         str(QUANTUM/"experience.py"),
                         str(QUANTUM/"hardware/standard.py"),
                         str(QUANTUM/"harness/qntelli_validate.py"),
                         str(QUANTUM/"orchestrator/orchestrator.py")]),
            ("guarantee", [PY, str(QUANTUM/"tests/test_solve_guarantee.py")]),
            ("qas", [PY, str(QUANTUM/"tests/test_qas_agent.py")]),
            ("experience", [PY, str(QUANTUM/"tests/test_experience.py")]),
            ("report_gen", [PY, str(QUANTUM/"tests/test_report_gen.py")]),
            ("hardware", [PY, str(QUANTUM/"tests/test_hardware_standard.py")]),
            ("solve_selftest", [PY, str(QUANTUM/"solve.py"), "--self-test"]),
            ("validators_bench", [PY, str(QUANTUM/"harness/qntelli_validate.py"), "bench"]),
        ]
        for name, cmd in tests:
            line(f"running {name} ...")
            rc, out, err = _sh(cmd, timeout=600)
            ok = rc == 0
            results[name] = {"rc": rc, "ok": ok}
            tail = (out + err).strip().splitlines()[-1] if (out+err).strip() else ""
            line(f"{name}: {'OK' if ok else 'FAIL'} rc={rc} | {tail}")
        line("orchestrator (real, all experiments) ...")
        rc, out, err = _sh([PY, str(QUANTUM/"orchestrator/orchestrator.py"),
                            "--design-start", "bell ghz qft grover optimization ml",
                            "--report-dir", str(REPORTS_DIR)], timeout=600)
        done = out.count('"autonomous_complete": true') if rc == 0 else 0
        results["orchestrator"] = {"rc": rc, "ok": rc == 0 and done >= 1,
                                    "complete": done}
        line(f"orchestrator: rc={rc} complete={done}/6")

        if include_live:
            line("LIVE one-enter tests (needs endpoint) ...")
            rc, out, err = _sh([PY, str(QUANTUM/"tests/test_solve_live.py")],
                               timeout=600)
            results["live"] = {"rc": rc, "ok": rc == 0}
            line(f"live: {'OK' if rc==0 else 'FAIL'} rc={rc}")

        passed = sum(1 for r in results.values() if r["ok"])
        line(f"done: {passed}/{len(results)} suites green")
        return {"log": log, "results": results,
                "passed": passed, "total": len(results)}


# ---- static frontend -------------------------------------------------------
INDEX_HTML = None


def _load_index_html():
    global INDEX_HTML
    p = HERE / "index.html"
    if p.exists():
        INDEX_HTML = p.read_text()
        return True
    return False


def _bootfront_command():
    return [PY, str(HERE / "gui_app.py")]


class Handler(BaseHTTPRequestHandler):
    server_version = "qntelli-gui/0.1"
    api = HarnessAPI()

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _safe_write(wfile, body):
        """Write a response body, tolerating a client that disconnects mid-write
        (e.g. the user closes/refreshes the browser tab while a large solve/status
        payload is streaming). An uncaught BrokenPipeError / ConnectionResetError
        would print an ugly stack trace in the server handler thread for an action
        that is completely benign to the server — so squash exactly those
        disconnects and nothing else."""
        try:
            wfile.write(body)
            wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # client went away; nothing we can or should do

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._safe_write(self.wfile, body)

    def _send_text(self, text, code=200, ctype="text/plain; charset=utf-8"):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._safe_write(self.wfile, body)

    def _send_html(self, text, code=200):
        self._send_text(text, code, "text/html; charset=utf-8")

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
        except Exception:
            n = 0
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def log_message(self, fmt, *args):  # quieter logs
        pass

    # ---- routing ----------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            if _load_index_html():
                self._send_html(INDEX_HTML)
            else:
                self._send_html(BUILTIN_INDEX, 200)
            return
        if path == "/api/status":
            self._send_json(self.api.status())
            return
        if path == "/api/bench":
            self._send_json(self.api.bench_report())
            return
        if path == "/api/onetimepass":
            self._send_json(self.api.onetimepass())
            return
        if path == "/api/solver/selftest":
            self._send_json(self.api.solver_selftest())
            return
        if path == "/api/hardware/devices":
            self._send_json(self.api.hardware_devices())
            return
        if path == "/api/hardware/jobs":
            limit = 50
            q = urllib.parse.parse_qs(parsed.query)
            if q.get("limit"):
                try:
                    limit = min(int(q["limit"][0]), 500)
                except Exception:
                    pass
            self._send_json(self.api.hardware_jobs(limit))
            return
        if path == "/api/experience":
            self._send_json(self.api.experience_stats())
            return
        if path == "/api/orchestrator/logs":
            self._send_json(self.api.orchestrator_logs())
            return
        if path == "/api/nav":
            self._send_json(_nav_payload())
            return
        if path == "/api/charts":
            self._send_json(self.api.charts())
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        if path == "/api/bench/run":
            self._run_blocking("bench_run", self.api.bench_run)
            return
        if path == "/api/onetimepass/run":
            self._run_blocking("onetimepass_run", self.api.onetimepass)
            return
        if path == "/api/orchestrator/run":
            exp = body.get("experiment", "bell")
            self._run_blocking("orchestrator",
                               lambda: self.api.orchestrator_run(exp, str(REPORTS_DIR)))
            return
        if path == "/api/orchestrator/replay":
            lp = body.get("log", "")
            self._run_blocking("orchestrator_replay",
                               lambda: self.api.orchestrator_replay(lp))
            return
        if path == "/api/solver/selftest/run":
            self._run_blocking("solver_selftest", self.api.solver_selftest)
            return
        if path == "/api/solver/solve":
            q = body.get("question", "")
            online = bool(body.get("online", False))
            self._run_blocking("solver_solve",
                               lambda: self.api.solver_solve(q, online=online))
            return
        if path == "/api/qas/run":
            exp = body.get("experiment", "bell")
            self._run_blocking("qas", lambda: self.api.qas_run(exp))
            return
        if path == "/api/tests/run":
            include_live = bool(body.get("live", False))
            self._run_blocking(
                "tests",
                lambda: self.api.tests_run(include_live=include_live),
                timeout=1200)
            return
        self._send_json({"error": "not found"}, 404)

    def _run_blocking(self, kind, fn, timeout=1200):
        """Run a potentially slow harness operation synchronously and return
        the JSON result to the caller."""
        try:
            result = fn()
            result = dict(result)
            result["_kind"] = kind
            self._send_json({"ok": True, "result": result})
        except Exception as e:
            import traceback
            self._send_json({"ok": False, "error": str(e),
                             "trace": traceback.format_exc()[-1500:]})


def _nav_payload():
    """Lightweight payload the UI uses to show which harness pieces exist."""
    known_experiments = ["bell", "ghz", "qft", "grover", "optimization", "ml"]
    return {"experiments": known_experiments}


# ---- built-in index (used if index.html is missing) ------------------------
BUILTIN_INDEX = """<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>qntelli GUI</title></head><body style='font-family:sans-serif'>
<h1>qntelli harness control center</h1>
<p>Embedded index not found. The GUI front-end lives in index.html next to
this server. Place it there (or re-run setup) and refresh.</p>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="qntelli harness GUI")
    ap.add_argument("--host", default=os.environ.get("QNTELLI_GUI_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("QNTELLI_GUI_PORT", "8090")))
    args = ap.parse_args()

    # make import path see the quantum package
    sys.path.insert(0, str(QUANTUM))

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("*" * 60)
    print("  qntelli harness GUI")
    print(f"  serving at http://{args.host}:{args.port}")
    print("  (Ctrl-C to stop)")
    print("*" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping ...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
