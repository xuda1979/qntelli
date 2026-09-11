# qntelli

**qntelli** is an intelligent agent for **quantum-computing science and
technology**. It writes correct quantum algorithm code, designs rigorous
experiment workflows, runs simulations, and validates results — with a target
of **>= 50% first-attempt code correctness** on standard algorithms.

qntelli is a purpose-built harness (a customised fork) that speaks to a model
deployment via the same endpoint and credentials used by `claude -p huanxin
-m dp4`, rebranded entirely around the quantum-computing domain.

---

## What qntelli does

- **Writes quantum algorithm code** in **Qiskit**, **PennyLane**, and **Cirq**.
- **Verifies it against analytic references** and **silently self-corrects**
  until a solution PASSES (the "one-enter" guarantee: you only ever receive
  tested, runnable code — or an honest, non-fabricated failure).
- **Verified algorithm library** (each with an analytic reference + golden
  solution, so one-enter verification works even fully offline, no model call):

  | Family | Verifier |
  |--------|----------|
  | Bell / GHZ | amplitude probabilities (n-aware up to any qubit count) |
  | Quantum Fourier Transform (QFT) | uniform-superposition probabilities |
  | Deutsch–Jozsa | conclusive const/balanced result |
  | Grover | requested marked state is the dominant top outcome |
  | expectation value (`<Z>`, EstimatorV2) | value within tolerance |
  | **Bernstein–Vazirani** | top measured bitstring == hidden secret |
  | **Swap test** | expected P(ancilla=1) for equal vs unequal states |
  | **Quantum Phase Estimation (QPE)** | estimated phase matches target eigenphase |
  | **VQE (variational eigensolver)** | converged energy near exact ground-state energy |
  | uniform / state-prep | uniform-superposition probabilities |
  | general / test-driven (`--test-file`) | user-supplied harness must pass |

- **Cross-framework one-enter verification** — the same algorithm can be
  requested and VERIFIED in **Qiskit**, **PennyLane**, or **Cirq**. The analytic
  reference is SDK-agnostic (probabilities/energy/phase are the same physics);
  the harness picks SDK-specific goldens, skips Qiskit-only autocorrect for
  non-Qiskit code, and gives SDK-aware repair feedback. The foundational Bell/GHZ
  families are covered in all three SDKs.
- **Designs experiment workflows** end-to-end: research question → circuit →
  transpilation & resource estimation → execution plan → measurement &
  post-processing → analysis → reproducible packaging.
- **QAS 智能体 (线路寻优)** — searches and evaluates candidate circuit
  implementations (baseline + transpile optimization levels) against depth,
  two-qubit-gate-count, and fidelity constraints (the analytic reference), then
  selects the best satisfying candidate. Usable standalone
  (`qas_agent.py --qasm <file> --ref '{...}'`) and wired into the orchestrator
  as the `qc.circuit.transpile` stage, so "线路寻优 → 仿真 → 验证 → 报告" is a
  real step in the Harness, not a placeholder.
- **Model hardware standard (ion-trap devices)** — `quantum/hardware/` is a
  vendor-neutral contract for connecting to REAL trapped-ion quantum computers:
  IonQ Forte/Aria (gpi/gpi2/zz|ms natives), Quantinuum H2/H1/Helios
  (phasedx/rz/zzphase), AQT PINE (r/rz/rxx) — all with all-to-all coupling.
  Three explicit execution tiers (simulation / emulator / qpu) are never
  conflated: the emulator tier runs REAL vendor compilers with offline physics
  sampling (Quantinuum pecos H2-1E, IonQ native-gate unitary sampling, AQT
  offline sim); QPU submission is credential- AND opt-in gated (never implicit,
  because it costs credits). Every job is appended to
  `quantum/hardware/jobs.jsonl` with device, tier, shots, status, and a counts
  hash for traceability. Wired into the orchestrator as the
  `qc.hardware.bind` + `qc.hardware.execute` stages, so every experiment can
  finish on an ion-trap device:

  ```bash
  python3 quantum/hardware/standard.py --devices          # device catalog
  python3 quantum/hardware/standard.py --check            # per-vendor capability
  python3 quantum/hardware/standard.py --run grover --device quantinuum:h2-1e
  # verified offline: Grover |101> top=101 @ peak 0.778 (analytic 0.78) on the
  # Quantinuum H2-1 local emulator (vendor compile + pecos), 8/8 device x
  # algorithm matrix green (IonQ forte/aria, Quantinuum H2-1E, AQT PINE)
  ```
