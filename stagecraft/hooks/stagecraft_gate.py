#!/usr/bin/env python3
r"""stagecraft_gate: PreToolUse check that an HTML artifact page carries the Stagecraft.

Installed by the owner as a PreToolUse hook on the Artifact publish tool (matcher "^Artifact$" plus whatever publish tool a
headless route uses). It reads one JSON object on stdin ({"tool_name", "tool_input"}) and only looks at a publish of an
.html page: not a read, list, comment, asset upload or typed-Artifact call, not a Markdown file.

check.mode (0.2.0) comes from Stagecraft settings, read the way scripts/options.py reads them (the catalog default, then the
person's file ~/.stagecraft/options.json or the folder named in STAGECRAFT_HOME, then a project file
.claude/stagecraft.json in the working folder or any folder above it; later wins; no new dependency):
  remind  (the default) a page is published and what is missing is printed;
  refuse  as remind, and a page with a layout mistake (below) is also refused until it is fixed or marked exempt;
  off     the check does nothing.
A value that is not one of the three, or a settings file that cannot be read, means remind.

method.tab (0.3.2) comes from the same three layers:
  recommended  (the default) a page that shows data (a table with rows, a figure, a summary card, a trend mark or a data-through
               block) and has no filled Method tab gets a reminder;
  required     the same page is refused until the Method tab is there and filled;
  off          the Method tab is not mentioned.
A Method tab is filled when PB_CONFIG.tabs declares { id: "method" }, the page marks content data-pb-tab="method", and all seven
sections (ids method-purpose, method-derived, method-sources, method-assumed, method-limits, method-open, method-rebuild) are in
it with words besides their headings and table headers ("None" is words; an empty section is not). A tab declared in PB_CONFIG.tabs
with no content is reminded whatever method.tab says. check.mode off silences everything, as before.

Decision:
  * Refuses (permissionDecision "deny", with the exact missing mark and the fix) when a CORE mark is missing (not when check.mode is off):
      data-artifact-header   the header box
      data-ws                the theme on the root (the snippet sets it)
      data-playbook          the version, on <body> or on the first element of the header markup
      id="pb-options"        the Options panel
  * Layout mistakes visible in the page text without rendering it (references/layout.md) are reminders, and refusals when check.mode is refuse:
      a max-width in ch on a paragraph or intro class in the page's own style block while the page has a table or card grid
      (a block marked data-pb-measure is the author's choice and is not reminded);
      a table inside an element that scrolls on its own or has a maximum height;
      a fixed height in px on a block that holds text.
    The checks read the page's style blocks and inline style attributes only; a rule added by script is not seen.
  * (0.3.4) A page that carries the older artifact header of the parley skill (a second div#ah, a second detail slider id ah-rail, or a
    script with var AH = {...}) beside Stagecraft's own header shows two headers, two detail sliders and two Pin to top buttons. That is
    reported like the layout mistakes: a reminder, and a refusal when check.mode is refuse. The reminder names the fix
    (scripts/inject_stagecraft.py removes the older header and carries its author values over).
  * Everything else is a reminder: printed to stderr and returned as additionalContext, never a refusal, and no
    permission decision is made, so the normal permission flow is unchanged.
  * A page may carry <!-- stagecraft: exempt (reason) --> and is then let through untouched.
  * Every error fails open: a broken payload, an unreadable file or any exception allows the call.

One log line per decision goes to the path in the environment variable STAGECRAFT_GATE_LOG
(default: ~/.stagecraft/gate.log).
"""
import io
import json
import os
import re
import sys
import time
from html.parser import HTMLParser

