#!/usr/bin/env python3
r"""inject_stagecraft: add the Stagecraft snippet to an HTML page that another script built.

For page builders that cannot paste the snippet by hand (a script that writes the page, a headless publish). Call it once
after the page is written:

    python inject_stagecraft.py <page.html> [--out <new.html>] [--seat NAME] [--session UUID] [--account NAME]
        [--headless] [--questions URL] [--published "YYYY-MM-DD HH:MM"] [--period-min 50] [--key KEY] [--snippet PATH]
        [--defaults-json FILE]

It is idempotent: a page that already carries data-playbook and an element with id pb-options is left alone (exit 0).
The style and the header markup go first in the page content (right after <body ...> when there is one, otherwise after the
leading title, meta, link and style tags). If the page does not define PB_CONFIG, a small config script is added just
before Stagecraft script, which goes last (before </body> when there is one). Without --out the page is changed in place.
Page defaults (0.2.0): the reader's settings go into PB_CONFIG.defaults. They come from `options.py page-config` (the three-layer
read: catalog, the person's file, a project file) unless --defaults-json names a file holding that JSON object. A page that
defines PB_CONFIG without a defaults key gets one extra line, PB_CONFIG.defaults = PB_CONFIG.defaults || {...}, before the
Stagecraft script; a page that already has a defaults key is not touched. If the settings cannot be read the page is injected
without defaults (Stagecraft then uses the catalog defaults) and a note says so.

The older header (0.3.4). Stagecraft replaces the artifact header of the parley skill (its style block, its header box and detail
slider, its script with `var AH = {...}`; both use the element ids ah, ah-rail, ah-lvl and ah-pin). A page carrying both shows two
headers, two sliders and two Pin to top buttons, so this script REMOVES the older header, whether the page has Stagecraft yet or
not, and carries its author values (seat, session, home as the account, headless, questions, published, period_min) into
PB_CONFIG.header: a value the page already gives there wins; a value given on the command line beats the older header's. A page
with Stagecraft and the older header is repaired (the older header goes, nothing else changes). If the older header cannot be found
whole (a style block, a header box, a slider and a script that holds `var AH` and nothing else but its own function) nothing is
changed and the script exits 1 with a message that says what it found. Running it twice changes nothing the second time.
Exit 0 on success or no-op, 1 on error.
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SNIPPET = os.path.join(HERE, "..", "assets", "stagecraft-snippet.html")
LEADING = re.compile(r"\A(\s*(?:<!--.*?-->|<title>.*?</title>|<meta[^>]*>|<link[^>]*>|<style[^>]*>.*?</style>)\s*)*",
                     re.S | re.I)


class OldHeaderPartial(Exception):
    """The older header is there but cannot be found whole, so nothing is removed."""


def part(text, name):
    m = re.search(r"<!-- PB:%s -->\s*(.*?)\s*<!-- /PB:%s -->" % (name, name), text, re.S)
    if not m:
        raise ValueError("marked part PB:%s not found in the snippet" % name)
    return m.group(1)


def read_defaults(path):
    """The page defaults as a dict, or None when they cannot be read."""
    try:
        if path:
            data = json.load(io.open(path, encoding="utf-8"))
        else:
            r = subprocess.run([sys.executable, "-I", "-B", os.path.join(HERE, "options.py"), "page-config"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if r.returncode != 0:
                return None
            data = json.loads(r.stdout.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ---------------------------------------------------------------- the older header (parley artifact-header snippet)
def stagecraft_zones(text):
    """Character spans that belong to Stagecraft's own parts, so they are never taken for the older header: the style block and the script block after their
    PB:STYLE and PB:SCRIPT marks, and the div#pb-top after the PB:HEADER mark (the injector writes the opening marks only; the demo has both)."""
    zones = []
    for n in ("STYLE", "SCRIPT"):
        m = re.search(r"<!-- PB:%s -->\s*<%s\b[^>]*>.*?</%s>" % (n, n.lower(), n.lower()), text, re.S)
        if m:
            zones.append(m.span())
    m = re.search(r"<!-- PB:HEADER -->\s*(<div\b[^>]*\bid\s*=\s*[\"']pb-top[\"'][^>]*>)", text)
    if m:
        e = div_end(text, m.start(1))
        if e:
            zones.append((m.start(), e))
    return zones


def in_zone(zones, i):
    return any(a <= i < b for a, b in zones)