- **成果交付与经验沉淀 (experience harvesting)** — every solve outcome (success
  AND failure) is recorded to an append-only knowledge log
  (`quantum/experience/samples.jsonl`) with algorithm, SDK, pass/fail, attempts,
  verification stage and code hash. These samples feed the knowledge base /
  training pool (blueprint ⑤), with per-(algorithm×SDK) pass-rate aggregation
  via `python3 quantum/experience.py --report`. Harvesting is failure-safe and
  never affects the solve result.
- **Tracks the one-time pass rate** (target >= 50%; current goldens 100%), and
  prints a **per-(algorithm-family × SDK) pass-rate dashboard** via
  `qntelli-solve --self-test`, so the agent can measure its own first-try
  verification quality across frameworks.
- Comes with the four bundled **quantum skills**: `quantum-algorithm`,
  `quantum-experiment`, `quantum-validate`, and `quantum-hardware`
  (ion-trap device access via the model hardware standard).

---

## Install

```bash
./install.sh
```

This compiles the standalone `qntelli` binary, writes a default `qntelli.env`,
and installs the `qntelli` wrapper onto `PATH`.

### Connection defaults
qntelli uses the same provider/endpoint/API key as `claude -p huanxin -m dp4`:
- Base URL: `HUANXIN_DP4_BASE_URL` (default huanxin dp4 ingress).
- API key: `HUANXIN_DP4_API_KEY` from `~/.codex/secrets/huanxin.env`.
- Model: `dp4`.

Set `QNTELLI_BASE_URL`, `QNTELLI_API_KEY`, `QNTELLI_MODEL` (or edit
`qntelli.env`) to override.

---

## Usage

```bash
qntelli --print "write a 3-qubit GHZ circuit and verify it"   # headless
qntelli                                                        # interactive
```

### One-click solver — also conversational

```bash
qntellisolve "write a 3-qubit GHZ and verify it"   # one-shot, returns VERIFIED code
qntellisolve --interactive                          # multi-turn, like codex / claude-code
echo "write a Bell circuit" | qntellisolve          # pipe a question
```

`--interactive` (alias `--repl`) opens a session where a human stays in the
loop: ask a question, get harness-VERIFIED code, then follow up ("now make it
4 qubits", "convert to PennyLane") — prior turns are threaded to the model as
context. Built-in commands: `!help`, `!last`, `!clear`, `!count`, `quit`.
Inside the session you are never shown a partial attempt — only passing, tested
code (or an honest failure message). Run `qntellisolve` with no question on a
terminal and it offers to start the interactive session.

### Quantum skills (invocable inside a session)
- **`/quantum-algorithm`** — author correct, runnable quantum code (first-pass discipline).
- **`/quantum-experiment`** — design a complete, reproducible experiment workflow.
- **`/quantum-validate`** — simulate and validate code; track the pass rate.

---

## Quantum harness (`quantum/`)

```
quantum/
├── harness/qntelli_validate.py   # validation + pass-rate harness (Qiskit/PennyLane/Cirq)
├── templates/
│   ├── experiment_workflow.md     # stage-by-stage experiment design template
│   └── benchmark_entanglement.py  # runnable end-to-end example experiment
├── reference/
│   └── canonical-building-blocks.md # verified building blocks for first-pass code
└── benchmarks/                    # results.json (pass-rate database)
```

```bash
python3 quantum/harness/qntelli_validate.py bench    # run built-in benchmark suite
python3 quantum/harness/qntelli_validate.py report  # show tracked pass rate
python3 quantum/harness/qntelli_validate.py run file.py --sdk qiskit
```

---

## Architecture note

The harness depends on the `@anthropic-ai/sdk` runtime contract
(`ANTHROPIC_*` env variables, `CLAUDE_CODE_*` host flags, and the
`~/.claude` home directory). qntelli renames all user-facing product branding
to **qntelli** while preserving these internal runtime identifiers that the
underlying model SDK requires. The `qntelli` wrapper sets them transparently.
