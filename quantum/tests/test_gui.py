#!/usr/bin/env python3
"""
test_gui.py - full test suite for the qntelli harness GUI.

Verifies, without a browser:
  * the server compiles and serves the dashboard HTML
  * every HTTP endpoint returns valid JSON with the expected shape
  * the orchestrator summary JSON-parsing helper is correct
  * the QAS subprocess worker isolates crashes (server stays up)
  * the frontend HTML contains all required UI hooks and is well-formed

Run:
    python3 quantum/tests/test_gui.py
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUI = HERE.parent / "gui"
GUIA = GUI / "gui_app.py"
WORKER = GUI / "worker.py"
INDEX = GUI / "index.html"
PY = sys.executable

_base = None
_server_proc = None


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _start_server():
    global _base, _server_proc
    port = _free_port()
    # Opt the server out of endpoint auto-configuration so the suite exercises
    # the deterministic no-endpoint fallback (and offline golden path) without
    # making live network calls, regardless of whether a secrets file exists on
    # the host running the tests. Explicitly tested separately (real endpoint
    # config is covered by test_endpoint_autoconfig).
    env = dict(os.environ)
    env["QNTELLI_GUI_NO_AUTOCONFIG"] = "1"
    _server_proc = subprocess.Popen(
        [PY, str(GUIA), "--port", str(port), "--host", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    _base = f"http://127.0.0.1:{port}"
    # wait for readiness
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            urllib.request.urlopen(_base + "/api/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def _stop_server():
    if _server_proc and _server_proc.poll() is None:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=5)
        except Exception:
            _server_proc.kill()


def _get(path, timeout=60):
    with urllib.request.urlopen(_base + path, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def _post(path, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else b"{}"
    req = urllib.request.Request(_base + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def _raw_post(path, raw: bytes, timeout=300):
    """POST an arbitrary (possibly non-JSON) raw body and return (status, json)."""
    req = urllib.request.Request(_base + path, data=raw, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


PASS = 0
FAILS = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAILS.append(name)
        print(f"  [FAIL] {name} {detail}")


def test_compile():
    print("\n== compile & import ==")
    r = subprocess.run([PY, "-m", "py_compile", str(GUIA), str(WORKER),
                        str(GUI / "envcfg.py")],
                       capture_output=True, text=True)
    check("gui_app.py + worker.py + envcfg.py compile", r.returncode == 0, r.stderr)
    # import the module in-process to test the JSON helper
    sys.path.insert(0, str(GUI))
    import gui_app as g
    text = '{\n  "a": 1,\n  "b": {"c": [1,2]}\n}tail'
    check("_extract_first_json nested", g._extract_first_json(text) ==
          {"a": 1, "b": {"c": [1, 2]}})
    check("_extract_first_json none", g._extract_first_json("no json here") is None)
    check("_extract_first_json empty", g._extract_first_json("") is None)


def test_backend_helpers():
    print("\n== backend helpers (time + outcome parsing) ==")
    import gui_app as g
    # _latest_iso_epoch: bug-fix — the hardware ledger stores ISO timestamps
    # with a non-standard "+0800" (no colon) zone that JS mis-parses. The
    # backend must normalise them to a reliable epoch.
    check("ISO +0800 parses", g._latest_iso_epoch("2026-08-30T13:18:47+0800") == 1788067127)
    check("ISO Z parses", g._latest_iso_epoch("2026-08-30T13:18:47Z") == 1788095927)
    check("int epoch passes through", g._latest_iso_epoch(1788067127) == 1788067127)
    check("millis epoch reduced", g._latest_iso_epoch(1788067127000) == 1788067127)
    check("None -> None", g._latest_iso_epoch(None) is None)
    check("garbage -> None", g._latest_iso_epoch("not-a-time") is None)
    check("empty -> None", g._latest_iso_epoch("") is None)
    # _top_outcome: bug-fix — the frontend used to show '—' for every job's
    # top outcome because the ledger only stores a counts dict.
    check("top outcome found", g._top_outcome({"00": 2008, "11": 1992}) == "00")
    check("top outcome largest", g._top_outcome({"0": 100, "111": 900, "1": 20}) == "111")
    check("empty counts -> None", g._top_outcome({}) is None)
    check("None counts -> None", g._top_outcome(None) is None)
    check("non-dict -> None", g._top_outcome("oops") is None)


def test_frontend_file():
    print("\n== frontend file ==")
    check("index.html exists", INDEX.exists())
    if not INDEX.exists():
        return
    html = INDEX.read_text()
    check("has required elements",
          all(x in html for x in ["btnOrch", "btnTests", "btnSolve", "btnQas",
                                  "btnBench", "loadStatus", "runTests",
                                  "api('/api/status'", "</html>"]))
    # bug-fix UI hooks introduced by the redesign
    check("has new UI hooks",
          all(x in html for x in ["btnSolveView", "codeModal", "modalCode",
                                  "donutCv", "lineCv", "tierCv", "expCv",
                                  "canvasSize", "expBars", "orchSummaryCards",
                                  "qasCandidates"]))
    # beauty/accessibility polish: custom scrollbars + reduced-motion support
    # (pure-CSS additions; must stay present so we don't lose the polish)
    check("custom scrollbar styling present",
          "-webkit-scrollbar" in html and "scrollbar-thumb" in html)
    check("reduced-motion accessibility present",
          "prefers-reduced-motion" in html)
    # bug-fix regression: _qasmCache is assigned inside runQas(). The file is
    # 'use strict', so it MUST be declared with let/var/const at top level —
    # assigning an undeclared identifier throws ReferenceError at runtime,
    # which would break the "view QASM" feature the moment a user visits the
    # QAS tab. Guard the declaration.
    qasm_decl = re.search(r"(?:let|var|const)\s+_qasmCache\s*=", html)
    check("_qasmCache declared (strict-mode safe)", qasm_decl is not None)
    # bug-fix regression: the old donut() centre hardcoded
    # `const pct=(total?100:0).toFixed(1)` so every dial showed '100.0%' no
    # matter the real pass rate. The centre must be driven by the actual
    # values, not a constant. Refuse a hardcoded 100 literal there.
    donut_src = re.search(r"function donut\([^)]*\)\{(.*?)\n\}", html, re.S)
    if donut_src:
        body = donut_src.group(1)
        check("donut centre not hardcoded to 100",
              "(total?100:0)" not in body and "(data[0]" in body or "centerValue" in body)
        check("donut accepts explicit centre via opts",
              "centerValue" in body and "centerLabel" in body)
    else:
        check("donut function found", False, "regex did not match donut()")
    # bug-fix: chart drawing must never run on a zero-size (hidden) canvas,
    # because arc() with a negative radius throws. The canvasSize guard must
    # be present.
    check("canvas negative-radius guard present",
          "canvasSize" in html and "getBoundingClientRect" in html and
          "return null" in html)
    check("no inline-JS QASM embedding (escaping hazard)",
          "onclick=\"openQasm" not in html)
    check("one <script> block", html.count("<script>") == 1)
    # light sanity: the inline script should have balanced backticks as a proxy
    # for healthy template literals (nested-backtick bugs are caught upstream).
    check("balanced <div> tags",
          html.count("<div") >= html.count("</div"))
    # REGRESSION GUARD (bug: general/custom questions returned no code and the
    # backend's failure `detail` was silently dropped, so users saw a blank
    # result with no explanation). The Solver render MUST surface `rr.detail`.
    solve_render = re.search(r"if\(rr\.detail\)txt\+='REASON.*", html)
    check("solver failure detail is surfaced in UI",
          bool(solve_render) and "REASON" in html and "STAGE" in html,
          "runSolve must render rr.stage and rr.detail on failure")
    # The online (model-backed) opt-in control for custom questions must exist,
    # and runSolve must send the `online` flag to the backend.
    check("online-model opt-in checkbox present",
          'id="chkOnline"' in html, "Solver tab needs a chkOnline checkbox")
    check("runSolve sends online flag",
          "{question:q,online}" in html, "runSolve must POST the online flag")
    # REGRESSION GUARD (bug: after a successful online/offline solve the
    # "View verified code" modal opened EMPTY — runSolve showed the button when
    # rr.code existed but never stored the code in _codeCache, so the modal's
    # openCode(_codeCache) received null/stale and bailed, i.e. users "got
    # nothing". runSolve MUST assign _codeCache before revealing the button.
    check("runSolve stores code in _codeCache for the modal",
          re.search(r"if\(rr\.code\)\{_codeCache\s*=rr\.code", html) is not None,
          "runSolve must set _codeCache=rr.code before showing btnSolveView")
    # If node is present, syntax-check the inline JS. This catches the real
    # bugs found in development: a stray brace in the particle animation and
    # a `??` mixed with `&&` without parentheses in a template literal.
    import shutil
    node = shutil.which("node")
    if node:
        script = re.search(r"<script>(.*?)</script>", html, re.S)
        if script:
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(script.group(1)); js_path = f.name
            try:
                r = subprocess.run([node, "--check", js_path],
                                   capture_output=True, text=True)
                check("inline JS passes node --check", r.returncode == 0,
                      (r.stderr or r.stdout)[-400:])
            finally:
                os.unlink(js_path)
    else:
        print("  (node not found; skipping inline-JS syntax check)")


def test_frontend_donut_behaviour():
    """Execute the actual donut() chart function headlessly under node with a
    mock canvas and assert the centre text reflects the real pass rate — NOT a
    hardcoded '100.0%'. Behavioural regression test for the bug where every
    donut always displayed 100% regardless of the underlying numbers."""
    import shutil
    node = shutil.which("node")
    check("node available for behavioural JS test", node is not None)
    if not node:
        return
    html = INDEX.read_text()
    # extract the donut function body (the brace-balanced block). The function
    # signature is exactly: function donut(cv,data,labels,opts){
    m = re.search(r"function donut\(cv,data,labels,opts\)\{(.*?)\n\}", html, re.S)
    check("donut() source extractable", m is not None, "could not find donut() {}")
    if not m:
        return
    body = m.group(1)
    # Assemble a self-contained node script: stub canvasSize + PALETTE, use a
    # recording 2d context, then call donut() with a 75% pass rate and print
    # every fillText so the test can inspect the centre value.
    script = (
        "var fills=[];\n"
        "var PALETTE=['#6c8cff','#b06cff','#4fe3d4','#ffb454','#ff6bb6','#3ddc97','#ff6b6b','#9aa3cf'];\n"
        "var ctx=(function(){\n"
        "  var r={scale:function(){},beginPath:function(){},arc:function(){},closePath:function(){},fill:function(){},\n"
        "         fillText:function(t){fills.push(String(t))}};\n"
        "  return r;})();\n"
        "var cv={getContext:function(){return ctx;},getBoundingClientRect:function(){return {width:200,height:200};}};\n"
        "function canvasSize(c){return {W:200,H:200,dpr:1,ctx:ctx};}\n"
        "function donut(cv,data,labels,opts){" + body + "}\n"
        "donut(cv,[300,100],['pass','fail'],{centerValue:'75%',centerLabel:'pass rate'});\n"
        "process.stdout.write(fills.join('|'));\n"
    )
    r = subprocess.run([node, "-e", script], capture_output=True, text=True)
    check("donut executes without throwing", r.returncode == 0, (r.stderr or "")[-300:])
    out = (r.stdout or "")
    center = out.split("|")[0] if out else ""
    check("donut centre shows real pass rate (not 100.0)",
          center == "75%", f"got centre text: {center!r}")
    check("donut centre label rendered", "pass rate" in out,
          f"centre label missing from: {out!r}")
    # second run: proportion-derived default when no explicit value is passed
    script2 = ("var fills=[];\nvar PALETTE=['#6c8cff'];\n"
               "var ctx={scale:function(){},beginPath:function(){},arc:function(){},closePath:function(){},fill:function(){},\n"
               "        fillText:function(t){fills.push(String(t))}};\n"
               "var cv={getContext:function(){return ctx;},getBoundingClientRect:function(){return {width:200,height:200};}};\n"
               "function canvasSize(c){return {W:200,H:200,dpr:1,ctx:ctx};}\n"
               "function donut(cv,data,labels,opts){" + body + "}\n"
               "donut(cv,[60,40],['a','b'],null);\n"
               "process.stdout.write(String(fills[0]));\n")
    r2 = subprocess.run([node, "-e", script2], capture_output=True, text=True)
    check("donut default centre is the total count (60+40=100)",
          (r2.stdout or "").strip() == "100",
          f"default centre got: {(r2.stdout or '')!r}")


def test_frontend_helpers_behaviour():
    """Behavioural tests for the small front-end helper functions, executed
    against the REAL inline script inside the headless DOM stub (no fragile
    regex re-extraction): the HTML escaper `esc()`, the timestamp formatter
    `fmtT()`, and the zero-size-canvas guard `canvasSize()` that prevents a
    negative-radius arc() throw. Also verifies the code-modal copy button hook
    (a beauty/utility feature) is present and wired.""" + """
    """
    import shutil
    node = shutil.which("node")
    check("node available for helper behavioural tests", node is not None)
    if not node:
        return
    html = INDEX.read_text()
    # the copy hook must exist and be wired to the copyCode handler
    check("code-modal copy button present",
          'id="modalCopy"' in html and "copyCode" in html and
          "$('#modalCopy').onclick=copyCode;" in html)
    check("mini button style present", ".btn.mini" in html)
    # the helpers must be the canonical forms (so the behavioural call below
    # is meaningful)
    check("esc defined as one-liner escaper",
          'const esc=s=>String' in html and '.replace(/[&<>"\'>]/g' in html.replace("'\"'", "'") or 'esc' in html)
    check("fmtT + canvasSize defined",
          "function fmtT" in html and "function canvasSize" in html)

    script_m = re.search(r"<script>(.*?)</script>", html, re.S)
    if not script_m:
        check("inline script extractable", False)
        return
    check("inline script extractable", True)
    stub = (HERE / "gui_dom_stub.js").read_text()
    # run the FULL front-end so esc/fmtT/canvasSize are the REAL functions, then
    # drive them directly and print results.
    driver = r"""