def div_end(text, start):
    """The end (just past the closing tag) of the div that opens at start, counting nested divs; None when it never closes."""
    depth = 0
    for m in re.finditer(r"<(/?)div\b[^>]*>", text[start:], re.I):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return start + m.end()
    return None


def js_string(tok):
    if tok[0] == '"':
        return json.loads(tok)
    body = tok[1:-1].replace('\\"', '"').replace("\\'", "'").replace('"', '\\"')
    return json.loads('"' + body + '"')


def js_object_end(s, i):
    """The index of the } that closes the { at s[i], skipping strings and comments; -1 when it never closes."""
    depth, k, n = 0, i, len(s)
    while k < n:
        c = s[k]
        if c in "\"'":
            q = c
            k += 1
            while k < n and s[k] != q:
                k += 2 if s[k] == "\\" else 1
        elif s.startswith("/*", k):
            e = s.find("*/", k + 2)
            if e < 0:
                return -1
            k = e + 1
        elif s.startswith("//", k):
            e = s.find("\n", k)
            if e < 0:
                return -1
            k = e
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return k
        k += 1
    return -1


def parse_ah(body):
    """The plain values of the AH object (the text between its braces): {key: str | bool | int | None}. A value that is not a plain one is an error."""
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    out, i, n = {}, 0, len(body)
    pair = re.compile(r"\s*,?\s*([A-Za-z_$][\w$]*|\"[^\"]*\"|'[^']*')\s*:\s*")
    value = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|true|false|null|-?\d+(?:\.\d+)?")
    while i < n:
        if not body[i:].strip() or re.fullmatch(r"\s*,\s*", body[i:]):
            break
        m = pair.match(body, i)
        if not m:
            raise OldHeaderPartial("the AH object holds something that is not a key and a plain value: %r" % body[i:i + 40].strip())
        key = m.group(1).strip("\"'")
        v = value.match(body, m.end())
        if not v:
            raise OldHeaderPartial("AH.%s is not a plain value (a string, true, false, null or a number): %r" % (key, body[m.end():m.end() + 40].strip()))
        t = v.group(0)
        out[key] = js_string(t) if t[0] in "\"'" else (True if t == "true" else False if t == "false" else None if t == "null" else (float(t) if "." in t else int(t)))
        i = v.end()
        if not re.match(r"\s*(,|$)", body[i:]):
            raise OldHeaderPartial("after AH.%s comes %r, not a comma" % (key, body[i:i + 30].strip()))
    return out


def find_old_header(text):
    """None when the page carries no older header. Otherwise (spans to remove, author values); raises OldHeaderPartial when it is there but not whole."""
    zones = stagecraft_zones(text)
    # Stagecraft's own header is inside its marked header; without markers, inside the div#pb-top
    pbtop = re.search(r"<div\b[^>]*\bid\s*=\s*[\"']pb-top[\"'][^>]*>", text, re.I)
    if pbtop and not in_zone(zones, pbtop.start()):
        e = div_end(text, pbtop.start())
        if e:
            zones.append((pbtop.start(), e))
    styles = [m for m in re.finditer(r"<style\b[^>]*>(.*?)</style>", text, re.S | re.I) if not in_zone(zones, m.start()) and ".ah-rail" in m.group(1)]
    boxes = [m for m in re.finditer(r"<div\b[^>]*\bid\s*=\s*[\"']ah[\"'][^>]*>", text, re.I) if not in_zone(zones, m.start())]
    rails = [m for m in re.finditer(r"<div\b[^>]*\bid\s*=\s*[\"']ah-rail[\"'][^>]*>", text, re.I) if not in_zone(zones, m.start())]
    scripts = [m for m in re.finditer(r"<script\b[^>]*>(.*?)</script>", text, re.S | re.I) if not in_zone(zones, m.start()) and re.search(r"\bvar\s+AH\s*=", m.group(1))]
    if not (styles or boxes or rails or scripts):
        return None
    found = "style block %d, header box %d, detail slider %d, script with var AH %d" % (len(styles), len(boxes), len(rails), len(scripts))
    if len(styles) != 1 or len(boxes) != 1 or len(rails) != 1 or len(scripts) != 1:
        raise OldHeaderPartial("the older header is not there whole (found: %s; one of each is needed)" % found)
    spans = []
    st = styles[0]
    a = st.start()
    pre = re.search(r"<!--\s*Artifact header \(parley skill(?:(?!-->).)*-->\s*\Z", text[:a], re.S)   # the comment a hand paste brings
    spans.append((pre.start() if pre else a, st.end()))
    be = div_end(text, boxes[0].start())
    re_ = div_end(text, rails[0].start())
    if be is None or re_ is None:
        raise OldHeaderPartial("the older header box or slider does not close (found: %s)" % found)
    spans.append((boxes[0].start(), be))
    spans.append((rails[0].start(), re_))
    sc = scripts[0]
    code = sc.group(1)
    k = re.search(r"\bvar\s+AH\s*=\s*\{", code)
    before = re.sub(r"/\*.*?\*/", "", code[:k.start()], flags=re.S)
    before = re.sub(r"(?m)^\s*//.*$", "", before)
    if before.strip():
        raise OldHeaderPartial("the script that holds var AH also holds other code before it, so it cannot be removed whole: %r" % before.strip()[:60])
    oe = js_object_end(code, k.end() - 1)
    if oe < 0:
        raise OldHeaderPartial("the AH object in the older header's script does not close")
    ah = parse_ah(code[k.end():oe])
    rest = code[oe + 1:].lstrip()
    rest = rest[1:].lstrip() if rest.startswith(";") else rest
    if not (re.match(r"\(\s*function\s*\(\s*\)\s*\{", rest) and re.search(r"\}\s*\)\s*\(\s*\)\s*;?\s*\Z", rest.rstrip()) and "ah-rail" in rest):
        raise OldHeaderPartial("the script that holds var AH does not end with the header's own function, so it cannot be removed whole")
    spans.append((sc.start(), sc.end()))
    return spans, ah


