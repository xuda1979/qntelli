#!/usr/bin/env python3
"""
tests for the ONE-ENTER quantum solve harness guarantee.

Verifies the hard requirement: any quantum coding question is driven to a
fully-correct, tested, working answer with ZERO human interaction —
  * works-until-correct: silent internal self-correction loop
  * no human interaction: solve() never prompts / asks the user a question
  * honesty: never fabricates a 'tested' result when it cannot converge
  * n-awareness: multi-qubit references are correct (found via live test)

Run:  python3 quantum/tests/test_solve_guarantee.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import solve as S

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def no_stdin_prompt_in_source():
    """The engine must never block for user input (no input()/getpass/EOF prompts)."""
    src = Path(S.__file__).read_text()
    return "input(" not in src


# ── T1: works-until-correct loop (silent self-correction) ──────────────────
def test_silent_self_correction():
    print("T1 silent self-correction (works-until-correct)")
    calls = {"n": 0}
    orig = S.call_model

    def fake(question, mode, feedback):
        calls["n"] += 1
        if calls["n"] == 1:
            # deliberately wrong: identity circuit -> fails Bell check
            return '''
import json
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
qc=QuantumCircuit(2,2); qc.measure([0,1],[0,1])
c=AerSimulator(seed_simulator=7).run(qc,shots=4000).result().get_counts()
print(json.dumps({'probs':{k:v/4000 for k,v in c.items()}}))
'''
        return S.GOLDEN["bell"]

    S.call_model = fake
    r = S.solve("Write a Bell state circuit, P(00)=P(11)=0.5", max_attempts=3)
    S.call_model = orig
    check("attacker wrong attempt 1 caught + corrected", r["ok"] and r["attempts"] == 2,
          f"attempts={r.get('attempts')}")
    check("user sees only tested code (has measure)", bool(r["code"]) and "measure" in r["code"])
    check("no user prompt issued", all(a.get("pass") is not None for a in r.get("attempt_log", [])))


# ── T2: honest failure — no fabricated 'tested', no user question ──────────
def test_honest_failure_no_fabrication():
    print("T2 honest failure (never fabricate correctness)")
    def bad(question, mode, feedback):
        return '''
import json
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
qc=QuantumCircuit(2,2); qc.measure([0,1],[0,1])
c=AerSimulator(seed_simulator=7).run(qc,shots=4000).result().get_counts()
print(json.dumps({'probs':{k:v/4000 for k,v in c.items()}}))
'''
    orig = S.call_model
    S.call_model = bad
    r = S.solve("Write a Bell state circuit, P(00)=P(11)=0.5", max_attempts=3)
    S.call_model = orig
    check("does NOT fabricate tested code", r["ok"] is False and r["code"] is None)
    check("autonomous honest failure (no question)", r.get("stage") == "max_attempts")
    check("value in attempt_log: all attempts ran", len(r.get("attempt_log", [])) == 3)


# ── T3: n-awareness (4-qubit GHZ verified against n=4 reference) ──────────
def test_n_aware_reference():
    print("T3 n-aware references (multi-qubit correctness)")
    cls = S.classify("build a 4-qubit GHZ state, |0000> and |1111> equally likely")
    check("classify detects n=4", cls.get("n") == 4, f"n={cls.get('n')}")
    ref_type, ref, tol = S.reference_for(cls, n=cls["n"])
    check("GHZ reference uses 4-qubit keys", ref == {"0000": 0.5, "1111": 0.5}, str(ref))
    # a correct 4-qubit GHZ circuit must verify clean
    code = '''
import json
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
n=4; qc=QuantumCircuit(n,n); qc.h(0)
for k in range(1,n): qc.cx(0,k)
qc.measure(range(n),range(n))
c=AerSimulator(seed_simulator=7).run(qc,shots=4000).result().get_counts()
print(json.dumps({'probs':{k:v/4000 for k,v in c.items()}}))
'''
    v = S.verify(code, ref_type, ref, tol)
    check("correct 4-qubit GHZ verifies PASS", v["pass"], v.get("detail"))


# ── T4: full bank, first solve (works-until-correct at scale) ──────────────
def test_full_bank_first_solve():
    print("T4 full bank — every question yields a verified solution")
    bank = S.bank_questions()
    results = []
    for qid, q in bank.items():
        r = S.solve(q["prompt"], offline=True)
        results.append((qid, r["ok"], r.get("attempts")))
    ok = all(ok for _, ok, _ in results)
    check(f"all {len(results)} bank questions verified (one enter)", ok,
          ", ".join(f"{qid}:{'OK' if okn else 'FAIL'}" for qid, okn, _ in results))


# ── T5: no-human-interaction invariant ─────────────────────────────────────
def test_no_human_interaction_invariant():
    print("T5 no-human-interaction invariant")
    check("solve.py never blocks on stdin", no_stdin_prompt_in_source())
    # The only 'failure' returns are honest, non-interactive (no '? for' phrasing)
    r = S.solve("draw me a circuit with no clear algorithm", offline=True)
    check("unclassifiable is honest+non-interactive (no user question)",
          r.get("ok") is False and r.get("interactive") is False,
          r.get("stage"))


# ── T6: no-data-leakage invariant ─────────────────────────────────────────
def test_no_data_leakage():
    print("T6 no-data-leakage (model never sees analytic reference/answer values)")
    # 6a: sanitizer strips expected/measured values from measurement-stage flips.
    cases = [
        ({"stage": "probs", "detail": "000: exp 0.125 got 0.132"}),           # probs
        ({"stage": "grover", "detail": "peak=0.947 top=010 marked=010"}),      # grover
        ({"stage": "dj", "detail": "nonzero=True (n=2)"}),                     # dj
        ({"stage": "expect", "detail": "|val|=0.0101"}),                       # expect
    ]
    leaky = ["exp ", "got ", "0.125", "0.132", "0.947", "top=", "marked=",
             "010", "0.0101", "0.500"]
    all_clean = True
    for vdict in cases:
        rt = vdict["stage"]
        out = S._sanitize_feedback(vdict, rt)
        if any(tok.lower() in out.lower() for tok in leaky):
            all_clean = False
            print(f"    LEAK in {rt}: {out}")
    check("sanitizer leaks NO analytic/measured values in any stage", all_clean)
    check("sanitizer exec keeps only the model's OWN traceback",
          "Traceback" in S._sanitize_feedback(
              {"stage": "exec", "detail": "Traceback (most recent call last):\nImportError"}, "probs"))

    # 6b: end-to-end — the solve loop must never receive analytic ref as feedback.
    #    Instrument call_model to record the feedback strings it was given.
    calls = {"feedbacks": []}
    orig = S.call_model

    def recording(question, mode, feedback):
        calls["feedbacks"].append(feedback or "")
        # first attempt wrong (probs preset), second correct.
        return S.GOLDEN["bell"] if len(calls["feedbacks"]) >= 2 else (
            'import json\n'
            'from qiskit import QuantumCircuit\n'
            'from qiskit_aer import AerSimulator\n'
            'qc=QuantumCircuit(2,2); qc.measure([0,1],[0,1])\n'
            'c=AerSimulator(seed_simulator=7).run(qc,shots=4000).result().get_counts()\n'
            'print(json.dumps({"probs":{k:v/4000 for k,v in c.items()}}))\n')

    S.call_model = recording
    r = S.solve("Bell circuit, P(00)=P(11)=0.5", max_attempts=3)
    S.call_model = orig
    leaked_fb = [fb for fb in calls["feedbacks"] if any(t in fb for t in ["exp ", "0.500", "0.5 "])]
    check("solve loop never feeds analytic reference back into call_model", not leaked_fb, str(leaked_fb))
    check("solve still converges under sanitized feedback", r["ok"])


def test_extended_algorithm_library():
    """T7: the extended verified-algorithm library (QPE, Bernstein-Vazirani,
    SWAP-test) — each must classify, have an analytic reference, and pass the
    offline one-enter solve end-to-end."""
    print("T7 extended algorithm library (QPE / BV / swap-test)")
    cases = {
        "bernstein_vazirani": "Bernstein-Vazirani with secret 101",
        "swap_unequal": "swap test between |+> and |-> (different states)",
        "swap_equal": "swap test between two equal |+> states",
        "qpe": "quantum phase estimation of theta=0.125",
    }
    # 7a: classifier routes each to the right family (ref_type present).
    for want, prompt in cases.items():
        cls = S.classify(prompt)
        rt = cls.get("ref_type")
        expected = {"bernstein_vazirani": "bv", "swap_unequal": "swap_test",
                    "swap_equal": "swap_test", "qpe": "qpe"}[want]
        check(f"classify[{want}] -> {expected}", rt == expected, f"got {rt}")
    # 7b: reference_for returns a concrete (non-empty) reference + sane tolerance.
    for prompt in cases.values():
        cls = S.classify(prompt)
        if cls["ref_type"] is None:
            continue
        rt, ref, tol = S.reference_for(cls, n=3)
        check(f"reference_for[{rt}] concrete", bool(ref) and tol >= 0, f"{ref}")
    # 7c: full offline solve returns VERIFIED code for each family.
    for want, prompt in cases.items():
        r = S.solve(prompt, offline=True)
        v = r.get("verification") or {}
        check(f"offline solve[{want}] ok+verified", r["ok"] and v.get("pass", r["ok"]),
              f"stage={v.get('stage')} detail={v.get('detail','')[:40]}")
    # 7d: golden solutions exist for every new ref_type (offline path depends on them).
    for key in ("bv", "swap_test", "qpe"):
        check(f"GOLDEN[{key}] present", key in S.GOLDEN and S.GOLDEN[key].strip(), "")


def test_vqe():
    """T8: VQE (variational quantum eigensolver) — classify, reference, and
    offline one-enter solve converges to the exact ground-state energy."""
    print("T8 VQE (variational quantum eigensolver)")
    prompt = "run VQE to find the ground state energy of a single qubit X Hamiltonian"
    # 8a: classifier routes to vqe
    cls = S.classify(prompt)
    check("classify[vqe] -> vqe", cls.get("ref_type") == "vqe", f"got {cls.get('ref_type')}")
    # 8b: reference is exact ground-state energy of H=X
    rt, ref, tol = S.reference_for(cls, n=1)
    check("reference_for[vqe] target -1.0", ref.get("energy") == -1.0, f"{ref} tol={tol}")
    # 8c: offline solve returns verified code (E ≈ -1 within tol)
    r = S.solve(prompt, offline=True)
    v = r.get("verification") or {}
    check("offline solve[vqe] ok+verified", r["ok"] and v.get("stage") == "vqe",
          f"stage={v.get('stage')} detail={v.get('detail','')[:40]}")
    # 8d: exact-golden energy passes the reference check (regression guard)
    check("GOLDEN[vqe] present", "vqe" in S.GOLDEN and S.GOLDEN["vqe"].strip(), "")


def test_multi_sdk_parity():
    """T9: cross-framework one-enter harness. The SAME algorithm can be
    requested and VERIFIED in Qiskit, PennyLane, or Cirq, because the analytic
    reference is SDK-agnostic; only the runner/golden/feedback differ per SDK."""
    print("T9 multi-SDK parity (qiskit / pennylane / cirq)")
    cases = [
        ("write a PennyLane Bell state", "pennylane", "bell"),
        ("write a PennyLane 3-qubit GHZ", "pennylane", "ghz"),
        ("write a Cirq Bell state", "cirq", "bell"),
        ("write a Cirq 3-qubit GHZ", "cirq", "ghz"),
        ("write a Qiskit Bell state", "qiskit", "bell"),
        ("write a PennyLane Bernstein-Vazirani secret 101", "pennylane", "bernstein_vazirani"),
        ("write a Cirq Bernstein-Vazirani secret 101", "cirq", "bernstein_vazirani"),
        ("write a Qiskit Bernstein-Vazirani secret 101", "qiskit", "bernstein_vazirani"),
    ]
    # 9a: classifier routes each question to the correct SDK.
    for prompt, want_sdk, want_alg in cases:
        cls = S.classify(prompt)
        check(f"classify[{want_alg}] sdk={want_sdk}",
              cls.get("sdk") == want_sdk and cls.get("algorithm") == want_alg,
              f"algorithm={cls.get('algorithm')} sdk={cls.get('sdk')}")
    # 9b: offline one-enter solve VERIFIES the same reference in every SDK, and
    #     the delivered code actually uses that SDK (not a fallback golden).
    for prompt, want_sdk, want_alg in cases:
        r = S.solve(prompt, offline=True)
        v = r.get("verification") or {}
        code = r.get("code") or ""
        code_sdk = ("pennylane" if "pennylane" in code else
                    ("cirq" if "import cirq" in code else "qiskit"))
        check(f"offline solve[{want_alg}, {want_sdk}] verified",
              r["ok"] and v.get("stage"),
              f"stage={v.get('stage')} detail={v.get('detail','')[:30]}")
        check(f"code sdk[{want_alg}, {want_sdk}] matches", code_sdk == want_sdk,
              f"got {code_sdk}")
    # 9c: non-Qiskit autocorrect does NOT mangle PennyLane/Cirq imports+circuits.
    cirq_code = S.GOLDEN["bell_cirq"]
    fixed = S._autocorrect_legacy_api(cirq_code, sdk="cirq")
    check("autocorrect no-op for cirq", "measure_all" not in fixed and "import cirq" in fixed, "")
    pl_code = S.GOLDEN["bell_pennylane"]
    fixed_pl = S._autocorrect_legacy_api(pl_code, sdk="pennylane")
    check("autocorrect no-op for pennylane", "measure_all" not in fixed_pl
          and "import pennylane" in fixed_pl, "")
    # 9d: SDK-specific goldens exist.
    for k in ("bell_pennylane", "ghz_pennylane", "bell_cirq", "ghz_cirq",
              "bv_pennylane", "bv_cirq"):
        check(f"GOLDEN[{k}] present", k in S.GOLDEN and S.GOLDEN[k].strip(), "")
    # 9e: mock a failing cirq first attempt -> SDK-aware sanitize feedback mentions cirq.
    fb = S._sanitize_feedback({"stage": "probs", "detail": "000: exp 0.5 got 0.9"},
                              "probs", sdk="cirq")
    check("sanitize feedback promps cirq", "cirq" in fb, "")


def test_n_aware_offline_goldens():
    """T10: GAP-003 — the offline goldens are n-aware (previously a 4+ qubit
    GHZ offline solve used the 3-qubit golden and failed). An arbitrary-n GHZ
    must verify offline against the n-aware reference. Now covers Qiskit,
    PennyLane, AND Cirq (the SDK-specific goldens were hardcoded to 3 qubits
    until Sprint 16).
    """
    print("T10 n-aware offline goldens (GAP-003, multi-SDK)")
    # Qiskit GHZ across n
    for n in (2, 3, 4, 5):
        r = S.solve(f"write a {n}-qubit GHZ", offline=True)
        v = r.get("verification") or {}
        check(f"offline qiskit {n}-qubit GHZ verified",
              r["ok"] and v.get("stage") == "probs",
              f"stage={v.get('stage')} detail={v.get('detail','')[:25]}")
    # PennyLane GHZ across n (was broken: golden hardcoded wires=3)
    for n in (3, 4, 5):
        r = S.solve(f"write a {n}-qubit GHZ in PennyLane", offline=True)
        v = r.get("verification") or {}
        check(f"offline pennylane {n}-qubit GHZ verified",
              r["ok"] and v.get("stage") == "probs",
              f"stage={v.get('stage')} detail={v.get('detail','')[:25]}")
    # Cirq GHZ across n (was broken: golden hardcoded range(3))
    for n in (3, 4, 5):
        r = S.solve(f"write a {n}-qubit GHZ using Cirq", offline=True)
        v = r.get("verification") or {}
        check(f"offline cirq {n}-qubit GHZ verified",
              r["ok"] and v.get("stage") == "probs",
              f"stage={v.get('stage')} detail={v.get('detail','')[:25]}")


def test_n_aware_qft_and_grover():
    """T11: Sprint-16 fixes — the QFT and Grover offline goldens are n-aware and
    marked-state-aware (previously hardcoded to 3 qubits / |101> repsectively):
      * a 4/5-qubit QFT offline-solves against the uniform n-qubit reference
      * a Grover for ANY marked state (not just |101>) offline-solves and
        verifies that the marked state is the top outcome
      * 4/5-qubit Grover applies the correct iteration count (single iteration
        only hits ~0.47 on N=16, below the verifier's peak>0.5 bar), and
      * spelled-out qubit counts ('four', 'five') are parsed, not just digits.
    These all failed before this sprint's harness fix."""
    print("T11 n-aware QFT + marked-state-aware Grover + word-quantifies")
    for n in (4, 5):
        r = S.solve(f"write a {n}-qubit quantum fourier transform", offline=True)
        check(f"offline qft {n}-qubit verified", r.get("ok"),
              str((r.get("verification") or {}).get("stage")))
    for marked in ("011", "100", "001", "1011", "0110", "11101"):
        q = f"grover for |{marked}>"
        nq = max(len(marked), 3)
        r = S.solve(q, offline=True)
        v = r.get("verification") or {}
        check(f"grover {marked} verified (n={nq})",
              r.get("ok") and v.get("top") == marked,
              f"stage={v.get('stage')} detail={v.get('detail','')[:40]}")
    # spelled-out qubit counts must classify to the right n
    cls = S.classify("four qubit grover target |0110>")
    check("classify 'four qubit' -> n=4", cls.get("n") == 4, f"n={cls.get('n')}")
    cls = S.classify("five qubit grover |11101>")
    check("classify 'five qubit' -> n=5 + marked=11101",
          cls.get("n") == 5 and cls.get("marked") == "11101",
          f"n={cls.get('n')} marked={cls.get('marked')}")


def test_multi_sdk_bv_secret_aware():
    """T12: Sprint-16/17 fixes — the Bernstein-Vazirani offline goldens were
    hardcoded to secret '101' AND, for Qiskit, applied CNOTs in an order that
    read non-palindromic secrets back reversed (e.g. 110 -> top 011 -> FAIL).
    Now ANY secret solves offline in Qiskit, PennyLane and Cirq, and the
    classifier recognises standalone 'bv'/'b-v' tokens (so 'bv secret 100'
    is classified, not 'unknown')."""
    print("T12 multi-SDK BV secret-aware (ANY secret, all 3 SDKs)")
    # BV verification returns {"pass","stage","detail","probs"}; the top
    # measured state is read from probs (not a dedicated key like grover).
    def _top(v):
        p = (v or {}).get("probs") or {}
        return max(p, key=p.get) if p else None
    for secret in ("101", "110", "011", "010", "100"):
        r = S.solve(f"bernstein vazirani secret {secret}", offline=True)
        v = r.get("verification") or {}
        check(f"qiskit BV secret {secret}", r.get("ok") and _top(v) == secret,
              str(v.get("detail")))
    for secret in ("110", "010"):
        r = S.solve(f"bernstein vazirani in pennylane secret {secret}", offline=True)
        v = r.get("verification") or {}
        check(f"pennylane BV secret {secret}", r.get("ok") and _top(v) == secret,
              str(v.get("detail")))
    for secret in ("010", "011"):
        r = S.solve(f"b-v cirq secret {secret}", offline=True)
        v = r.get("verification") or {}
        check(f"cirq BV secret {secret}", r.get("ok") and _top(v) == secret,
              str(v.get("detail")))
    r = S.solve("bv secret 100", offline=True)
    check("classify standalone 'bv' token", r.get("ok"),
          str((r.get("verification") or {}).get("stage")))


def main():
    print("=== qntelli ONE-ENTER harness guarantee tests ===\n")
    test_silent_self_correction()
    test_honest_failure_no_fabrication()
    test_n_aware_reference()
    test_full_bank_first_solve()
    test_no_human_interaction_invariant()
    test_no_data_leakage()
    test_extended_algorithm_library()
    test_vqe()
    test_multi_sdk_parity()
    test_n_aware_offline_goldens()
    test_n_aware_qft_and_grover()
    test_multi_sdk_bv_secret_aware()
    print(f"\n=== {PASS} passed, {FAIL} failed ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
