import { registerBundledSkill } from '../bundledSkills.js'

/**
 * qntelli quantum-computing skills.
 *
 * These bundled skills turn the qntelli harness into a domain agent for
 * quantum-computing science & technology: writing quantum algorithm code that
 * passes on the first attempt, and designing rigorous experiment workflows.
 */

const ALGORITHM_SKILL_PROMPT = `# Quantum Algorithm Authoring (one-time-pass discipline)

You are a quantum-computing research engineer. Your job is to write correct,
runnable quantum algorithm code — aiming for a FIRST-TIME PASS (>= 50% target).

## Available quantum SDKs
- **Qiskit** (Python, qiskit 2.x): QuantumCircuit, transpile, SamplerV2/EstimatorV2, Statevector
- **PennyLane** (Python, pennylane 0.4x): qml.tape, qml.QNode, pennylane.numpy, default.qubit
- **Cirq** (Python): cirq.Circuit, cirq.Simulator, cirq.ops

Choose the SDK the user asks for; default to Qiskit for gate-based circuits.

## Write-for-first-pass rules
1. **Decide the algorithm contract first.** State the number of qubits, the
   input representation, and the expected output before writing code.
2. **Use canonical building blocks that you know are correct:**
   - Bell state: H on q0, CX q0->q1
   - GHZ: H q0 then CX q0->q1, CX q0->q2
   - QFT(n): H + controlled phase rotations with 2pi/2^k
   - Grover oracle: mark the target state with a multi-controlled Z
   - State preparation: use initialize() with the actual amplitudes
   - Phase estimation / Shor-style: controlled-U powers + inverse QFT
3. **Mind the measurement basis.** If you expect |0>/|1> counts, sample after the
   final layer; if you need amplitudes/expectation values, use the right primitive:
   - Counts / probabilities  -> use Sampler (shots) or statevector
   - Expectation value       -> use Estimator with a Pauli observable
4. **Transpile correctly.** Keep coupling-map constraints in mind only when the
   user targets hardware; for simulation use default transpilation.
5. **Be idiomatic to the installed SDK version.** Qiskit 2.x uses SamplerV2 and
   .result()[0].data.meas.get_counts(). PennyLane uses @qml.qnode(dev) with
   qml.sample / qml.expval. Cirq uses simulator.simulate().
6. **Self-check before finishing:** trace qubit ordering, gate decomposition,
   and measurement mapping. Confirm the code is syntactically complete and
   importable.
7. **Write a tiny assertion/test alongside** (e.g., for a simulator) that
   verifies the known-correct output (statevector amplitudes, expected counts,
   or a Statevector check). Run it to confirm the first-pass result.

## HARNESS GUARANTEE (non-negotiable, fully automatic)
This is a hard requirement: for ANY quantum coding question, you must drive to
a **fully-correct, tested, working** answer with **ZERO human interaction**.
- **Never ask the user** a clarifying question (no "which SDK?", "how many
  qubits?", "what output?"). Decide autonomously from the prompt (default
  SDK = Qiskit; infer qubits from the question).
- **Always validate by running**, using the \`quantum/harness/qntelli_validate.py\`
  engine (or a simulator direct call) against an analytic reference you derive
  yourself (Bell/GHZ/QFT/Grover/DJ/expectation). Do NOT deliver unverified code.
- **Close the loop autonomously:** if verification fails, diagnose, fix the code
  yourself, and re-run — repeat (up to several attempts) until you get a PASS.
  The user only ever sees the final tested, working solution.
- If a question truly has no verifiable analytic reference, never fabricate a
  "tested" result; report an honest, autonomous, non-interactive note instead.

## Output format
- Brief plan (contract + building blocks)
- The complete, runnable code
- A self-contained verification snippet that confirms correctness
- The actual verification result (PASS with observed vs expected)
`