EXEMPT = "stagecraft: exempt"
CORE = [
    ("data-artifact-header", re.compile(r"data-artifact-header")),
    ("data-ws", re.compile(r"data-ws")),
    ("data-playbook", re.compile(r"data-playbook\s*=")),
    ('id="pb-options"', re.compile(r"""id\s*=\s*["']pb-options["']""")),
]
HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(HERE, "..", "options", "catalog.json")
MODES = ("remind", "refuse", "off")
METHOD_MODES = ("required", "recommended", "off")
METHOD_IDS = ("purpose", "derived", "sources", "assumed", "limits", "open", "rebuild")
LOG = os.environ.get("STAGECRAFT_GATE_LOG") or os.path.join(os.path.expanduser("~"), ".stagecraft", "gate.log")
FIX = ("Copy the three marked parts of assets/stagecraft-snippet.html into the page (PB:STYLE and PB:HEADER first in "
       "the content, PB:SCRIPT last), define var PB_CONFIG before the script, then publish again. A page built by a script "
       "can run scripts/inject_stagecraft.py once after it is written. Only the page's owner exempts a page, with "
       "<!-- stagecraft: exempt (reason) -->.")


def _load(p):
    try:
        with io.open(p, encoding="utf-8") as fh:
            v = json.load(fh)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def read_setting(sid, allowed, fallback):
    """One setting: catalog default, then the person's file, then a project file; later wins. Anything unusable is the fallback."""
    val = fallback
    try:
        for o in _load(CATALOG).get("options", []):
            if o.get("id") == sid and o.get("default") in allowed:
                val = o["default"]
        base = os.environ.get("STAGECRAFT_HOME") or os.path.join(os.path.expanduser("~"), ".stagecraft")
        v = _load(os.path.join(base, "options.json")).get("values", {})
        if isinstance(v, dict) and v.get(sid) in allowed:
            val = v[sid]
        d = os.getcwd()
        while True:
            pp = os.path.join(d, ".claude", "stagecraft.json")
            if os.path.isfile(pp):
                v = _load(pp).get("values", {})
                if isinstance(v, dict) and v.get(sid) in allowed:
                    val = v[sid]
                break
            up = os.path.dirname(d)
            if up == d:
                break
            d = up
    except Exception:
        pass
    return val


def check_mode():
    """check.mode: catalog default, then the person's file, then a project file; later wins. Anything unusable is remind."""
    return read_setting("check.mode", MODES, "remind")


def method_mode():
    """method.tab: the same three layers. Anything unusable is recommended."""
    return read_setting("method.tab", METHOD_MODES, "recommended")


TEXTSEL = re.compile(r"(?<![\w-])(p|intro|lede|lead|subtitle|summary|blurb|description|standfirst)(?![\w-])")
TEXTBOX = re.compile(r"(?<![\w-])(p|intro|lede|lead|summary|blurb|description|note|notes|card|box|panel|article|section|text|body|content|callout|alert|banner|hero)(?![\w-])")
HAS_GRID = re.compile(r"<table\b|class\s*=\s*[\"'][^\"']*\b(pb-cards|pb-grid|cards?|grid)\b|display\s*:\s*grid", re.I)
SCROLLY = r"(overflow(?:-x|-y)?\s*:\s*(?:auto|scroll)|max-height\s*:\s*[^;\"']+)"


def css_rules(text):
    """(selector, body) of every rule in the page's own style blocks (media blocks included, flattened)."""
    out = []
    for blk in re.findall(r"<style[^>]*>(.*?)</style>", text, re.S | re.I):
        blk = re.sub(r"/\*.*?\*/", "", blk, flags=re.S)
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", blk):
            out.append((m.group(1).strip(), m.group(2)))
    return out


OLD_HEADER_FIX = ("The page carries the older artifact header of the parley skill (a second header box, a second detail slider with its own Pin to top button, "
                  "or a script with var AH = {...}) beside Stagecraft's own header: two headers, two sliders and two Pin to top buttons on one page. Stagecraft replaces the "
                  "older header, so a page never carries both. Run python scripts/inject_stagecraft.py <page> once: it removes the older header (its style block, header box, "
                  "slider and script) and carries its author values (seat, session, account, headless, questions, published, period) into PB_CONFIG.header. "
                  "Or delete those four parts by hand.")


