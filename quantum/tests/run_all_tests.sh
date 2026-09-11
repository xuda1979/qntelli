#!/usr/bin/env bash
# qntelli test runner — runs the one-enter harness guarantee suite + project green suite.
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
echo "############ QNTELLI TEST SUITE ############"
echo "== 1. compile all python =="
python3 -m py_compile quantum/harness/qntelli_validate.py \
  quantum/benchmarks/onetimepass.py \
  quantum/orchestrator/orchestrator.py \
  quantum/orchestrator/metrics.py quantum/solve.py \
  quantum/report_gen.py quantum/generate_reports.py \
  quantum/gui/gui_app.py quantum/gui/worker.py quantum/gui/envcfg.py || exit 1
echo "   OK"
echo "== 2. offline one-enter guarantee tests =="
python3 quantum/tests/test_solve_guarantee.py || exit 1
echo "== 2b. QAS 智能体 (circuit search) tests =="
python3 quantum/tests/test_qas_agent.py || exit 1
echo "== 2c. experience/knowledge-harvest tests =="
python3 quantum/tests/test_experience.py || exit 1
echo "== 2d. report-gen (qc.experiment.report) tests =="
python3 quantum/tests/test_report_gen.py || exit 1
echo "== 2e. model hardware standard (ion-trap devices) tests =="
python3 quantum/tests/test_hardware_standard.py || exit 1
echo "== 3. full-bank self-test =="
python3 quantum/solve.py --self-test | tail -1
echo "== 4. harness bench + onetimepass =="
python3 quantum/harness/qntelli_validate.py bench | tail -1
python3 quantum/benchmarks/onetimepass.py --offline | tail -1
echo "== 5. orchestrator (real, default) incl. QAS + ion-trap hardware stages =="
python3 quantum/orchestrator/orchestrator.py \
  --design-start bell ghz qft grover optimization ml --out-log /tmp/qt 2>/dev/null \
  | grep -cE '"autonomous_complete": true' | sed 's/^/   oracle complete: /'
rm -f /tmp/qt.* 2>/dev/null
echo "== 5b. harness GUI (server endpoint + frontend + crash isolation) =="
python3 quantum/tests/test_gui.py || exit 1
echo "== 6. LIVE one-enter tests (skip if no endpoint) =="
python3 quantum/tests/test_solve_live.py
echo "############ DONE ############"
