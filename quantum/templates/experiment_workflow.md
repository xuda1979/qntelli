# qntelli Quantum Experiment Workflow Template

Use this template to design any quantum-computing experiment reproducibly.
Each stage has inputs, outputs, and a "definition of done" (DoD). Keep every
stage complete enough to run end-to-end.

## 0. Metadata (fill once)
```yaml
experiment_id: <slug>
title: <short descriptive title>
objective: <hypothesis / quantity being measured>
sdk: qiskit | pennylane | cirq
backend: simulator | <hardware name>
backend_basis: [ibm_brisbane, fake_vigo, default.qubit, ...]
seed: 42
shots: 4000
mitigation: [measurement_error | zne | pauli_twirling | none]
reporter: <who/what generated this>
```

## 1. Research question & hypothesis
- State the physical/algorithmic property under test.
- Define the falsifiable outcome (what result confirms / disproves the hypothesis).
- **DoD**: one sentence hypothesis + one explicit confirmation condition.

## 2. Circuit / algorithm design
- Qubit count, initial state, gate sequence (reference the `quantum-algorithm` skill).
- Depth, gate count, connectivity constraints (if hardware).
- **DoD**: a parameterised circuit builder function; compiles & simulates correctly
  on a 2 qubit case before scaling.

## 3. Transpilation & resource estimation
- Compile to the target basis gate set; report CNOT count and depth.
- Estimate shots needed for the desired error bar (binomial/quantum shot noise).
- **DoD**: printed circuit layout + estimated runtime + shot budget.

## 4. Execution plan
- Choose simulator (exact statevector for validation) vs sampling; or real backend.
- Specify shot budget and any error mitigation to apply.
- **DoD**: a `run_experiment(config)` that dispatches to the chosen backend and
  returns raw samples/expectations.

## 5. Measurement & post-processing
- Observables and readout; calibration (measurement-error matrix) if applicable.
- Unbiasing / discarding / coincidence counting as needed.
- **DoD**: processed observable values + readout-corrected counts.

## 6. Analysis & statistics
- Error bars / confidence intervals; hypothesis test; compare to classical baseline.
- **DoD**: a plot/table + a verdict (PASS/FAIL vs the confirmation condition).

## 7. Reproducibility & packaging
- Fixed seeds, pinned SDK versions, saved raw data + config + notebook + report.
- **DoD**: one command re-runs the whole experiment (`qntelli-run` or a Makefile target).

## Definition of done (cross-cutting)
- [ ] Runs end-to-end in one command
- [ ] Seeds pinned; deterministic
- [ ] Correctness cross-checked against an analytic reference (see `qntelli_validate.py`)
- [ ] Raw data + config committed next to the report