def double_header(text):
    """0.3.4: one reminder when a Stagecraft page also carries the older header of the parley skill, else []. Stagecraft's own script is left out of the reading."""
    rest = re.sub(r"<!-- PB:SCRIPT -->\s*<script>.*?</script>", "", text, flags=re.S)
    if not (re.search(r"data-playbook\s*=", rest) and re.search(r"""id\s*=\s*["']pb-options["']""", rest)):
        return []   # not a Stagecraft page: the missing core marks are reported on their own
    boxes = len(re.findall(r"""\bid\s*=\s*["']ah["']""", rest))
    rails = len(re.findall(r"""\bid\s*=\s*["']ah-rail["']""", rest))
    if boxes > 1 or rails > 1 or re.search(r"\bvar\s+AH\s*=\s*\{", rest):
        return [OLD_HEADER_FIX]
    return []


def layout_reminders(text):
    """Layout mistakes visible in the text of the page (style blocks and inline style attributes), without rendering it."""
    out = []
    rules = css_rules(text)
    if HAS_GRID.search(text) and "data-pb-measure" not in text:
        for sel, body in rules:
            if re.search(r"(?<![\w-])max-width\s*:\s*[\d.]+ch\b", body) and TEXTSEL.search(sel):
                out.append("A max-width in ch on a paragraph or intro class (%s) while the page has a table or card grid: held to a "
                           "reading width above full-width content it becomes a narrow strip with an empty half beside it. Let it run the "
                           "width of its block, put it beside something in a pb-row, or mark it data-pb-measure if the line length is on purpose." % sel[:60])
                break
    wrapped = False
    for sel, body in rules:
        for cm in re.finditer(r"\.([A-Za-z_][\w-]*)", sel):
            if re.search(SCROLLY, body) and re.search(r"class\s*=\s*[\"'][^\"']*\b%s\b[^\"']*[\"'][^>]*>(?:(?!</div>|</section>).)*?<table\b" % re.escape(cm.group(1)), text, re.S | re.I):
                wrapped = True
    if wrapped or re.search(r"<(?:div|section|article|figure|details)\b[^>]*style\s*=\s*[\"'][^\"']*" + SCROLLY + r"[^\"']*[\"'][^>]*>(?:(?!</div>|</section>).)*?<table\b", text, re.S | re.I):
        out.append("A table sits inside an element that scrolls on its own or has a maximum height: a table is never put in its own scroll "
                   "box. Filter a long table, hide low-priority columns (data-priority) and let the page scroll.")
    fixed = False
    for sel, body in rules:
        if re.search(r"(?<![\w-])height\s*:\s*\d+px", body) and TEXTBOX.search(sel):
            fixed = True
    if fixed or re.search(r"<(?:p|div|section|article|li|td|span)\b[^>]*style\s*=\s*[\"'][^\"']*(?<![\w-])height\s*:\s*\d+px[^\"']*[\"'][^>]*>\s*[^<\s]", text, re.I):
        out.append("A fixed height in px on a block that holds text: more text than expected is clipped or spills. Let the block take the "
                   "height its text needs (min-height is fine).")
    return out


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
HEADS = {"h1", "h2", "h3", "h4", "h5", "h6", "thead", "caption"}
SKIPT = {"script", "style", "template"}
TAB_MEDIA = {"img", "svg", "canvas", "video", "iframe", "table", "input", "textarea"}
METH_MEDIA = {"img", "svg", "canvas", "video", "iframe"}
PLACEHOLDER = re.compile(r"^(todo|tbd|\.\.\.|…|fill in( here)?\.?)$", re.I)


