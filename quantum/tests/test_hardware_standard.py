#!/usr/bin/env python3
"""
Tests for the qntelli MODEL HARDWARE STANDARD (quantum/hardware/standard.py).

The standard is the ion-trap device access layer: a vendor-neutral contract
(device catalog, native gate families, honest execution tiers, job ledger)
for reaching IonQ / Quantinuum / AQT trapped-ion systems.

All tests are OFFLINE (no credentials, no network) and verify genuine physics
through the vendor compilers — never stubs:

  HW-1  device catalog: profiles complete, native gates real, all-to-all
  HW-2  capability check: emulator honest, QPU honestly locked w/o credentials
  HW-3  native compilation: Bell rebases to all four ion-trap gate families
        with EXACT analytic probabilities (0.5/0.5) via unitary sampling
  HW-4  Quantinuum emulator end-to-end: vendor compile + validity predicate +
        pecos sampling — Bell 00/11 ~ 1.0 correlation
  HW-5  Quantinuum emulator Grover |101>: top == 101, peak ~0.78 (0.08 tol)
  HW-6  IonQ emulator (forte + aria families): Bell/Grover correct on
        gpi/gpi2/{zz,ms} native gates
  HW-7  AQT emulator: Bell through vendor offline sim (r/rz/rxx natives)
  HW-8  honest tier ladder: unknown device raises; qpu without credentials
        raises PermissionError; simulation fallback works and is LABELLED
  HW-9  job ledger: records appended with device/tier/counts hash, honest
        status, and never breaks execution on write failure
  HW-10 orchestrator integration: hardware bind + execute skills fire in the
        bell chain and complete autonomously (validated by state log events)

Run:  python3 quantum/tests/test_hardware_standard.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

QUANTUM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(QUANTUM))
sys.path.insert(0, str(QUANTUM / "hardware"))

import standard as hw  # noqa: E402

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


def bell():
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(2, 2)
    qc.h(0); qc.cx(0, 1); qc.measure([0, 1], [0, 1])
    return qc


def grover101():
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(3, 3)
    qc.h(range(3))
    qc.x(1); qc.h(2); qc.ccx(0, 1, 2); qc.h(2); qc.x(1)
    qc.h(range(3)); qc.x(range(3)); qc.h(2); qc.ccx(0, 1, 2); qc.h(2); qc.x(range(3)); qc.h(range(3))
    qc.measure(range(3), range(3))
    return qc


def probs_from_counts(counts):
    tot = sum(counts.values()) or 1
    return {k: v / tot for k, v in counts.items()}


def test_catalog():
    print("HW-1 device catalog: complete ion-trap profiles")
    devs = {d["device_id"]: d for d in hw.list_devices()}
    check(">=4 devices", len(devs) >= 4, ", ".join(devs))
    for expected in ("ionq:forte", "ionq:aria", "quantinuum:h2-1", "quantinuum:h2-1e", "aqt:pine"):
        check(f"catalog has {expected}", expected in devs)
    for did, d in devs.items():
        gates = d["native_gates"]
        known = ({"gpi", "gpi2", "zz"} <= set(gates) or
                 {"gpi", "gpi2", "ms"} <= set(gates) or
                 {"phasedx", "zzphase"} <= set(gates) or
                 {"r", "rxx"} <= set(gates))
        check(f"{did} natives are ion-trap real", known, str(gates))
        check(f"{did} all-to-all coupling", d["coupling"] == "all-to-all")
        check(f"{did} declares tiers", len(d["tiers"]) >= 1)


def test_capability():
    print("HW-2 capability: emulator available, QPU honestly locked offline")
    for vendor, cls in hw.ADAPTERS.items():
        cap = cls().capability()
        check(f"{vendor} emulator capability declared", isinstance(cap["emulator"], bool))
        check(f"{vendor} qpu locked w/o creds", not cap["qpu"], cap["qpu_detail"][:60])


def test_native_compile():
    print("HW-3 native compilation: exact Bell physics on all gate families")
    from pytket.circuit import OpType
    cases = [
        ("ionq_forte", hw.GateFamily.IONQ_FORTE),
        ("ionq_aria", hw.GateFamily.IONQ_ARIA),
        ("quantinuum", hw.GateFamily.QUANTINUUM),
        ("aqt", hw.GateFamily.AQT),
    ]
    for fam_name, fam in cases:
        dev = hw.IonTrapDevice(
            device_id=f"test:{fam_name}", vendor="test", model="t",
            gate_family=fam, num_qubits=2, max_shots=1000,
            tiers=[hw.ExecutionTier.EMULATOR], credentials_env=[])
        tk = hw.compile_to_native(bell(), dev)
        ops = {cmd.op.type for cmd in tk}
        allowed = {
            hw.GateFamily.IONQ_FORTE: {OpType.GPI, OpType.GPI2, OpType.ZZPhase, OpType.Measure},
            hw.GateFamily.IONQ_ARIA: {OpType.GPI, OpType.GPI2, OpType.XXPhase, OpType.Measure},
            hw.GateFamily.QUANTINUUM: {OpType.PhasedX, OpType.Rz, OpType.ZZPhase, OpType.Measure},
            hw.GateFamily.AQT: {OpType.PhasedX, OpType.Rz, OpType.ZZPhase, OpType.Measure},
        }[fam]
        check(f"{fam_name}: ops subset of native set", ops <= allowed,
              str(sorted(o.name for o in ops)))
        probs = hw._tket_probs(tk)
        ok = abs(probs.get("00", 0) - 0.5) < 1e-9 and abs(probs.get("11", 0) - 0.5) < 1e-9
        check(f"{fam_name}: unitary probs exactly 0.5/0.5", ok,
              f"00={probs.get('00'):.4f} 11={probs.get('11'):.4f}")


def test_quantinuum_emulator():
    print("HW-4 Quantinuum emulator: vendor compile + pecos physics (Bell)")
    cap = hw.QuantinuumAdapter().capability()
    if not cap["emulator"]:
        print("  [SKIP] pecos not installed")
        return
    rec = hw.submit_job(bell(), "quantinuum:h2-1e", shots=2000, algorithm="bell")
    check("status complete", rec.status == "complete", rec.detail[:80])
    check("tier labelled emulator", rec.tier == "emulator")
    p = probs_from_counts(rec.counts)
    corr = p.get("00", 0) + p.get("11", 0)
    check("Bell correlation ~1.0", abs(corr - 1.0) < 0.02, f"corr={corr:.4f}")


def test_quantinuum_grover():
    print("HW-5 Quantinuum emulator Grover |101> vs analytic 0.78")
    cap = hw.QuantinuumAdapter().capability()
    if not cap["emulator"]:
        print("  [SKIP] pecos not installed")
        return
    rec = hw.submit_job(grover101(), "quantinuum:h2-1e", shots=4000, algorithm="grover")
    check("status complete", rec.status == "complete", rec.detail[:80])
    p = probs_from_counts(rec.counts)
    top = max(p, key=p.get)
    check("top state is |101>", top == "101", f"top={top} peak={p[top]:.3f}")
    check("peak within tol of 0.78", abs(p["101"] - 0.78) < 0.08, f"peak={p['101']:.3f}")


def test_ionq_emulator():
    print("HW-6 IonQ emulator: gpi/gpi2/{zz,ms} families")
    for did in ("ionq:forte", "ionq:aria"):
        rec = hw.submit_job(bell(), did, shots=2000, algorithm="bell")
        check(f"{did} bell complete", rec.status == "complete", rec.detail[:60])
        p = probs_from_counts(rec.counts)
        ok = abs(p.get("00", 0) - 0.5) < 0.05 and abs(p.get("11", 0) - 0.5) < 0.05
        check(f"{did} bell 0.5/0.5", ok)
        rec2 = hw.submit_job(grover101(), did, shots=4000, algorithm="grover")
        p2 = probs_from_counts(rec2.counts)
        top2 = max(p2, key=p2.get)
        check(f"{did} grover top=101", top2 == "101", f"peak={p2[top2]:.3f}")


def test_aqt_emulator():
    print("HW-7 AQT emulator: vendor offline sim (r/rz/rxx)")
    cap = hw.AQTAdapter().capability()
    if not cap["emulator"]:
        print("  [SKIP] qiskit-aqt-provider not installed")
        return
    rec = hw.submit_job(bell(), "aqt:pine", shots=1000, algorithm="bell")
    check("status complete", rec.status == "complete", rec.detail[:80])
    p = probs_from_counts(rec.counts)
    ok = abs(p.get("00", 0) - 0.5) < 0.05 and abs(p.get("11", 0) - 0.5) < 0.05
    check("bell 0.5/0.5", ok, str({k: round(v, 3) for k, v in p.items()}))


def test_tier_ladder():
    print("HW-8 honest tier ladder")
    try:
        hw.get_device("nope:x")
        check("unknown device raises", False)
    except KeyError:
        check("unknown device raises", True)
    # qpu without credentials must refuse (never silently emulate)
    try:
        hw.submit_job(bell(), "quantinuum:h2-1", allow_qpu=True)
        check("qpu w/o creds raises PermissionError", False)
    except PermissionError:
        check("qpu w/o creds raises PermissionError", True)
    # a simulation-only device is labelled simulation
    dev = hw.IonTrapDevice(
        device_id="test:simonly", vendor="test", model="t",
        gate_family=hw.GateFamily.GENERIC, num_qubits=2, max_shots=1000,
        tiers=[hw.ExecutionTier.SIMULATION], credentials_env=[])
    hw._CATALOG.append(dev)
    try:
        rec = hw.submit_job(bell(), "test:simonly", shots=100, algorithm="bell")
        check("simulation fallback labelled", rec.tier == "simulation" and rec.status == "complete",
              f"tier={rec.tier} status={rec.status}")
    finally:
        hw._CATALOG.pop()


def test_ledger():
    print("HW-9 job ledger: append-only records with counts hash")
    ledger = Path(hw.JOBS_LOG)
    before = len(ledger.read_text().splitlines()) if ledger.exists() else 0
    hw.submit_job(bell(), "quantinuum:h2-1e", shots=200, algorithm="bell")
    after_lines = ledger.read_text().splitlines() if ledger.exists() else []
    check("ledger grew by >=1", len(after_lines) >= before + 1)
    rec = json.loads(after_lines[-1])
    for key in ("job_id", "device_id", "tier", "algorithm", "shots", "status", "counts_hash"):
        check(f"record has {key}", key in rec, str(rec.get(key))[:40])
    check("tier is emulator (honest labelling)", rec.get("tier") == "emulator")


def test_orchestrator_integration():
    print("HW-10 orchestrator integration: hardware skills fire autonomously")
    sys.path.insert(0, str(QUANTUM / "orchestrator"))
    import importlib
    import orchestrator as orch
    importlib.reload(orch)
    o = orch.MultiAgentOrchestrator("bell", real=True)
    o.run_with_feedback()
    events = [r["event"] for r in o.state_log]
    check("hardware_bound event logged", "hardware_bound" in events)
    check("hw_job event logged", "hw_job" in events)
    check("experiment completes autonomously", o.status["complete"])
    hw_events = [r for r in o.state_log if r["event"] == "hw_job"]
    if hw_events:
        payload = hw_events[0]["payload"]
        check("hw job complete + emulator tier",
              payload["status"] == "complete" and payload["tier"] == "emulator",
              f"tier={payload['tier']} status={payload['status']}")


def main():
    print("=== qntelli HARDWARE STANDARD test suite (offline) ===")
    test_catalog()
    test_capability()
    test_native_compile()
    test_quantinuum_emulator()
    test_quantinuum_grover()
    test_ionq_emulator()
    test_aqt_emulator()
    test_tier_ladder()
    test_ledger()
    test_orchestrator_integration()
    print(f"=== hardware-standard: {PASS} PASS / {FAIL} FAIL ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