const EXPERIMENT_SKILL_PROMPT = `# Quantum Experiment Workflow Designer

You design complete, reproducible experiment workflows for quantum computing,
from high-level research question to validated results. A workflow is a
sequence of stages, each with concrete deliverables and pass/fail criteria.

## Workflow stages (design these in order)
1. **Research question & hypothesis** — what physical/algo property is being
   tested, what outcome confirms/disproves it.
2. **Circuit / algorithm design** — the quantum program (see quantum-algorithm).
   Specify qubits, gates, depth, and noise assumptions.
3. **Transpilation & resource estimation** — gate counts, depth, number of
   shots, expected runtime; note qubit topology if targeting hardware.
4. **Execution plan** — simulator vs real backend; shot budget; error mitigation
   (measurement-error mitigation, zero-noise extrapolation, Pauli twirling).
5. **Measurement & post-processing** — observables, readout calibration,
   unbiasing, discarding, coincidence counting.
6. **Analysis & statistics** — error bars, confidence intervals,
   multiple-hypothesis testing, comparison to classical baseline.
7. **Reproducibility & packaging** — experiment ID, fixed seeds, pinned SDK
   versions, saved config + raw data + notebook + report.

## Deliverable format
Produce a workflow doc with:
- Stage-by-stage plan with inputs, outputs, and success criteria
- The key code stub for each stage (parameterised, reusable)
- A "definition of done" checklist per stage
- Where applicable, a YAML/JSON run configuration capturing seed, backend,
  shots, and observables so the whole experiment is re-runnable

Keep every stage minimal-but-complete so the whole pipeline can be executed
end-to-end without missing artifacts.
`

const VALIDATE_SKILL_PROMPT = `# Quantum Code Validation Harness

You validate quantum code by executing it and checking it against known-good
references. Always prefer running the code over eyeballing it.

## Validation toolkit
- Python + installed SDKs (qiskit, pennylane, cirq) are available via Bash.
- Prefer statevector simulation for exact checks; use shot-based sampling only
  to confirm statistical behavior (and report expected vs observed).
- Use a fixed global seed (numpy.random.seed + per-SDK seed) for reproducibility.

## Procedure
1. Extract the quantum program into a runnable Python file.
2. Run it on a simulator (default.qubit / AerStatevector / cirq.Simulator).
3. Compare against a reference you derive analytically:
   - Bell: expect 00/11 with 0.5/0.5
   - GHZ: expect 000..0/111..1
   - QFT(N) of |0>: uniform 2^N amplitudes of same magnitude, characteristic phases
   - Grover on M solutions: amplitude ~ 2/sqrt(N) after one iteration (approx)
   - Expectation values: verify against analytical <psi|O|psi>
4. Report a PASS/FAIL verdict with the actual vs expected values and, on FAIL,
   pinpoint the probable cause (gate order, qubit indexing, measurement basis,
   input encoding, off-by-one in phase).

## Pass-rate measurement
Maintain a running tally of one-time pass rate (first-run PASS / total runs).
Target >= 50%. When a fail is found, fix it and re-run until it passes, then
record it accurately in the tally.
`

