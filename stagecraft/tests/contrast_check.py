#!/usr/bin/env python3
r"""contrast_check: compute the contrast of the palette in assets/stagecraft-snippet.html and fail under the floor.

    python -I -B tests/contrast_check.py [path-to-snippet]

It parses the color tokens out of the snippet's style block (the light set on :root and :root[data-ws="default"], the dark
set in the prefers-color-scheme media rule and in the explicit dark rules) and checks, for each set:
  text tokens (--fg --muted --accent --ask --ok --warn) on --bg and on --surface: at least 7:1
  --line on --bg and on --surface: at least 3:1
  and the pairings the components use: --accent on --accent-soft, --ask on --ask-soft, --warn on --warn-soft,
  --bg on --accent (a pressed button), --bg on --fg (the toast): at least 7:1.
0.2.0 adds two more checks:
  reader.contrast "standard": the rules on :root[data-contrast="standard"] are laid over each palette and the same text pairs
  must reach 4.5:1 (the floor of that setting);
  the six workspace colours (--ws-orange and the others, a stripe on the header box) must reach 3:1 on --bg and --surface in both themes.
Exit 0 when every pair passes, 1 otherwise.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "..", "assets", "stagecraft-snippet.html")
TEXT = ["--fg", "--muted", "--accent", "--ask", "--ok", "--warn"]
PAIRS = [("--accent", "--accent-soft"), ("--ask", "--ask-soft"), ("--warn", "--warn-soft"), ("--bg", "--accent"), ("--bg", "--fg")]


def lum(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = lum(a), lum(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def palettes(css):
    """{'light': {...}, 'dark': {...}} from the rules that define --bg."""
    sets = {"light": {}, "dark": {}}
    rule = re.compile(r"(@media[^{]*\{)?\s*([^{}@]+)\{([^{}]*--bg:[^{}]*)\}")
    for m in rule.finditer(css):
        media, sel, body = m.group(1) or "", m.group(2), m.group(3)
        dark = "prefers-color-scheme: dark" in media or 'data-ptheme="dark"' in sel or ('data-theme="dark"' in sel)
        toks = dict((k.strip(), v.strip()) for k, v in re.findall(r"(--[a-z-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;", body))
        sets["dark" if dark else "light"].update(toks)
    return sets


def token_sets(css, selector_part, token_re):
    """{'light': {...}, 'dark': {...}} of the tokens matching token_re in the rules whose selector contains selector_part (or, for an empty
    selector_part, in the rules that define the token at all)."""
    sets = {"light": {}, "dark": {}}
    rule = re.compile(r"(@media[^{]*\{)?\s*([^{}@]+)\{([^{}]*)\}")
    for m in rule.finditer(css):
        media, sel, body = m.group(1) or "", m.group(2), m.group(3)
        if selector_part and selector_part not in sel:
            continue
        toks = dict((k.strip(), v.strip()) for k, v in re.findall(r"(%s)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;" % token_re, body))
        if not toks:
            continue
        dark = "prefers-color-scheme: dark" in media or 'data-ptheme="dark"' in sel or 'data-theme="dark"' in sel
        sets["dark" if dark else "light"].update(toks)
    return sets


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    html = io.open(path, encoding="utf-8").read()
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    sets = palettes(css)
    bad = 0
    for name in ("light", "dark"):
        p = sets[name]
        need = set(TEXT + ["--bg", "--surface", "--line", "--accent-soft", "--ask-soft", "--warn-soft"])
        missing = sorted(need - set(p))
        if missing:
            print("FAIL %s palette is missing tokens: %s" % (name, ", ".join(missing)))
            bad += 1
            continue
        print("%s palette: %d tokens" % (name, len(p)))
        for t in TEXT:
            for bg in ("--bg", "--surface"):
                r = ratio(p[t], p[bg])
                ok = r >= 7.0
                bad += 0 if ok else 1
                print("  %s %s on %s %s: %.2f:1 (need 7:1)" % ("PASS" if ok else "FAIL", t, bg, p[t], r))
        for bg in ("--bg", "--surface"):
            r = ratio(p["--line"], p[bg])
            ok = r >= 3.0
            bad += 0 if ok else 1
            print("  %s --line on %s: %.2f:1 (need 3:1)" % ("PASS" if ok else "FAIL", bg, r))
        for a, b in PAIRS:
            r = ratio(p[a], p[b])
            ok = r >= 7.0
            bad += 0 if ok else 1
            print("  %s %s on %s: %.2f:1 (need 7:1)" % ("PASS" if ok else "FAIL", a, b, r))
    std = token_sets(css, 'data-contrast="standard"', r"--[a-z-]+")
    for name in ("light", "dark"):
        p = dict(sets[name])
        p.update(std[name])
        print("%s palette with reader.contrast standard: %d overridden token(s)" % (name, len(std[name])))
        if not std[name]:
            print("FAIL no standard-contrast rule found for the %s palette" % name)
            bad += 1
        for t in TEXT:
            for bg in ("--bg", "--surface"):
                r = ratio(p[t], p[bg])
                ok = r >= 4.5
                bad += 0 if ok else 1
                print("  %s %s on %s %s: %.2f:1 (need 4.5:1)" % ("PASS" if ok else "FAIL", t, bg, p[t], r))
        for a, b in PAIRS:
            r = ratio(p[a], p[b])
            ok = r >= 4.5
            bad += 0 if ok else 1
            print("  %s %s on %s: %.2f:1 (need 4.5:1)" % ("PASS" if ok else "FAIL", a, b, r))
    ws = token_sets(css, "", r"--ws-[a-z]+")
    for name in ("light", "dark"):
        toks = ws[name]
        if len(toks) != 6:
            print("FAIL %s workspace colours: found %d, want 6" % (name, len(toks)))
            bad += 1
        for t in sorted(toks):
            for bg in ("--bg", "--surface"):
                r = ratio(toks[t], sets[name][bg])
                ok = r >= 3.0
                bad += 0 if ok else 1
                print("  %s %s %s on %s: %.2f:1 (need 3:1) [%s]" % ("PASS" if ok else "FAIL", t, toks[t], bg, r, name))
    # 0.3.2 adds the shortcut list, its toggle and the Method contents bar to this list; 0.3.3 replaces the toggle (gone) with the key button of Bind Shortcuts and the refusal line (--ask on the panel's own surface).
    # 0.3.1: the floating tabs, the strip and the draft line take their colours only from tokens that are checked above:
    # the tab's text and border are --accent on --surface (hover and open: --accent on --accent-soft), the strip and the draft line sit on --surface,
    # the draft line's text is --muted (on --surface: 7:1 above). A literal colour in one of these rules would escape the check, so none is allowed.
    for sel, want in (('.pb-ftab {', ("color: var(--accent)", "background: var(--surface)")), ('.pb-ftabs[data-mode="strip"][data-on="1"] {', ("background: var(--surface)",)), ('.pb-draft {', ("color: var(--muted)",)),
                     # 0.3.2: the shortcut list and its toggle, the contents bar of the Method tab: text --fg, --muted or --accent on --surface (checked above), borders --line or --accent
                     ('.pb-flist {', ("background: var(--surface)", "color: var(--fg)", "border: 1px solid var(--line)")), ('.pb-flist-dl dd {', ("color: var(--muted)",)),
                     ('.pb-opt .pb-bind-k {', ("color: var(--accent)", "background: var(--surface)", "border: 1px solid var(--accent)")), ('.pb-bindrow .pb-bind-m[data-bad="1"] {', ("color: var(--ask)",)), ('.pb-method-nav {', ("background: var(--surface)", "border: 1px solid var(--line)")),
                     ('.pb-method-nav a {', ("color: var(--accent)",))):
        m = re.search(re.escape(sel) + r"([^{}]*)\}", css)
        body = m.group(1) if m else ""
        decls = [d.strip() for d in body.split(";") if d.strip() and not d.strip().startswith("box-shadow")]   # a shadow is not a text or background colour
        literal = [c for d in decls for c in re.findall(r"#[0-9a-fA-F]{3,6}|rgba?\([^)]*\)", d)]
        ok = bool(m) and all(w in body for w in want) and not literal
        bad += 0 if ok else 1
        print("  %s %s uses palette tokens (%s)%s" % ("PASS" if ok else "FAIL", sel.strip(" {"), "; ".join(want), "" if ok else " [missing rule, token or a literal colour: %s]" % literal))
    print("RESULT:", "OK" if not bad else "%d failing pair(s)" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
