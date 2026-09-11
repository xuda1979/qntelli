# qntelli Harness Control Center (GUI)

A beautiful, **dependency-free** web dashboard for the qntelli quantum
harness. The server uses only the Python standard library (`http.server`) so
there is nothing to `pip install` — it runs on any Python 3.9+.

## What it controls

| Tab | Capability | Backed by |
|-----|------------|-----------|
| **Status** | harness health, SDK availability, benchmark summary, generated reports | `harness_results.json` + probes |
| **Orchestrator** | run any of 6 experiment chains (Bell/GHZ/QFT/Grover/opt/ML) with real execution + ion-trap emulator + .docx report; replay state logs | `orchestrator/orchestrator.py` |
| **Solver** | one-enter verified solve: offline goldens for supported families (deterministic, no model call) + on-line model-backed solve for general/custom questions (e.g. a bespoke XOR gate with `xor_gate(a,b)`), plus full-bank self-test | `solve.py` |
| **QAS 线路寻优** | circuit architecture search & resource evaluation | `qas_agent.py` |
| **Hardware** | ion-trap device catalog + job ledger (IonQ/Quantinuum/AQT) | `hardware/standard.py` |
| **Experience** | per-(algorithm×SDK) pass-rate knowledge base | `experience.py` |
| **Test Suite** | run the complete harness test campaign live; see per-suite verdicts | `tests/*` + `solve.py` + validator bench + orchestrator |

## Run

```bash
python3 quantum/gui/gui_app.py            # serves on http://127.0.0.1:8090
python3 quantum/gui/gui_app.py --port 8123 --host 0.0.0.0
```

Or use the wrapper:

```bash
./quantum/gui/run.sh
```

Open the printed URL in any modern browser. No build step, no bundler, no
node.

## Design notes (why it is bug-free by construction)

* **Crash isolation** — heavy harness operations (QAS simulation, solver)
  run in an **isolated subprocess** (`gui/worker.py`). A segfault in a
  C-extension (e.g. qiskit-aer) can never take down the GUI server. This was
  a real bug found during testing: the in-process QAS path crashed the whole
  HTTP server.
* **Robust parsing** — JSON extraction uses a balanced-brace parser
  (`_extract_first_json`), not brittle regex, so pretty-printed nested JSON
  (orchestrator summaries, hardware records) parses correctly.
* **Read-only hygiene** — the server never fabricates results; every number
  comes from the harness's own append-only ledgers and result DBs.
* **Solve reachability** — for general/custom questions (no analytic golden,
  e.g. "XOR gate with `xor_gate(a,b)`") the Solve button reaches a real model.
  `gui_app.py`/`worker.py` auto-load the huanxin DP4 endpoint exactly like the
  CLI launchers (`bin/qntelli-solve`, `qntelli.sh`) via `gui/envcfg.py` — a
  public default base-URL plus the standard `~/.codex/secrets/huanxin.env`
  API key. Set `QNTELLI_GUI_NO_AUTOCONFIG=1` to opt out (used by tests to keep
  the no-endpoint fallback deterministic).
* **Self-testing** — `quantum/tests/test_gui.py` starts a real server on an
  ephemeral port and exercises every endpoint, then confirms the server
  survives bad inputinches and crash-prone operations.

## Test the GUI

```bash
python3 quantum/tests/test_gui.py
```

Expect: **102/102 GREEN** (spins up its own server; no browser needed). Beyond
the endpoint + crash-isolation + malformed-input + param-cap ***server*** tests
it runs several layers of **front-end** verification so the dashboard itself is
bug-free:

* **Static regression guards** — the inline `<script>` is `'use strict'`, so
  every assigned identifier must be declared. A historical bug assigned
  `_qasmCache` without declaring it, which threw `ReferenceError` the instant a
  user opened the QAS tab; a test now forbids that class of error from
  returning.
* **Behavioural donut test** — the `donut()` chart is executed headlessly under
  node against a recording mock canvas and asserted to render the *real* pass
  rate (e.g. `75%`), not the old hard-coded `100.0%`, and to fall back to the
  running total when no explicit centre value is given.
* **Headless full-script load** — the entire extracted front-end runs inside a
  minimal DOM stub (`tests/gui_dom_stub.js`) under node and must reach the
  end-of-script marker with exit 0, catching any load-time `ReferenceError` or
  `TypeError` in the particle animation, every automatic loader, and the
  wire-up.
* **Happy-path render** — the same stub, but with `fetch` mocked to return
  realistic harness payloads so the automatic loaders actually **build** the
  DOM (stat cards, device/job/experience tables, donut + line + bar charts).
  Any rendering `TypeError` (bad template, null deref, chart math) is caught.
* **Falsification guard** — the happy-path run installs its own
  `unhandledRejection` / `uncaughtException` recorders and **fails** if any
  error fires during the async render. This closed a real class of bug: the
  status donut legend referenced an undeclared `num` variable, throwing
  `ReferenceError` that the stub's old no-op rejection handler silently
  swallowed while the test still "passed".
* **Behavioural helper tests** — the *real* `esc()` (XSS escaping),
  `fmtT()` (timestamp → em-dash on null) and `canvasSize()` (zero-size-canvas
  negative-radius guard) functions are executed headlessly under node and
  asserted on, by driving the full inline script inside the DOM stub.
* **Beauty/utility feature guards** — confirm the copy-to-clipboard button on
  the verified-code modal, the custom scrollbar styling, and the
  `prefers-reduced-motion` accessibility support all remain present.

All of these run with zero new npm/python dependencies (node is only used if
already installed).

## Files

* `gui_app.py` — the HTTP server + JSON API + harness integrations
* `worker.py` — crash-isolated subprocess worker for QAS
* `index.html` — the dashboard front-end (embedded CSS + JS)
* `run.sh` — convenience launcher
* `tests/test_gui.py` — the GUI test suite (also wired into `run_all_tests.sh`)
* `tests/gui_dom_stub.js` — minimal headless-DOM stub used by the load test


## API reference (all JSON)

| Method | Path | Body | Purpose |
|--------|------|------|---------|
| GET | `/api/status` | — | harness health & counts |
| GET | `/api/nav` | — | known experiments |
| GET | `/api/bench` | — | latest validator bench summary |
| POST | `/api/bench/run` | — | run the validator bench |
| POST | `/api/onetimepass/run` | — | run the one-enter onetimepass |
| POST | `/api/orchestrator/run` | `{experiment}` | run an experiment chain |
| POST | `/api/orchestrator/replay` | `{log}` | replay a state log |
| GET | `/api/orchestrator/logs` | — | list state logs |
| POST | `/api/solver/solve` | `{question}` | offline-golden verified solve |
| POST | `/api/solver/selftest/run` | — | full-bank self-test |
| POST | `/api/qas/run` | `{experiment}` | QAS circuit search |
| GET | `/api/hardware/devices` | — | device catalog |
| GET | `/api/hardware/jobs?limit=N` | — | job ledger |
| GET | `/api/experience` | — | knowledge-base stats |
| POST | `/api/tests/run` | `{live}` | run the full test campaign |