class PageScan(HTMLParser):
    """The content of every data-pb-tab block and of the seven Method sections, read from the page source: the words outside
    headings, table headers and captions, and whether there is any media. (The page's own words, as an agent reading only
    the source would see them: nothing here comes from running the page.)"""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []          # (tag, [collector keys opened here])
        self.skip = 0
        self.noise = 0
        self.tabs = {}           # tab id -> {"text": str, "media": bool}
        self.method = {}         # section name -> {"text": str, "media": bool, "in_tab": bool}
        self.active = []         # (kind, name)

    def _col(self, kind, name):
        d = self.tabs if kind == "tab" else self.method
        if name not in d:
            d[name] = {"text": "", "media": False, "in_tab": False}
        return d[name]

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        opened = []
        if tag not in SKIPT and not self.skip:
            tid = a.get("data-pb-tab")
            if tid:
                self._col("tab", tid.strip()); opened.append(("tab", tid.strip()))
            sid = (a.get("id") or "").strip()
            if sid.startswith("method-") and sid[7:] in METHOD_IDS:
                c = self._col("method", sid[7:])
                c["in_tab"] = c["in_tab"] or any(k == "tab" and n == "method" for k, n in self.active + opened)
                opened.append(("method", sid[7:]))
            if not self.noise:
                for k, n in self.active + opened:
                    if k == "tab" and tag in TAB_MEDIA:
                        self._col("tab", n)["media"] = True
                    if k == "method" and tag in METH_MEDIA:
                        self._col("method", n)["media"] = True
        if tag in VOID:
            return
        self.stack.append((tag, opened))
        self.active += opened
        if tag in SKIPT:
            self.skip += 1
        if tag in HEADS:
            self.noise += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                while len(self.stack) > i:
                    tg, opened = self.stack.pop()
                    for o in opened:
                        if o in self.active:
                            self.active.remove(o)
                    if tg in SKIPT:
                        self.skip = max(0, self.skip - 1)
                    if tg in HEADS:
                        self.noise = max(0, self.noise - 1)
                return

    def handle_data(self, data):
        if self.skip or self.noise or not data.strip():
            return
        for k, n in self.active:
            c = self._col(k, n)
            c["text"] += " " + data


def scan_page(text):
    s = PageScan()
    try:
        s.feed(text)
        s.close()
    except Exception:
        pass
    return s


def declared_tabs(text):
    """The ids in PB_CONFIG.tabs (a list of { id, label }), or []. Read from the page's own script."""
    m = re.search(r"(?<![\w-])tabs[\"']?\s*:\s*\[", text)   # a key may be written quoted, as inject_stagecraft.py writes it
    if not m:
        return []
    depth, i = 0, m.end() - 1
    while i < len(text):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return re.findall(r"""\bid["']?\s*:\s*["']([a-z][a-z0-9_-]*)["']""", text[m.end():i])


def words_in(c):
    txt = re.sub(r"\s+", " ", c["text"]).strip()
    if PLACEHOLDER.match(txt):
        return False
    return bool(re.search(r"[A-Za-z0-9]", txt)) or bool(c["media"])


def tab_reminders(text, scan=None, ids=None):
    """Reminders about named tabs: a declared tab with no content, and content that names a tab nobody declared."""
    out = []
    ids = declared_tabs(text) if ids is None else ids
    if len(ids) < 2:
        return out
    scan = scan or scan_page(text)
    for i in ids:
        c = scan.tabs.get(i)
        if c is None:
            out.append('Tab "%s" is declared in PB_CONFIG.tabs but no block of the page carries data-pb-tab="%s": add its content or take it out of the list.' % (i, i))
        elif not (c["text"].strip() or c["media"]):
            out.append('Tab "%s" is declared in PB_CONFIG.tabs but has no content (only headings or nothing at all): fill it or take it out of the list.' % i)
    for i in scan.tabs:
        if i not in ids:
            out.append('A block carries data-pb-tab="%s" but PB_CONFIG.tabs does not declare that tab, so the block stays above the tabs.' % i)
    return out


DATA_RE = re.compile(r"<table\b(?:(?!</table>).)*?<td\b|data-(?:money|pct|int|total|spark|series)\b|class\s*=\s*[\"'][^\"']*\bpb-cards?\b|(?<![\w-])sources[\"']?\s*:\s*\[\s*\{", re.S | re.I)


def shows_data(text):
    return bool(DATA_RE.search(text))


def method_state(text, scan=None, ids=None):
    """(declared, missing, empty): is the Method tab declared and marked, which of the seven sections are absent, which are empty."""
    ids = declared_tabs(text) if ids is None else ids
    scan = scan or scan_page(text)
    declared = "method" in ids and "method" in scan.tabs
    missing, empty = [], []
    for n in METHOD_IDS:
        c = scan.method.get(n)
        if c is None or not c["in_tab"]:
            missing.append(n)
        elif not words_in(c):
            empty.append(n)
    return declared, missing, empty