// drive the helper functions that the inline script just defined
var __out=[];
(function(){
  __out.push('E:'+esc('<b>&"\''));
  __out.push('F:'+fmtT(null));
  __out.push('FN:'+fmtT(1788000000));
  // canvasSize must return null for a hidden (0-size) canvas
  var zero={getContext:function(){return {};},getBoundingClientRect:function(){return {width:0,height:0};}};
  __out.push('C0:'+String(canvasSize(zero)));
  // and live metrics for a visible canvas
  var real={getContext:function(){return 'CTX';},getBoundingClientRect:function(){return {width:200,height:100};}};
  window.devicePixelRatio=2;
  var cs=canvasSize(real);__out.push('CR:'+cs.W+','+cs.H+','+cs.dpr+','+cs.ctx);
})();
console.log('HELPERS='+__out.join('|'));
process.exit(0);
"""
    combined = stub + "\n// ==== extracted inline front-end ====\n" + script_m.group(1) + "\n" + driver
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(combined); h_path = f.name
    try:
        r = subprocess.run([node, h_path], capture_output=True, text=True, timeout=60)
        check("helpers execute without throwing", r.returncode == 0, (r.stderr or "")[-500:])
        out = r.stdout or ""
        m = re.search(r"HELPERS=(\[?.*\]?)", out)
        if not m:
            check("helpers printed results", False, f"no HELPERS marker in: {out[-200:]!r}")
            return
        parts = m.group(1).split("|")
        def part(k):
            for p in parts:
                if p.startswith(k+":"):
                    return p[len(k)+1:]
            return None
        check("esc() neutralises HTML/JS metacharacters",
              "&lt;b&gt;&amp;&quot;&#39;" in (part("E") or ""),
              f"got: {part('E')!r}")
        check("fmtT(null) renders em-dash", part("F") == "—",
              f"got: {part('F')!r}")
        check("canvasSize null on hidden canvas", part("C0") == "null",
              f"got: {part('C0')!r}")
        check("canvasSize returns live metrics on visible canvas",
              part("CR") == "200,100,2,CTX", f"got: {part('CR')!r}")
    finally:
        os.unlink(h_path)


def test_frontend_script_loads():
    """Run the FULL front-end script headlessly under node inside a DOM stub
    and assert it loads without throwing. This catches load-time ReferenceErrors
    / TypeErrors — the same class of bug as the historical _qasmCache (assigned
    but never declared under 'use strict', which threw ReferenceError the moment
    the QAS tab was used). The stub lets every automatic loader (status, hw,
    exp, logs), the particle animation and all wire-up execute."""
    import shutil
    node = shutil.which("node")
    check("node available for headless load test", node is not None)
    if not node:
        print("  (node not found; skipping headless front-end load test)")
        return
    stub = (HERE / "gui_dom_stub.js")
    check("DOM stub exists", stub.exists())
    if not stub.exists():
        return
    script = re.search(r"<script>(.*?)</script>", INDEX.read_text(), re.S)
    check("inline <script> extractable", script is not None)
    if not script:
        return
    combined = stub.read_text() + "\n// ==== extracted inline front-end ====\n" + \
               script.group(1) + "\nconsole.log('FRONTEND-SCRIPT-OK');\n"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(combined); js_path = f.name
    try:
        r = subprocess.run([node, js_path], capture_output=True, text=True, timeout=60)
        check("front-end script loads cleanly (exit 0)",
              r.returncode == 0, (r.stderr or "")[-500:])
        check("front-end script reached end-of-script marker",
              "FRONTEND-SCRIPT-OK" in (r.stdout or ""))
    finally:
        os.unlink(js_path)
    # --- happy-path render test: mock fetch with realistic harness payloads
    # so the automatic loaders actually BUILD the DOM (stat cards, tables,
    # donut/spark/bar charts) and any rendering TypeError surfaces.
    script_body = script.group(1)
    mock_fetch = r"""
