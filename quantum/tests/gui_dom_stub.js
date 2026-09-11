// gui_dom_stub.js - minimal headless browser DOM stub so the qntelli GUI
// front-end script can be executed under node to prove it loads without
// runtime exceptions (ReferenceError/TypeError) in 'use strict' mode.
//
// Usage: this file is concatenated BEFORE the extracted inline <script> of
// index.html and run with `node combined.js`. It stubs document/window/fetch/
// canvas so every loader + the particle background + the wire-up run headless.
//
// It is intentionally minimal: it only needs to let the script PARSE and
// EXECUTE without throwing, not render pixels.

// keep the process from hanging on timers / network.
// Set globalThis.__QNTELLI_REAL_TIMEOUT = true (in the preamble) to keep the
// real setTimeout so a test can wait for async loaders to finish rendering;
// setInterval is always disabled so the background auto-refresh never loops.
if (typeof global !== "undefined") {
  global.setInterval = () => 0;               // never run background refresh
  if (process.env.QNTELLI_REAL_TIMEOUT !== "1") {
    global.setTimeout = (fn, ms) => 0;        // never run deferred callbacks
  }
  global.requestAnimationFrame = () => 0;     // never run the particle loop
  global.clearTimeout = () => {};
  global.getComputedStyle = () => ({});
  process.on("unhandledRejection", () => {}); // loaders intentionally no-op offline
}

function make2dCtx() {
  return {
    scale(){}, beginPath(){}, arc(){}, moveTo(){}, lineTo(){}, closePath(){},
    fill(){}, stroke(){}, fillRect(){}, strokeRect(){}, clearRect(){}, fillText(){},
    translate(){}, save(){}, restore(){}, createLinearGradient(){return {addColorStop(){}};},
    createRadialGradient(){return {addColorStop(){}};}, set fillStyle(v){}, get fillStyle(){return ''},
    set strokeStyle(v){}, get strokeStyle(){return ''}, set lineWidth(v){}, get lineWidth(){return 1},
    set font(v){}, get font(){return ''}, set textAlign(v){}, get textAlign(){return ''},
    set globalAlpha(v){}, get globalAlpha(){return 1}, rect(){}, roundRect(){},
    setTransform(){}, transform(){}, measureText(){return {width:10};},
  };
}

function makeEl(tag, id) {
  const e = {
    tagName: tag || "div", id: id || "", dataset: {}, style: {},
    innerHTML: "", textContent: "", value: "", className: "", placeholder: "",
    disabled: false, checked: false, hidden: false,
    classList: {
      _s: new Set(),
      add(c){ this._s.add(c); }, remove(c){ this._s.delete(c); },
      toggle(c){ this._s.has(c)?this._s.delete(c):this._s.add(c); },
      contains(c){ return this._s.has(c); },
    },
    _attrs: {},
    setAttribute(k, v){ this._attrs[k] = String(v); },
    getAttribute(k){ return this._attrs[k] != null ? this._attrs[k] : null; },
    removeAttribute(k){ delete this._attrs[k]; },
    addEventListener(){}, removeEventListener(){}, appendChild(){}, removeChild(){},
    querySelector(){ return null; }, querySelectorAll(){ return []; },
    getBoundingClientRect(){ return { width: 220, height: 40, top: 0, left: 0 }; },
    getContext(){ return make2dCtx(); },
    focus(){}, blur(){}, click(){}, insertBefore(){}, cloneNode(){ return makeEl(tag,id); },
  };
  // allow `el.onclick = fn` / `el.onclick` reads (plain writable property)
  e.onclick = null;
  return e;
}

// registry so $('#'+id) and (in principle) more selectors work
const byId = new Map();
function reg(id, el){ byId.set(id, el); return el; }
const canvasSel = new Set(["particles","donutCv","lineCv","tierCv","expCv"]);

function querySelector(sel) {
  if (sel[0] === "#") {
    const id = sel.slice(1);
    let el = byId.get(id);
    if (!el) { el = makeEl("div", id); reg(id, el); }
    return el;
  }
  // any other selector (tag etc.) -> fresh generic element
  return makeEl("div", "");
}

const allElements = [];
function querySelectorAll(sel) {
  if (sel === ".tab") {
    // the nav tabs; give them a data-s + a real addEventListener+querySelector
    return ["status","orch","solver","qas","hw","exp","tests"].map((s, i) => {
      const e = makeEl("div");
      e.dataset.s = s;
      e.addEventListener = (ev, fn) => { if (ev === "click") e._click = fn; };
      e.querySelector = () => null;
      e.onclick = null;
      return e;
    });
  }
  if (sel === ".section") {
    return Array.from(byId.values()).filter(el => {
      const t = el._attrs && (el._attrs["data-section"] || el._attrs["id"]);
      return /^s-/.test(el.id || "");
    });
  }
  return [];
}

const document = {
  hidden: false,
  querySelector, querySelectorAll,
  addEventListener(){}, removeEventListener(){},
  documentElement: { style: {} },
  body: makeEl("body", "body"),
  createElement(){ return makeEl("div"); },
};

const window = globalThis;
window.devicePixelRatio = 1;
window.innerWidth = 1280;
window.innerHeight = 800;
window.__DQ = { querySelector, querySelectorAll };

global.document = document;
global.window = window;
global.addEventListener = () => {};
global.navigator = { userAgent: "node-stub" };
global.location = { href: "http://127.0.0.1:8090/", search: "", hash: "" };

// bare identifier globals a browser provides late in the script run-time (the
// particle animation reads `innerWidth`/`innerHeight` directly in resize()).
global.innerWidth = 1280;
global.innerHeight = 800;

// fetch that never contacts a network: resolves a 404 so api() throws,
// which every loader is designed to tolerate (try/catch or .catch).
global.fetch = async () => {
  return { ok: false, status: 404, statusText: "offline",
           json: async () => ({ error: "offline stub" }) };
};
