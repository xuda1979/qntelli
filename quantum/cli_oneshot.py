#!/usr/bin/env python3
"""
qntelli one-shot binary entrypoint.

When given a quantum-coding question, drives the harness (generate -> verify by
running -> silently self-correct) until it has a VERIFIED, working solution, and
prints ONLY that correct code on stdout. Nothing else. On genuine failure exits
non-zero with the reason on stderr (never fabricates, never prints broken code).

Usage:
  qntellisolve "write a 3-qubit GHZ circuit ..."
  echo "write a Bell circuit ..." | qntellisolve
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import solve as S


_BANNER = r"""
qntelli ▸ an intelligent agent for quantum-computing science & technology
          works like codex / claude-code: ask a question, get VERIFIED code,
          then keep the conversation going with follow-ups.
"""

_HELP = """\
Commands:
  <question>       ask a quantum-coding question (Bell/GHZ/DJ/QFT/Grover/...)
                   — you get only harness-VERIFIED, runnable code
  !last            print the code from the most recent successful answer
  !clear           reset the conversation context (forget prior turns)
  !count           show how many questions were solved this session
  !help            show this help
  quit / exit      leave the session
Anything else is treated as a follow-up question and solved with the prior
turns as context (e.g. "now make it 4 qubits", "convert to PennyLane").
"""


def _solve_print(question: str, *, max_attempts: int, test_file: str | None,
                 history: list | None = None) -> tuple[bool, dict] | None:
    """Solve one question and print ONLY verified code to stdout. Returns
    (ok, result) or None if no question was given (caller loop should exit)."""
    # Keep stdout 100% code so it can be piped; all chatter goes to stderr.
    print("Working …", file=sys.stderr, end="", flush=True)
    try:
        if test_file:
            harness = Path(test_file).read_text()
            r = S.solve_with_test(question, harness, max_attempts=max_attempts)
        else:
            # Fall back to the offline golden path when no model endpoint is
            # configured, exactly like solve.py --question. This keeps the
            # one-shot / REPL entry points consistent with the solver CLI:
            # a supported-family question (Bell/GHZ/QFT/DJ/Grover/expect/BV/
            # swap/QPE/VQE) still returns its VERIFIED golden code offline
            # instead of a bare "no-endpoint" error, while general questions
            # (no analytic family) honestly report no-offline-golden.
            offline = not S.BASE_URL or not S.API_KEY
            r = S.solve(question, max_attempts=max_attempts, history=history,
                        offline=offline)
    except KeyboardInterrupt:
        print("\rinterrupted", file=sys.stderr, flush=True)
        return (False, {})
    if r["ok"] and r.get("code"):
        n = r.get("attempts", 1)
        print(f"\r✓ done ({n} LLM call{'s' if n != 1 else ''})",
              file=sys.stderr, flush=True)
        sys.stdout.write(r["code"])
        if not r["code"].endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
        return (True, r)
    print("\r", file=sys.stderr, flush=True)
    print(f"ERROR: could not produce a VERIFIED solution for that question "
          f"({r.get('stage','')}) after {r.get('attempts', 0)} LLM calls.",
          file=sys.stderr)
    return (False, r)


def _repl(*, max_attempts: int, test_file: str | None) -> int:
    """Interactive multi-turn session where a human stays in the loop —
    ask, get verified code, then follow up just like codex / claude-code."""
    print(_BANNER, file=sys.stderr)
    print(_HELP, file=sys.stderr)

    session_history: list[dict] = []   # conversational QnA turns fed to the model
    last_code = ""
    solved_count = 0

    prompt = "qntelli> "
    while True:
        try:
            question = input(prompt)
        except EOFError:
            print(file=sys.stderr)
            break
        except KeyboardInterrupt:
            print(file=sys.stderr)
            continue

        q = question.strip()
        if not q:
            continue
        low = q.lower()
        if low in ("quit", "exit", "q"):
            print(f"bye — solved {solved_count} question(s) this session.",
                  file=sys.stderr)
            break
        if low in ("!last", "=last", "show last"):
            if last_code:
                sys.stdout.write(last_code)
                if not last_code.endswith("\n"):
                    sys.stdout.write("\n")
                sys.stdout.flush()
            else:
                print("(no successful answer yet this session)", file=sys.stderr)
            continue
        if low in ("!clear", "clear"):
            session_history = []
            print("context cleared.", file=sys.stderr)
            continue
        if low in ("!count",):
            print(f"solved {solved_count} question(s) this session with "
                  f"{len(session_history)} recorded assistant answer(s).",
                  file=sys.stderr)
            continue
        if low in ("!help", "help", "?"):
            print(_HELP, file=sys.stderr)
            continue

        ok, r = _solve_print(q, max_attempts=max_attempts,
                             test_file=test_file, history=session_history or None)
        if ok and r.get("code"):
            last_code = r["code"]
            solved_count += 1
            # Record the human turn + verified assistant answer so a follow-up
            # ("now make it 4 qubits") still has this spec as context. Clip to
            # a bounded window so long sessions don't blow the context budget.
            session_history.append({"role": "user", "content": q[:1500]})
            session_history.append({"role": "assistant",
                                    "content": r["code"][-4000:]})
            session_history = session_history[-12:]
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--help", action="store_true")
    ap.add_argument("--debug-env", action="store_true")
    ap.add_argument("--interactive", "--repl", action="store_true",
                    help="start an interactive, multi-turn conversation session")
    ap.add_argument("--test-file", default=None,
                    help="path to a test harness file; generated code is "
                         "appended and must pass it (exit 0) before printing")
    ap.add_argument("--max-attempts", type=int, default=S.MAX_ATTEMPTS)
    ap.add_argument("--self-test", action="store_true",
                    help="run the full golden bank offline and print the per-"
                         "(algorithm x SDK) one-enter pass-rate dashboard")
    ap.add_argument("question", nargs="*", default=None)
    args, _ = ap.parse_known_args()
    if getattr(args, "debug_env", False):
        import traceback as _tb
        print(f"frozen BASE_URL->{S.BASE_URL!r} API_KEY_set->{bool(S.API_KEY)}")
        # Attempt one real call to surface the true failure (e.g. SSL certs).
        code = S.call_model("Bell state circuit", "qntelli", "")
        print("call_model returned:", repr(code) if code else "None")
        S._print_live_exc()  # prints last urllib exception if any
        return 0
    if args.help:
        print("Ask a quantum coding question; get only correct, tested code.\n"
              "Use --interactive (or --repl) for a multi-turn conversation.",
              file=sys.stderr)
        return 0

    # --self-test: run the whole golden bank offline and print the per-(
    # algorithm-family x SDK) one-enter pass-rate dashboard. Consistent with
    # `solve.py --self-test` so `qntelli-solve --self-test` (documented in the
    # README) works identically through this entry point.
    if getattr(args, "self_test", False):
        bank = S.bank_questions()
        results = []
        for qid, q in bank.items():
            r = S.solve(q["prompt"], mode="qntelli", offline=True)
            vstage = ((r.get("verification") or {}).get("stage")
                      if r.get("verification") else None)
            results.append({"id": qid, "ok": r["ok"],
                            "attempts": r.get("attempts"),
                            "verification": vstage, "detail": r.get("detail")})
        passed = sum(1 for r in results if r["ok"])
        print(f"ONE-ENTER SELF-TEST: {passed}/{len(results)} verified on first solve")
        for r in results:
            print(f"  [{('PASS' if r['ok'] else 'FAIL'):4}] {r['id']:22s} stage={r['verification']}")
        S._print_pass_dashboard(results, S.bank_questions())
        return 0 if passed == len(results) else 1

    # Interactive session takes precedence: a human is here to converse.
    if getattr(args, "interactive", False):
        if args.question:
            print("note: --interactive ignores positional arguments; use the "
                  "prompt below. (Pass a question WITHOUT --interactive for a "
                  "one-shot.)", file=sys.stderr)
        return _repl(max_attempts=args.max_attempts, test_file=args.test_file)

    question = " ".join(args.question) if args.question else None
    if not question:
        # Only read stdin when it is actually piped/redirected. If stdin is an
        # interactive terminal (user ran `qntelli-solve` with no question),
        # do NOT block forever waiting for input — print usage and exit.
        if sys.stdin.isatty():
            print("no question given.\n"
                  "  one-shot:   qntellisolve '<quantum coding question>'\n"
                  "  pipe:       echo '<question>' | qntellisolve\n"
                  "  converse:   qntellisolve --interactive   (multi-turn,"
                  " like codex/claude-code)\n"
                  "  (start --interactive now? press Enter, or 'n' to exit)",
                  file=sys.stderr)
            try:
                _ans = input("start interactive session? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return 2
            if _ans in ("", "y", "yes"):
                return _repl(max_attempts=args.max_attempts,
                             test_file=args.test_file)
            return 2
        question = sys.stdin.read().strip()
    if not question:
        print("usage: qntellisolve '<quantum coding question>'  (or pipe the "
              "question in; or use --interactive for a conversation)",
              file=sys.stderr)
        return 2

    ok, _ = _solve_print(question, max_attempts=args.max_attempts,
                         test_file=args.test_file)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