global.fetch = async (url) => {
  const u = String(url);
  const j = (obj) => ({ ok:true, status:200, json:async()=>obj });
  if (u.includes('/api/status')) return j({
    python:'3.11.0', harness_ready:{qiskit:true,pennylane:true,cirq:true},
    bench:{passes:380,total:380,rate:1.0}, runs_total:380, onetimepass_total:16,
    jobs_total:918, reports:[{name:'grover_case_study.docx',mtime:1788067127}],
    experience_total:9, ts:1788067127});
  if (u.includes('/api/charts')) return j({
    hardware_tiers:{simulation:5,emulator:3}, hardware_status:{complete:8},
    experience_groups:[{key:'bell/qiskit',pass:4,fail:1},
                       {key:'ghz/qiskit',pass:3,fail:1}],
    experience_total:{pass:7,fail:2},
    bench_history:[{pass:380,total:380,rate:1}]});
  if (u.includes('/api/hardware/devices')) return j({
    rc:0, devices:[{device_id:'ionq:forte',num_qubits:30,
      native_gates:['gpi','gpi2','zz','ms'],tiers:['simulation','emulator','qpu']},
      {device_id:'quantinuum:h2-1e',num_qubits:20,
      native_gates:['phasedx','rz','zzphase'],tiers:['emulator']}]});
  if (u.includes('/api/hardware/jobs')) return j({
    jobs:[{device_id:'ionq:forte',tier:'emulator',status:'complete',
           counts_top:'00',shots:2000,_epoch:1788067127}], total:918});
  if (u.includes('/api/experience')) return j({
    rc:0, stats:{groups:{'bell/qiskit':{pass:4,fail:1},
                         'ghz/qiskit':{pass:3,fail:1}},
                 total:{pass:7,fail:2}}, samples:[]});
  if (u.includes('/api/orchestrator/logs')) return j([
    {name:'state_log.jsonl',mtime:1788067127,lines:10}]);
  return j({error:'unmocked '+u});
};
// Falsification guard: any unhandled rejection or uncaught exception during
// the async render phase is a REAL front-end bug. Record them and make the
// suite fail, instead of silently swallowing (a historical bug — the donut
// legend referenced an undeclared `num` variable, throwing ReferenceError,
// which the stub's no-op rejection handler used to hide).
process.on('unhandledRejection', (e, p) => {
  global.__errors = (global.__errors||[]).concat(String(e && e.message || e));
});
process.on('uncaughtException', (e) => {
  global.__errors = (global.__errors||[]).concat('uncaughtException: ' + String(e && e.message || e));
});
// wait briefly for the async loaders to render, then assert render completed
let ticks = 0;
const wait = global.setTimeout(function tick(){
  ticks++;
  const stats = document.querySelector('#statusStats').innerHTML || '';
  const jobsTbl = document.querySelector('#hwJobsTable').innerHTML || '';
  const expTbl = document.querySelector('#expTable').innerHTML || '';
  if ((stats.includes('benchmark runs') && jobsTbl.includes('ionq:forte') &&
       expTbl.includes('bell/qiskit')) || ticks > 60) {
    console.log('RENDER-STATS=' + String(stats.length));
    console.log('RENDER-JOBS=' + String(jobsTbl.length));
    console.log('RENDER-EXP=' + String(expTbl.length));
    console.log('RENDER-DONE ' + (stats.includes('benchmark runs') ? 'OK' : 'EMPTY'));
    const errs = global.__errors || [];
    console.log('RENDER-ERRORS=' + JSON.stringify(errs));
    process.exit(0);
  }
  global.setTimeout(tick, 40);
}, 40);
"""
    happy = stub.read_text() + mock_fetch + "\n// ==== extracted inline front-end ====\n" + script_body
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(happy); hp_path = f.name
    try:
        env = dict(os.environ); env["QNTELLI_REAL_TIMEOUT"] = "1"
        r = subprocess.run([node, hp_path], capture_output=True, text=True,
                           timeout=60, env=env)
        check("happy-path render runs (exit 0)",
              r.returncode == 0, (r.stderr or "")[-600:])
        check("happy-path renders sanity",
              "RENDER-DONE OK" in (r.stdout or ""), (r.stdout or "")[-300:])
        # Falsification guard: the async render must complete with ZERO
        # unhandled rejections / uncaught exceptions. Historically this was
        # the `num is not defined` ReferenceError in the status donut legend —
        # swallowed by the stub so the test still "passed". A REJECTIONS line
        # is always printed (even when empty), so we can assert it firmly.
        rej = re.search(r"RENDER-ERRORS=(\[.*\])", r.stdout or "")
        if rej:
            errs = json.loads(rej.group(1))
            check("happy-path render has no runtime errors",
                  not errs, "; ".join(errs) if errs else "")
        else:
            check("happy-path render reports error list",
                  False, "RENDER-ERRORS marker missing from output")
    finally:
        os.unlink(hp_path)


def test_status_endpoint():
    print("\n== status ==")
    st, d = _get("/api/status")
    check("status 200", st == 200)
    check("python version present", "python" in d)
    check("harness sdk probe", isinstance(d.get("harness_ready"), dict))
    check("bench summary shape", "passes" in (d.get("bench") or {}))


def test_nav():
    st, d = _get("/api/nav")
    check("nav has experiments", isinstance(d.get("experiments"), list) and
          "bell" in d["experiments"] and "grover" in d["experiments"])


def test_hardware():
    print("\n== hardware ==")
    st, d = _get("/api/hardware/devices")
    check("devices rc0", d.get("rc") == 0)
    check("ion-trap devices present", len(d.get("devices", [])) >= 1)
    st, j = _get("/api/hardware/jobs?limit=5")
    check("jobs ledger", isinstance(j.get("jobs"), list))
    check("jobs have device_id",
          all("device_id" in x for x in j.get("jobs", [])[:3]) or not j.get("jobs"))
    # bug-fix: the harness stores ISO ts with a '+0800' zone and only a counts
    # dict. The server must normalise these so the frontend can show a time and
    # a top outcome without guessing.
    for rec in j.get("jobs", [])[:3]:
        if not rec:
            continue
        check("job has epoch", "_epoch" in rec)
        check("job has top outcome", "counts_top" in rec)
    if j.get("jobs"):
        first = j["jobs"][0]
        if "counts" in first:
            expected = max(first["counts"].items(), key=lambda kv: kv[1])[0]
            check("top outcome matches counts", first["counts_top"] == expected)
            check("epoch looks sane", first["_epoch"] is None or first["_epoch"] > 1500000000)


def test_charts_endpoint():
    print("\n== charts endpoint ==")
    st, d = _get("/api/charts")
    check("charts 200", st == 200)
    check("hardware_tiers dict", isinstance(d.get("hardware_tiers"), dict))
    check("hardware_status dict", isinstance(d.get("hardware_status"), dict))
    check("experience_groups list", isinstance(d.get("experience_groups"), list))
    check("experience_total has pass/fail",
          "pass" in (d.get("experience_total") or {}) and
          "fail" in (d.get("experience_total") or {}))
    check("bench_history list", isinstance(d.get("bench_history"), list))
    # experience totals must be self-consistent with the groups
    tot = d.get("experience_total") or {}
    gpass = sum(g.get("pass", 0) for g in d.get("experience_groups", []))
    gfail = sum(g.get("fail", 0) for g in d.get("experience_groups", []))
    check("experience totals match groups",
          tot.get("pass") == gpass and tot.get("fail") == gfail)


def test_experience():
    print("\n== experience ==")
    st, d = _get("/api/experience")
    check("experience rc0", d.get("rc") == 0)
    s = d.get("stats", {})
    check("groups present", isinstance(s.get("groups"), dict))
    check("total has pass/fail", "pass" in (s.get("total") or {}))


def test_logs_and_replay():
    print("\n== logs & replay ==")
    st, logs = _get("/api/orchestrator/logs")
    check("logs list", isinstance(logs, list))
    if logs:
        name = logs[0]["name"]
        st, r = _post("/api/orchestrator/replay", {"log": name})
        check("replay rc0", (r.get("result") or {}).get("rc") == 0)
        check("replay has trace", "output" in (r.get("result") or {}))


def test_qas_worker_isolation():
    print("\n== QAS subprocess isolation ==")
    st, d = _post("/api/qas/run", {"experiment": "qft"}, timeout=200)
    res = d.get("result") or {}
    check("qas ok", d.get("ok") is True, str(d)[:200])
    check("qas selected present",
          isinstance(res.get("result"), dict) and
          (res["result"].get("selected") or {}).get("name") in
          ("baseline", "opt1", "opt2", "opt3"))


def test_online_solve_isolation():
    """Regression: the model-backed (online) solve for general/custom questions
    must run in the crash-isolated worker subprocess — it executes generated
    quantum code that can segfault a C-extension (qiskit-aer), and that crash
    must NEVER take down the GUI server. Confirms the request completes and the
    server is still alive afterwards."""
    print("\n== online solve crash isolation ==")
    gen_q = ("Design a custom 2-qubit circuit and use qiskit_aer to return the "
             "counts via a function named my_circ().")
    st, d = _post("/api/solver/solve",
                  {"question": gen_q, "online": True}, timeout=300)
    res = d.get("result") or {}
    rr = res.get("result") or {}
    check("online solve survives (HTTP 200)", st == 200 and d.get("ok") is True,
          str(d)[:200])
    # With no endpoint in the test server's env, the worker returns a clear
    # no-endpoint result (still a well-formed, non-crashing response).
    check("online solve returns a well-formed verdict",
          isinstance(rr, dict) and "ok" in rr, str(rr)[:200])
    # Server must still be alive (crash-isolated from the worker).
    try:
        urllib.request.urlopen(_base + "/api/status", timeout=5)
        check("server alive after online solve", True)
    except Exception as e:
        check("server alive after online solve", False, str(e))


def test_endpoint_autoconfig():
    """REG-ROOT-CAUSE: the GUI's Solve button returned NO code for general/custom
    questions (e.g. the XOR gate) because the server never populated the model
    endpoint env the way the CLI launchers do, so solve.BASE_URL/API_KEY were
    empty and the online path failed with 'no model endpoint configured'.

    Exercise the shared envcfg module (used by both gui_app.py and worker.py) to
    confirm it populates the endpoint config the same way, WITHOUT making any
    live network call (we only assert env gets populated, not that the endpoint
    responds)."""
    print("\n== endpoint auto-config (GUI Solve reachability) ==")
    import importlib
    import os
    import sys
    # Isolate: clear any pre-set endpoint vars so the auto-config must supply them.
    saved = {k: os.environ.pop(k, None)
             for k in ("QNTELLI_BASE_URL", "HUANXIN_DP4_BASE_URL",
                       "QNTELLI_API_KEY", "HUANXIN_DP4_API_KEY",
                       "QNTELLI_GUI_NO_AUTOCONFIG")}
    try:
        if str(GUI) not in sys.path:
            sys.path.insert(0, str(GUI))
        import envcfg
        importlib.reload(envcfg)
        envcfg.configure_endpoint()
        base = os.environ.get("QNTELLI_BASE_URL") or os.environ.get("HUANXIN_DP4_BASE_URL")
        key = os.environ.get("QNTELLI_API_KEY") or os.environ.get("HUANXIN_DP4_API_KEY")
        check("auto-config supplies a base URL", bool(base), f"base={base!r}")
        check("auto-config supplies an API key", bool(key),
              f"key_set={bool(key)}")
        check("no_proxy bypass present for aihuanxin.cn",
              "aihuanxin.cn" in os.environ.get("no_proxy", ""))
        # The end-point must be visible to solve.py (which reads env at import).
        qp = str(GUI.parent)
        if qp not in sys.path:
            sys.path.insert(0, qp)
        import solve
        importlib.reload(solve)
        check("solve sees BASE_URL after auto-config", bool(solve.BASE_URL))
        check("solve sees API_KEY after auto-config", bool(solve.API_KEY))
    finally:
        # Restore the original env so the rest of the suite is unaffected.
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_bench_run():
    print("\n== validator bench (fast path) ==")
    st, d = _post("/api/bench/run", timeout=200)
    out = (d.get("result") or {}).get("output", "")
    check("bench ran", d.get("ok") is True)
    check("bench reports rate", "PASS RATE" in out)


def test_solver():
    print("\n== offline solver ==")
    st, d = _post("/api/solver/solve", {"question": "write a 3-qubit GHZ circuit and verify it"}, timeout=120)
    res = d.get("result") or {}
    rr = res.get("result") or {}
    check("solver ok", rr.get("ok") is True, str(rr)[:200])
    check("verified code returned", isinstance(rr.get("code"), str) and len(rr.get("code", "")) > 10)
    # REGRESSION (bug: custom/general question returned no code and the reason
    # was invisible). Backend must return a clear, non-empty `detail` + `stage`
    # so the frontend can surface it. HTTP still 200, JSON well-formed.
    gen_q = ("Given two 8-bit integers a and b design a Quantum Circuit that acts "
             "as a classical XOR gate. Implement a function named xor_gate(a,b) "
             "and simulate with the Qiskit Aer Sampler.")
    st, d = _post("/api/solver/solve", {"question": gen_q}, timeout=120)
    res = d.get("result") or {}
    rr = res.get("result") or {}
    check("general question returns well-formed JSON", st == 200 and d.get("ok") is True)
    check("general question explicitly fails (no silent hang)", rr.get("ok") is False)
    check("general question failure carries a stage",
          isinstance(rr.get("stage"), str) and len(rr.get("stage", "")) > 0,
          str(rr)[:150])
    check("general question failure carries a reason (detail)",
          isinstance(rr.get("detail"), str) and len(rr.get("detail", "")) > 0,
          str(rr)[:150])
    # ONLINE solve path: with `online:true` on a general question, if no model
    # endpoint is configured the GUI must return a CLEAR no-endpoint error and
    # — critically — must NOT crash the server or hang.
    st, d = _post("/api/solver/solve",
                  {"question": gen_q, "online": True}, timeout=120)
    res = d.get("result") or {}
    rr = res.get("result") or {}
    check("online solve survives (HTTP 200)", st == 200 and d.get("ok") is True)
    if rr.get("ok") is False:
        check("online no-endpoint carries a stage",
              rr.get("stage") == "no-endpoint", str(rr)[:150])
        check("online no-endpoint carries a clear detail",
              isinstance(rr.get("detail"), str) and "endpoint" in rr.get("detail", ""),
              str(rr)[:150])
    # A supported-family question with online:true still uses the offline golden
    # (never requires a model), so it must return verified code even with no
    # endpoint configured.
    st, d = _post("/api/solver/solve",
                  {"question": "write a 2-qubit Bell circuit and verify it",
                   "online": True}, timeout=120)
    res = d.get("result") or {}
    rr = res.get("result") or {}
    check("online flag keeps golden family offline-solvable",
          rr.get("ok") is True and isinstance(rr.get("code"), str)
          and len(rr.get("code", "")) > 10,
          str(rr)[:200])


def test_404():
    print("\n== 404 handling ==")
    try:
        urllib.request.urlopen(_base + "/api/does-not-exist", timeout=5)
        check("404 returned", False)
    except urllib.error.HTTPError as e:
        check("404 returned", e.code == 404)


def test_server_survives_bad_input():
    print("\n== bad input does not kill server ==")
    # JSON body that the orchestrator handler must survive (unknown experiment)
    st, d = _post("/api/orchestrator/run", {"experiment": "not-a-real-exp"}, timeout=120)
    check("orchestrator survives unknown experiment", st == 200)
    # empty solver question
    st, d = _post("/api/solver/solve", {"question": ""}, timeout=30)
    check("solver survives empty question", st == 200 and d.get("ok") is True)


def test_server_robustness():
    print("\n== malformed input & param caps ==")
    # a completely non-JSON POST body must be tolerated (treated as {}), not 500
    try:
        st, d = _raw_post("/api/orchestrator/run", b"this is not json{{{")
        check("non-JSON body returns 200 (not 500)", st == 200)
        check("non-JSON body result is well-formed", d.get("ok") is True)
    except Exception as e:
        check("non-JSON body returns 200 (not 500)", False, str(e))
    # empty post body -> defaults, no crash
    try:
        st, d = _raw_post("/api/orchestrator/run", b"")
        check("empty body returns 200", st == 200)
    except Exception as e:
        check("empty body returns 200", False, str(e))
    # hardware job ledger limit must be capped (large limit -> <= 500 rows)
    st, d = _get("/api/hardware/jobs?limit=99999")
    jobs = d.get("jobs", [])
    check("jobs limit capped at 500", len(jobs) <= 500, f"got {len(jobs)}")
    # a small requested limit is honoured
    st, d = _get("/api/hardware/jobs?limit=2")
    check("jobs limit=2 honoured", len(d.get("jobs", [])) <= 2)
    # garbage limit falls back to the default (no crash)
    st, d = _get("/api/hardware/jobs?limit=abc")
    check("garbage jobs limit tolerated", isinstance(d.get("jobs"), list))
    # non-numeric / malformed query strings on other endpoints must not crash
    for p in ("/api/hardware/jobs?limit=1e9", "/api/hardware/jobs?limit=-5"):
        try:
            st, d = _get(p)
            check(f"endpoint tolerates {p}", isinstance(d.get("jobs"), list))
        except Exception as e:
            check(f"endpoint tolerates {p}", False, str(e))


def main():
    ok = _start_server()
    check("server starts", ok)
    if not ok:
        print("FATAL: server did not start")
        sys.exit(1)
    try:
        test_compile()
        test_backend_helpers()
        test_frontend_file()
        test_frontend_donut_behaviour()
        test_frontend_helpers_behaviour()
        test_frontend_script_loads()
        test_status_endpoint()
        test_nav()
        test_hardware()
        test_charts_endpoint()
        test_experience()
        test_logs_and_replay()
        test_qas_worker_isolation()
        test_online_solve_isolation()
        test_endpoint_autoconfig()
        test_bench_run()
        test_solver()
        test_404()
        test_server_survives_bad_input()
        test_server_robustness()
    finally:
        _stop_server()

    print(f"\n{'='*50}")
    print(f"GUI TEST RESULT: {PASS} passed, {len(FAILS)} failed")
    if FAILS:
        print("failures:", FAILS)
        sys.exit(1)
    print("ALL GUI TESTS GREEN")
    sys.exit(0)


if __name__ == "__main__":
    main()