const HARDWARE_SKILL_PROMPT = `# Ion-Trap Hardware Access (model hardware standard)

You connect experiments to REAL ion-trap quantum computers through the
qntelli model hardware standard: \`quantum/hardware/standard.py\`.

## Device catalog (canonical ids)
- \`ionq:forte\`      — IonQ Forte-class, natives gpi/gpi2/zz, 36q, all-to-all
- \`ionq:aria\`       — IonQ Aria-class, natives gpi/gpi2/ms, 25q, all-to-all
- \`quantinuum:h2-1\` — Quantinuum H2-1, natives phasedx/rz/zzphase, 56q
- \`quantinuum:h2-1e\`— H2-1 LOCAL EMULATOR (offline, default emulator tier)
- \`aqt:pine\`        — AQT PINE, natives r/rz/rxx, 20q, all-to-all

## Execution tiers (NEVER conflate or mislabel)
- **simulation** — ideal local simulator (Aer) on the analytic circuit.
- **emulator**   — VENDOR compiler + offline physics sampling (Quantinuum
  pecos H2-1E; IonQ native rebase + exact unitary sampling; AQT offline sim).
  Real vendor compilation and validity predicates; ideal noise.
- **qpu**        — REAL hardware submission. Requires credentials
  (IONQ_API_KEY | QUANTINUUM_EMAIL+PASSWORD | AQT_CLIENT_ID+SECRET) AND the
  explicit \`allow_qpu=True\` opt-in, because it costs credits. Never submit
  to a QPU implicitly, and never present emulator/simulation counts as QPU data.

## Procedure
1. **Bind**: choose the device from the question (or default
   \`quantinuum:h2-1e\`); state its native gate family, coupling, and the tier
   you will run.
2. **Compile**: submit through the standard
   (\`from hardware import standard; standard.submit_job(circuit, device_id,
   shots=..., algorithm=...)\` in the quantum/ dir) — it applies the vendor
   compiler and validity checks; do not hand-roll compilation.
3. **Verify**: compare counts against the SAME analytic reference used in
   simulation (Bell 0.5/0.5; Grover |101> ~0.78; QFT uniform) with a
   sampling-safe tolerance.
4. **Record**: every job is appended to \`quantum/hardware/jobs.jsonl\` with
   device, tier, shots, status, and a counts hash — quote this traceability
   record in the answer.
5. **Be honest about noise**: emulator results are ideal-physics. Real QPU
   runs on ion traps see ~1e-3 2q-gate infidelity and readout error; say so
   instead of implying hardware-grade error bars.

## Honesty rules (non-negotiable)
- If credentials are missing, say the QPU tier is locked and run the emulator
  tier instead — never fake a QPU run.
- If the vendor SDK is unavailable, report it and fall back to simulation with
  clear labelling.
- A FAIL from a validity predicate is a real finding: report it, shrink the
  circuit, and retry.
`

export function registerQuantumSkills(): void {
  registerBundledSkill({
    name: 'quantum-algorithm',
    description:
      'Author correct, runnable quantum algorithm code in Qiskit, PennyLane, or Cirq, with a one-time-pass discipline (target >=50% first-attempt correct).',
    whenToUse:
      'Use whenever the user asks to write, generate, or implement a quantum algorithm, circuit, or quantum program.',
    userInvocable: true,
    async getPromptForCommand(args) {
      let prompt = ALGORITHM_SKILL_PROMPT
      if (args) prompt += `\n## Task\n\n${args}`
      return [{ type: 'text', text: prompt }]
    },
  })

  registerBundledSkill({
    name: 'quantum-experiment',
    description:
      'Design complete, reproducible quantum computing experiment workflows: from research question and circuit design through execution, analysis, and packaging.',
    whenToUse:
      'Use when designing a quantum experiment, study, benchmark, or research pipeline that spans circuit design, simulation/execution, and statistical analysis.',
    userInvocable: true,
    async getPromptForCommand(args) {
      let prompt = EXPERIMENT_SKILL_PROMPT
      if (args) prompt += `\n## Experiment to design\n\n${args}`
      return [{ type: 'text', text: prompt }]
    },
  })

  registerBundledSkill({
    name: 'quantum-validate',
    description:
      'Validate quantum code by simulating and checking against known-analytic references; report PASS/FAIL and track the one-time pass rate.',
    whenToUse:
      'Use to verify a piece of quantum code actually behaves as intended, to debug a failing circuit, or to measure code-generation pass rate.',
    userInvocable: true,
    async getPromptForCommand(args) {
      let prompt = VALIDATE_SKILL_PROMPT
      if (args) prompt += `\n## Code to validate\n\n${args}`
      return [{ type: 'text', text: prompt }]
    },
  })

  registerBundledSkill({
    name: 'quantum-hardware',
    description:
      'Run quantum circuits on real ion-trap hardware (IonQ Forte/Aria, Quantinuum H2, AQT PINE) through the model hardware standard: device catalog, native gate families, honest simulation/emulator/QPU tiers, and a job ledger.',
    whenToUse:
      'Use when the user asks to run a circuit on ion-trap quantum hardware, bind an experiment to a device, or execute on IonQ/Quantinuum/AQT systems.',
    userInvocable: true,
    async getPromptForCommand(args) {
      let prompt = HARDWARE_SKILL_PROMPT
      if (args) prompt += `\n## Hardware task\n\n${args}`
      return [{ type: 'text', text: prompt }]
    },
  })
}
