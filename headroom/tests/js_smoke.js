// Smoke test for the page's inline script: run it against a stub DOM, then drive its controls.
// Usage: node js_smoke.js PAGE.html
// Prints one JSON object with the rendered text of the main sections. Exits non-zero on any thrown error.
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync(process.argv[2], 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (scripts.length !== 1) { console.error('expected exactly one inline script, found ' + scripts.length); process.exit(2); }

const els = {};
function mkEl(id) {
  let html = '';
  const e = {
    id, textContent: '', value: '', checked: true, hidden: false, attrs: {}, handlers: {}, kids: {},
    get innerHTML() { return html; },
    set innerHTML(v) { html = String(v); this.kids = {}; },   // a re-render drops the old child elements, as a real DOM does
    addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); },
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k]; },
    removeAttribute(k) { delete this.attrs[k]; },
    querySelectorAll(sel) {
      const out = [];
      const re = sel === '.chip' ? /class="chip" data-i="(\d+)"/g : sel === 'th[data-k]' ? /data-k="(\w+)"/g : null;
      if (!re) return out;
      let m;
      while ((m = re.exec(html))) {
        const key = sel + ':' + m[1];
        if (!this.kids[key]) { this.kids[key] = mkEl('child:' + key); this.kids[key].attrs[sel === '.chip' ? 'data-i' : 'data-k'] = m[1]; }
        out.push(this.kids[key]);
      }
      return out;
    },
  };
  return e;
}
const el = (id) => els[id] || (els[id] = mkEl(id));
const sandbox = {
  document: { getElementById: el, documentElement: { setAttribute() {}, removeAttribute() {} } },
  localStorage: { getItem() { return null; }, setItem() {} },
  console,
};
vm.createContext(sandbox);
try {
  vm.runInContext(scripts[0], sandbox, { filename: 'page-inline.js' });
  // drive the controls
  const fire = (id, type, ev) => (el(id).handlers[type] || []).forEach((f) => f(ev || { target: el(id) }));
  el('win').value = '7'; fire('win', 'change');
  el('metric').value = 'fresh'; fire('metric', 'change');
  el('metric').value = 'calls'; fire('metric', 'change');
  el('tcSched').checked = false; fire('tcSched', 'change');
  el('tcSched').checked = true; fire('tcSched', 'change');
  el('q').value = 'demo'; fire('q', 'input');
  el('q').value = ''; fire('q', 'input');
  el('theme').value = 'dark'; fire('theme', 'change');
  // click a session header to sort, and an account chip to hide then show it
  el('sessions').querySelectorAll('th[data-k]').forEach((h) => (h.handlers.click || []).forEach((f) => f()));
  [1, 2].forEach(() => el('acctChips').querySelectorAll('.chip').forEach((c) => (c.handlers.click || []).forEach((f) => f())));  // hide, then show again
} catch (e) {
  console.error('script error: ' + (e && e.stack || e));
  process.exit(1);
}
const keys = ['sub', 'notices', 'tiles', 'meters', 'meterNote', 'daily', 'hourly', 'ins', 'models', 'sessions', 'sessNote', 'about'];
const out = {};
keys.forEach((k) => { out[k] = (el(k).innerHTML || '') + (el(k).textContent || ''); });
console.log(JSON.stringify(out));
