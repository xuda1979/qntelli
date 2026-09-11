# qntelli — Canonical Quantum Building Blocks (one-time-pass reference)

Use these verified building blocks to maximise first-attempt correctness.
They are pedagogically canonical and sim-safe. For each, the exact gate
sequence is given so the agent can reproduce it without guessing.

## 1. Bell state  |Φ+> = (|00>+|11>)/√2  (Qiskit)
```python
from qiskit import QuantumCircuit
qc = QuantumCircuit(2, 2)
qc.h(0)
qc.cx(0, 1)        # controlled-NOT, control=0 target=1
qc.measure([0, 1], [0, 1])
# Sampler: counts ~ {00: .5, 11: .5}
```

## 2. GHZ state (n qubits)  (Qiskit)
```python
from qiskit import QuantumCircuit
n = 3
qc = QuantumCircuit(n, n)
qc.h(0)
for k in range(1, n):
    qc.cx(0, k)           # ladder of CNOTs from qubit 0
qc.measure(range(n), range(n))
# Sampler: counts ~ {000...0: .5, 111...1: .5}
```

## 3. Deutsch–Jozsa (balanced/constant oracle)
- n+1 qubits: n query qubits all in |+>, 1 ancilla in |->.
- Oracle: balanced -> CNOT from each query qubit to ancilla (or CX(x_i, ancilla))
  measuring parity; constant -> identity (or X on ancilla).
```python
from qiskit import QuantumCircuit
n = 2
qc = QuantumCircuit(n + 1, n)
qc.h(range(n)); qc.x(n); qc.h(n)          # |+...>|-> ancilla
# balanced oracle: mark parity of query bits onto ancilla
for i in range(n):
    qc.cx(i, n)                             # oracle for balanced
qc.h(range(n))
qc.measure(range(n), range(n))
# balanced -> P(00)=1 ; constant -> P(00)=1 (with identity oracle)
```

## 4. Quantum Fourier Transform (n qubits)  (Qiskit)
```python
import numpy as np
from qiskit import QuantumCircuit
def qft(n):
    qc = QuantumCircuit(n)
    for j in range(n):
        qc.h(j)
        for k in range(j + 1, n):
            qc.cp(np.pi / 2 ** (k - j), k, j)   # phase 2π/2^(k-j), control=k target=j
    for j in range(n // 2):                     # reverse qubit order
        qc.swap(j, n - 1 - j)
    return qc
```

## 5. Grover (1 marked state, n qubits)
```python
import numpy as np
from qiskit import QuantumCircuit
n, marked = 3, 5            # mark |101>
qc = QuantumCircuit(n, n)
qc.h(range(n))
# Oracle: flip phase of |marked> via multi-controlled Z (X basis trick)
qc.x([i for i in range(n) if not ((marked >> i) & 1)])
qc.h(n - 1); qc.mcx(list(range(n - 1)), n - 1); qc.h(n - 1)
qc.x([i for i in range(n) if not ((marked >> i) & 1)])
# Diffusion
qc.h(range(n)); qc.x(range(n)); qc.h(n - 1)
qc.mcx(list(range(n - 1)), n - 1); qc.h(n - 1)
qc.x(range(n)); qc.h(range(n))
qc.measure(range(n), range(n))
# one iteration amplifies |marked>: P ~ (sin(3θ))^2, θ = asin(1/√8)
```

## 6. Expectation values (Qiskit EstimatorV2)
```python
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp
from qiskit_aer.primitives import EstimatorV2   # or SamplerV2
qc = QuantumCircuit(1)
qc.h(0)                                        # |+>
op = SparsePauliOp(["Z"])                       # <+|Z|+> = 0
est = EstimatorV2()
print(est.run([(qc, [op])]).result()[0].data.evs)   # ~ 0
```

## 7. PennyLane QNode (expectation + samples)
```python
import pennylane as qml
from pennylane import numpy as np
dev = qml.device("default.qubit", wires=2, shots=4000)
@qml.qnode(dev)
def circuit():
    qml.Hadamard(0)
    qml.CNOT(wires=[0, 1])
    return qml.sample(qml.PauliZ(0))
samples = circuit().numpy()
```

## 8. Cirq Bell circuit
```python
import cirq
q0, q1 = cirq.LineQubit.range(2)
circuit = cirq.Circuit(
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, q1, key='m'),
)
sim = cirq.Simulator()
result = sim.run(circuit, repetitions=4000)   # counts ~ {00:.5, 11:.5}
```

## Cross-SDK correctness checks (for qntelli_validate.py)
- Bell/GHZ: measure P(00)=P(11)=0.5 on simulator.
- QFT(|0>): uniform |amplitude| = 1/√(2^n); verify with Statevector.
- Grover(1 marked of N=8): one iteration -> P ≈ sin²(3·asin(1/√8)) ≈ 0.781.
- Deutsch–Jozsa balanced n=2: measure 00 with P=1.