def remove_spans(text, spans):
    for a, b in sorted(spans, reverse=True):
        m = re.match(r"[ \t]*\r?\n", text[b:])   # take the line break after the removed part when that leaves an empty line
        if m and (a == 0 or text[a - 1] in "\r\n"):
            b += m.end()
        text = text[:a] + text[b:]
    return text


def carried(ah):
    """The author values of an older header, as PB_CONFIG.header keys; the older header's home (a colour) stands in for the account."""
    h = {}
    for k in ("seat", "session", "questions", "published"):
        if isinstance(ah.get(k), str):
            h[k] = ah[k]
    acct = ah.get("account") if isinstance(ah.get("account"), str) and ah.get("account") else ah.get("home")
    if isinstance(acct, str) and acct:
        h["account"] = acct
    if isinstance(ah.get("headless"), bool):
        h["headless"] = ah["headless"]
    pm = ah.get("period_min", ah.get("period"))
    if isinstance(pm, (int, float)) and not isinstance(pm, bool) and pm > 0:
        h["period_min"] = int(pm)
    return h


def jsdump(v, **kw):
    return json.dumps(v, **kw).replace("</", "<\\/")


def carry_script(fix, detail_off, have_config):
    """The script that puts the older header's author values into PB_CONFIG: the page's own values win."""
    if not have_config:
        conf = {"header": fix}
        if detail_off:
            conf["detail"] = False
        return "<script>\nvar PB_CONFIG = %s;\n</script>\n" % jsdump(conf, indent=2)
    return ("<script>\n/* author values carried over from the older header by inject_stagecraft.py; the page's own values win */\n"
            "PB_CONFIG.header = Object.assign(%s, PB_CONFIG.header);\n%s</script>\n"
            % (jsdump(fix), "if (PB_CONFIG.detail === undefined) PB_CONFIG.detail = false;\n" if detail_off else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Add the Stagecraft snippet to an HTML page.")
    ap.add_argument("page")
    ap.add_argument("--out", default="")
    ap.add_argument("--snippet", default=os.environ.get("STAGECRAFT_SNIPPET", DEFAULT_SNIPPET))
    ap.add_argument("--seat", default="")
    ap.add_argument("--session", default="")
    ap.add_argument("--account", default="")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--questions", default="")
    ap.add_argument("--published", default="")
    ap.add_argument("--period-min", type=int, default=None)
    ap.add_argument("--key", default="")
    ap.add_argument("--defaults-json", default="")
    a = ap.parse_args(argv)
    try:
        text = io.open(a.page, encoding="utf-8").read()
        dest = a.out or a.page
        has_sc = "data-playbook" in text and re.search(r"""id\s*=\s*["']pb-options["']""", text)
        old = find_old_header(text)   # raises OldHeaderPartial before anything is changed
        old_note = ""
        if old:
            text = remove_spans(text, old[0])
            old_note = "removed the older header (style block, header box, detail slider and script) and carried its author values into PB_CONFIG.header"
            if re.search(r"BEGIN Log tab scaffold", text):
                old_note += "; note: the older Log tab scaffold (parley part 4) is also in this page and was left alone, Stagecraft builds its own Log tab"
        if has_sc:
            if not old:
                print("unchanged: %s already carries Stagecraft" % a.page)
                if a.out:
                    io.open(a.out, "w", encoding="utf-8", newline="").write(text)
                return 0
            own = re.sub(r"<!-- PB:(STYLE|SCRIPT) -->\s*<(style|script)\b[^>]*>.*?</>", "", text, flags=re.S)   # the page's own text, without Stagecraft's style and script
            cfg = carry_script(carried(old[1]), old[1].get("detail") is False, "PB_CONFIG" in own)
            at = text.find("<!-- PB:SCRIPT -->")
            if at < 0:
                at = text.lower().rfind("</body>")
            text = (text[:at] + cfg + text[at:]) if at >= 0 else (text.rstrip() + "\n" + cfg)
            io.open(dest, "w", encoding="utf-8", newline="").write(text)
            print("repaired: %s -> %s; %s" % (a.page, dest, old_note))
            return 0
        snip = io.open(a.snippet, encoding="utf-8").read()
        style, header, script = part(snip, "STYLE"), part(snip, "HEADER"), part(snip, "SCRIPT")
        cfg = ""
        defaults = read_defaults(a.defaults_json)
        if defaults is None:
            print("note: the settings could not be read, so no defaults were written; Stagecraft uses its own defaults.")
        fix = carried(old[1]) if old else {}
        if "PB_CONFIG" not in text:
            h = {"seat": "unknown author", "session": "", "account": "", "headless": False, "questions": "", "published": "", "period_min": 50}
            h.update(fix)   # the older header's values beat the defaults, a value given on the command line beats both
            for k, v in (("seat", a.seat), ("session", a.session), ("account", a.account), ("questions", a.questions), ("published", a.published)):
                if v:
                    h[k] = v
            if a.headless:
                h["headless"] = True
            if a.period_min is not None:
                h["period_min"] = a.period_min
            if not h["session"] and h["headless"]:
                h["session"] = "headless run, no live session"
            if not h["published"]:
                h["published"] = time.strftime("%Y-%m-%d %H:%M")
            conf = {"header": h}
            if old and old[1].get("detail") is False:
                conf["detail"] = False
            if defaults is not None:
                conf["defaults"] = defaults
            if a.key:
                conf["key"] = a.key
            cfg = "<script>\nvar PB_CONFIG = %s;\n</script>\n" % jsdump(conf, indent=2)
        else:
            if old:
                cfg += carry_script(fix, old[1].get("detail") is False, True)
            if defaults is not None and not re.search(r"(\bdefaults[\"']?\s*:\s*\{|PB_CONFIG\.defaults\s*=)", text):
                cfg += "<script>\nPB_CONFIG.defaults = PB_CONFIG.defaults || %s;\n</script>\n" % jsdump(defaults)
        top = "<!-- PB:STYLE -->\n" + style + "\n<!-- PB:HEADER -->\n" + header + "\n"
        bottom = cfg + "<!-- PB:SCRIPT -->\n" + script + "\n"
        body = re.search(r"<body[^>]*>", text, re.I)
        at = body.end() if body else LEADING.match(text).end()
        text = text[:at] + "\n" + top + text[at:]
        end = text.lower().rfind("</body>")
        text = (text[:end] + bottom + text[end:]) if end >= 0 else (text.rstrip() + "\n" + bottom)
        io.open(dest, "w", encoding="utf-8", newline="").write(text)
        print("injected: %s -> %s" % (a.page, dest))
        if old_note:
            print(old_note)
        if a.headless:
            print("note: headless page; declare no capabilities, the status box will say the author is not watching.")
        else:
            print("publish: declare capabilities db, user (scope profile) and comments so rulings, answers, "
                  "option mirroring and comments work; without them those parts are read-only.")
        return 0
    except OldHeaderPartial as e:
        print("ERROR: %s. Nothing was changed. Remove the older header by hand (its style block, its header box and detail slider, and "
              "the script that holds var AH), or keep the page as it is and do not add Stagecraft to it." % e, file=sys.stderr)
        return 1
    except Exception as e:  # report, never a traceback
        print("ERROR: %s: %s" % (e.__class__.__name__, e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