def method_problem(text, scan=None, ids=None):
    """None when the Method tab is there and filled, otherwise one sentence saying what is wrong."""
    declared, missing, empty = method_state(text, scan, ids)
    if not declared:
        return ('The page shows data but has no Method tab: declare { id: "method", label: "Method" } in PB_CONFIG.tabs and put the seven fixed '
                "sections (assets/method-skeleton.html) in the page as plain text, with data-pb-tab=\"method\", so that a reader or an agent with no context "
                "and no tools can see how each figure was derived, where the sources are, and which values were typed in or assumed.")
    if missing or empty:
        return ("The Method tab has sections that are %s%s%s. Each of the seven sections needs words of its own in the page source; a section that "
                'does not apply says "None".' % (("missing (" + ", ".join(missing) + ")") if missing else "", " and " if missing and empty else "", ("empty (" + ", ".join(empty) + ")") if empty else ""))
    return None


def log(decision, tool, path, why=""):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with io.open(LOG, "a", encoding="utf-8") as fh:
            fh.write("%s %s %s %s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), decision, tool, path, why))
    except Exception:
        pass


def page_text(tool, ti):
    """(path, text) of the page being published, or (None, None) when this call is not an HTML page publish."""
    if tool == "Artifact":
        if (ti.get("action") or "publish") != "publish" or ti.get("asset") or ti.get("type_url"):
            return None, None
        path = ti.get("file_path") or ""
        if not path.lower().endswith((".html", ".htm")):
            return None, None
        return path, io.open(path, encoding="utf-8", errors="replace").read()
    if "publish" not in tool.lower():
        return None, None
    for k in ("html", "content", "body"):
        if isinstance(ti.get(k), str) and "<" in ti[k]:
            return "(inline %s)" % k, ti[k]
    for k in ("file_path", "path", "filePath"):
        p = ti.get(k)
        if isinstance(p, str) and p.lower().endswith((".html", ".htm")) and os.path.isfile(p):
            return p, io.open(p, encoding="utf-8", errors="replace").read()
    return None, None


def reminders(text, ti):
    out = []
    # Stagecraft's own style and script are not the page author's work: judge the page without them
    text = re.sub(r"<!-- PB:STYLE -->\s*<style>.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<!-- PB:SCRIPT -->\s*<script>.*?</script>", "", text, flags=re.S)
    if "PB_CONFIG" not in text:
        out.append("No PB_CONFIG object: define var PB_CONFIG = {key, header, log, ...} before Stagecraft script so the "
                   "header, the Log tab and the per-page option keys are filled.")
    else:
        if not re.search(r"""session["']?\s*:\s*["'][^"']{8,}""", text):
            out.append("PB_CONFIG.header.session is empty: put the authoring session's full id there, with seat, account, "
                       "headless and questions.")
        if not re.search(r"\blog[\"']?\s*:", text):
            out.append("PB_CONFIG.log is missing: pass {qa: [...], versions: [...]} so the Log tab shows what was asked and "
                       "changed, or log: false to leave the tab out.")
        if not re.search(r"""\bkey["']?\s*:\s*["'][^"']""", text):
            out.append("PB_CONFIG.key is missing: without it the stored options are keyed by the page title.")
    if not re.search(r"""class\s*=\s*["'][^"']*\bl[123]\b""", text):
        out.append("No block is tagged l1, l2 or l3: tag secondary content with the lowest detail level that shows it and say "
                   "in one line near the top what each level adds.")
    if re.search(r"overflow(-x|-y)?\s*:\s*(auto|scroll)", text) and "<table" in text:
        out.append("An overflow auto or scroll rule is in the page: tables must not sit in a scroll box; Stagecraft fits "
                   "them to the width and hides low-priority columns instead.")
    for m in re.finditer(r"<table\b[^>]*>(.*?)</table>", text, re.S | re.I):
        if len(re.findall(r"<th\b", m.group(1), re.I)) >= 6 and "data-priority" not in m.group(1):
            out.append("A table with six or more columns has no data-priority on any header: say which columns can be hidden "
                       "first on a narrow screen (highest number goes first).")
            break
    if not re.search(r"<title>\s*\S", text, re.I) and "<head" not in text.lower():
        out.append("No <title>: give the page a two to four word name.")
    if "claude:viewport-fit-sides" not in text:
        out.append('Add <meta name="claude:viewport-fit-sides" content="cover"> beside the title (Stagecraft shell already '
                   "uses the 16 px safe-area gutters it promises).")
    uses_db = bool(re.search(r"data-pb-rulings|class\s*=\s*[\"'][^\"']*pb-ask", text))
    caps = ti.get("capabilities")
    if isinstance(caps, dict):
        need = [n for n in ("db", "user", "comments") if n not in caps]
        if need and uses_db:
            out.append("The page has rulings or ask cards but capabilities lack: %s. Rulings need db and user (scope profile); "
                       "answers and comments need comments; without them those parts are read-only." % ", ".join(need))
        elif "db" not in caps:
            out.append("capabilities lack db: the header cannot read the author heartbeat and options will not follow the "
                       "viewer across browsers.")
    return out


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw or "{}")
        tool = data.get("tool_name") or ""
        ti = data.get("tool_input") or {}
        if not isinstance(ti, dict):
            raise ValueError("tool_input is not an object")
        path, text = page_text(tool, ti)
        if text is None:
            return 0
        if EXEMPT in text:
            log("ALLOW", tool, path, "exempt")
            return 0
        mode = check_mode()
        if mode == "off":
            log("ALLOW", tool, path, "check.mode off")
            return 0
        missing = [name for name, rx in CORE if not rx.search(text)]
        if missing:
            log("DENY", tool, path, "missing " + " ".join(missing))
            reason = ("Stagecraft mark missing: %s. Every artifact page carries Stagecraft: the header box "
                      "(data-artifact-header), the theme on the root (data-ws), the version (data-playbook) and the Options "
                      "panel (id=\"pb-options\"). %s" % (", ".join(missing), FIX))
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                                "permissionDecisionReason": reason}}))
            return 0
        rem = reminders(text, ti)
        lay = layout_reminders(re.sub(r"<!-- PB:STYLE -->\s*<style>.*?</style>", "", re.sub(r"<!-- PB:SCRIPT -->\s*<script>.*?</script>", "", text, flags=re.S), flags=re.S))
        dbl = double_header(text)
        lay = lay + dbl
        rem += lay
        body = re.sub(r"<!-- PB:STYLE -->\s*<style>.*?</style>", "", re.sub(r"<!-- PB:SCRIPT -->\s*<script>.*?</script>", "", text, flags=re.S), flags=re.S)
        ids = declared_tabs(body)
        scan = scan_page(body)
        rem += tab_reminders(body, scan, ids)
        mm, mprob = method_mode(), None
        if mm != "off" and shows_data(body):
            mprob = method_problem(body, scan, ids)
            if mprob and mm == "recommended":
                rem.append(mprob + " (method.tab is recommended: this is a reminder.)")
        why = []
        if mode == "refuse" and lay:
            why.append("Stagecraft layout mistake (check.mode is refuse): " + " | ".join(lay) + " Fix the page, or mark it <!-- stagecraft: exempt (reason) --> if the owner agrees.")
        if mm == "required" and mprob:
            why.append("Stagecraft Method tab missing (method.tab is required): " + mprob + " Or mark the page <!-- stagecraft: exempt (reason) --> if the owner agrees.")
        if why:
            log("DENY", tool, path, "%s%s" % ("check.mode refuse; %d layout mistake(s) " % len(lay) if mode == "refuse" and lay else "", "method.tab required; Method tab missing or empty" if mm == "required" and mprob else ""))
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                                "permissionDecisionReason": " | ".join(why)}}))
            return 0
        log("ALLOW", tool, path, "core marks present; %d reminder(s)" % len(rem))
        if rem:
            msg = "Stagecraft reminders (the publish is allowed):\n- " + "\n- ".join(rem)
            sys.stderr.write(msg + "\n")
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}))
    except Exception as e:  # fail open: the gate never blocks because it broke
        log("ERROR", "?", "?", e.__class__.__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
