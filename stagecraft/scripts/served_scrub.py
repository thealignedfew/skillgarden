#!/usr/bin/env python3
r"""served_scrub: take the owner's name, and the dated rulings that carry it, out of a page's source comments.

Why: a kit that keeps its history as comments ("Owner 2026-11-04: ...") ships that history in the source of every
page it serves, shared pages included. A comment is invisible on the page but present in the source of every page served,
including pages shared with the team. The rulings belong in the skill text; the served source must not carry them.

What it does: finds every comment in the page (HTML comments, CSS block comments in <style>, JS line and block
comments in <script>) and removes each one whose text names the owner (the owner's words come from scrub_terms.txt, see load_terms). Only comments are touched: page text, strings,
attributes and code are never changed. Anything else that carries the name is reported as "residual", left as written.
An exempt marker (<!-- artifact-header: exempt (...) --> or <!-- stagecraft: exempt (...) -->) keeps its marker but
loses its reason when the reason names the owner (the reason stays in the session's own record).

Use:
    python served_scrub.py page.html            dry run: say what would go, change nothing
    python served_scrub.py page.html --apply    rewrite the page in place; the original goes to --backup-dir
    from served_scrub import scrub              scrub(text) -> (new_text, report)

The lexer is deliberate: JS strings, template literals with ${ }, regex literals and comments are told apart, so a
"//" inside a URL string or a regex is not taken for a comment. If the lexer cannot make sense of a page (an
unterminated string or comment) it reports ok=False and changes nothing. Exit codes: 0 fine or nothing to do,
1 error, 2 dry run found something to remove.
"""
import argparse
import io
import os
import re
import sys
import time

def load_terms():
    """The words that name the page's owner, as one compiled pattern. Nothing in this file names anyone: the list is the
    person's own and lives beside the script (scrub_terms.txt), or in ~/.stagecraft/scrub_terms.txt, or in the
    STAGECRAFT_SCRUB_TERMS environment variable (one regular expression). One regular expression per line in the file;
    blank lines and lines starting with # are ignored. No list found means nothing matches and nothing is changed."""
    parts = []
    env = os.environ.get("STAGECRAFT_SCRUB_TERMS", "")
    if env.strip():
        parts.append(env.strip())
    else:
        for f in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrub_terms.txt"),
                  os.path.join(os.path.expanduser("~"), ".stagecraft", "scrub_terms.txt")):
            if os.path.isfile(f):
                for ln in io.open(f, encoding="utf-8"):
                    ln = ln.strip()
                    if ln and not ln.startswith("#"):
                        parts.append(ln)
                break
    return re.compile("|".join("(?:%s)" % x for x in parts)) if parts else re.compile(r"(?!x)x")


OWNER = load_terms()
EXEMPT_COMMENT = re.compile(r"<!--\s*(artifact-header|stagecraft):\s*exempt\b", re.I)
SCRIPT_OPEN = re.compile(r"<(script|style)\b([^>]*)>", re.I)
JS_TYPES = ("", "text/javascript", "application/javascript", "module", "text/babel", "text/jsx")
VALUE_END_BLOCKED = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw", "case",
                     "do", "else", "yield", "await"}
WORD = re.compile(r"[A-Za-z0-9_$]+")


class LexError(Exception):
    pass


def _script_is_js(attrs):
    m = re.search(r"""\btype\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", attrs, re.I)
    t = (m.group(1) or m.group(2) or m.group(3) or "") if m else ""
    return t.strip().lower() in JS_TYPES


def _css_spans(text, s, e):
    spans = []
    i = s
    while i < e:
        c = text[i]
        if c in "'\"":
            q, i = c, i + 1
            while i < e and text[i] != q:
                i += 2 if text[i] == "\\" else 1
            i += 1
        elif c == "/" and text.startswith("/*", i):
            end = text.find("*/", i + 2, e)
            if end < 0:
                raise LexError("unterminated CSS comment")
            spans.append((i, end + 2, "block"))
            i = end + 2
        else:
            i += 1
    return spans


def _js_spans(text, s, e):
    spans = []
    i = s
    depth = 0
    stack = []                 # brace depth at each open ${ of a template literal
    value = False              # True when the last significant token ends an expression ("/" is then division)

    def template(i):
        """Scan template literal text from i; return the index after its closing backtick, or after an opening ${."""
        nonlocal depth
        while i < e:
            c = text[i]
            if c == "\\":
                i += 2
            elif c == "`":
                return i + 1
            elif c == "$" and text.startswith("${", i):
                stack.append(depth)
                depth += 1
                return i + 2, True
            else:
                i += 1
        raise LexError("unterminated template literal")

    def scan_template(i):
        nonlocal value
        r = template(i)
        if isinstance(r, tuple):
            value = False
            return r[0]
        value = True
        return r

    while i < e:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and text.startswith("//", i):
            nl = i
            while nl < e and text[nl] not in "\r\n":
                nl += 1
            spans.append((i, nl, "line"))
            i = nl
        elif c == "/" and text.startswith("/*", i):
            end = text.find("*/", i + 2, e)
            if end < 0:
                raise LexError("unterminated JS comment")
            spans.append((i, end + 2, "block"))
            i = end + 2
        elif c in "'\"":
            q, i = c, i + 1
            while i < e and text[i] != q:
                if text[i] == "\\":
                    i += 2
                elif text[i] in "\r\n":
                    raise LexError("unterminated string")
                else:
                    i += 1
            i += 1
            value = True
        elif c == "`":
            i = scan_template(i + 1)
        elif c == "/":
            if value:
                i += 1
                value = False
            else:
                j, ok = i + 1, False
                in_class = False
                while j < e and text[j] not in "\r\n":
                    d = text[j]
                    if d == "\\":
                        j += 2
                        continue
                    if d == "[":
                        in_class = True
                    elif d == "]":
                        in_class = False
                    elif d == "/" and not in_class:
                        ok = True
                        break
                    j += 1
                if not ok:
                    i += 1             # not a regex after all: treat as an operator
                    value = False
                else:
                    j += 1
                    while j < e and (text[j].isalpha()):
                        j += 1
                    i = j
                    value = True
        elif WORD.match(text, i):
            m = WORD.match(text, i)
            w = m.group(0)
            i = m.end()
            value = w not in VALUE_END_BLOCKED
        elif c in ")]":
            i += 1
            value = True
        elif c == "{":
            depth += 1
            i += 1
            value = False
        elif c == "}":
            depth -= 1
            i += 1
            if stack and depth == stack[-1]:
                stack.pop()
                i = scan_template(i)
            else:
                value = False
        else:
            i += 1
            value = False
    if stack:
        raise LexError("unterminated template expression")
    return spans


def comment_spans(text):
    """Every comment in the page as (start, end, kind): kind html | block | line. Raises LexError on a page it cannot read."""
    spans = []
    i, n = 0, len(text)
    while i < n:
        j = text.find("<", i)
        if j < 0:
            break
        if text.startswith("<!--", j):
            end = text.find("-->", j + 4)
            if end < 0:
                raise LexError("unterminated HTML comment")
            spans.append((j, end + 3, "html"))
            i = end + 3
            continue
        m = SCRIPT_OPEN.match(text, j)
        if m:
            tag = m.group(1).lower()
            close = re.compile(r"</%s\s*>" % tag, re.I).search(text, m.end())
            if not close:
                raise LexError("unterminated <%s>" % tag)
            if tag == "style":
                spans += _css_spans(text, m.end(), close.start())
            elif _script_is_js(m.group(2)):
                spans += _js_spans(text, m.end(), close.start())
            i = close.end()
            continue
        i = j + 1
    return spans


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def scrub(text, pattern=None):
    """Return (new_text, report). report: ok, removed (list of (line, kind, first 60 chars)), residual (list of
    (line, 60 chars of context)), reason (when ok is False). new_text equals text when nothing was removed or ok is False."""
    pattern = pattern or OWNER
    rep = {"ok": True, "removed": [], "residual": [], "reason": ""}
    try:
        spans = comment_spans(text)
    except LexError as ex:
        rep["ok"], rep["reason"] = False, str(ex)
        return text, rep
    cuts = []                                   # (start, end, replacement)
    for s, e, kind in spans:
        body = text[s:e]
        if not pattern.search(body):
            continue
        if kind == "html" and EXEMPT_COMMENT.match(body):
            marker = EXEMPT_COMMENT.match(body).group(1).lower()
            cuts.append((s, e, "<!-- %s: exempt -->" % marker))
            rep["removed"].append((_line(text, s), "exempt-reason", body[:60].replace("\n", " ")))
            continue
        ls = text.rfind("\n", 0, s) + 1
        le = text.find("\n", e)
        le = len(text) if le < 0 else le
        before, after = text[ls:s], text[e:le]
        if before.strip() == "" and after.strip() == "":
            cuts.append((ls, min(le + 1, len(text)), ""))          # the comment is alone on its line(s): drop the lines
        elif kind == "line":
            cuts.append((s - (len(before) - len(before.rstrip(" \t"))), e, ""))
        else:
            cuts.append((s, e, "" if kind == "html" else ("\n" if "\n" in body else " ")))
        rep["removed"].append((_line(text, s), kind, body[:60].replace("\n", " ")))
    if cuts:
        cuts.sort()
        merged = []
        for c in cuts:
            if merged and c[0] < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], c[1]), merged[-1][2])
            else:
                merged.append(c)
        out, at = [], 0
        for s, e, r in merged:
            out.append(text[at:s])
            out.append(r)
            at = e
        out.append(text[at:])
        new = "".join(out)
        try:
            left = [1 for s, e, k in comment_spans(new) if pattern.search(new[s:e]) and not EXEMPT_COMMENT.match(new[s:e])]
        except LexError as ex:
            rep["ok"], rep["reason"] = False, "after scrub: " + str(ex)
            return text, rep
        if left:
            rep["ok"], rep["reason"] = False, "a comment naming the owner survived the scrub"
            return text, rep
    else:
        new = text
    for m in pattern.finditer(new):
        if len(rep["residual"]) < 50:
            a = max(0, m.start() - 25)
            rep["residual"].append((_line(new, m.start()), new[a:m.end() + 25].replace("\n", " ")))
    return new, rep


def scrub_file(path, apply=False, backup_dir=None):
    """Scrub one page on disk, byte-safe (keeps CRLF). Returns report; with apply writes the page and saves the original."""
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "removed": [], "residual": [], "reason": "not UTF-8"}
    new, rep = scrub(text)
    rep["changed"] = bool(rep["ok"] and rep["removed"])
    if apply and rep["changed"]:
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            bk = os.path.join(backup_dir, "%s.pre-scrub-%s" % (os.path.basename(path), time.strftime("%Y%m%d-%H%M%S")))
            with open(bk, "wb") as fh:
                fh.write(raw)
            rep["backup"] = bk
        tmp = path + ".scrub.tmp"
        with open(tmp, "wb") as fh:
            fh.write(new.encode("utf-8"))
        os.replace(tmp, path)
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("page")
    ap.add_argument("--apply", action="store_true", help="rewrite the page in place (default: dry run)")
    ap.add_argument("--backup-dir", default="", help="where the original goes on --apply")
    a = ap.parse_args()
    if not os.path.isfile(a.page):
        print("ERROR: no such file: %s" % a.page, file=sys.stderr)
        return 1
    rep = scrub_file(a.page, a.apply, a.backup_dir or None)
    if not rep["ok"]:
        print("UNREADABLE: %s (%s); page left as it was" % (a.page, rep["reason"]))
        return 1
    verb = "removed" if a.apply else "would remove"
    print("%s %d comment(s) naming the owner in %s" % (verb, len(rep["removed"]), a.page))
    for ln, kind, head in rep["removed"][:20]:
        print("  line %d (%s): %s" % (ln, kind, head))
    if rep["residual"]:
        print("outside comments, left as written: %d mention(s)" % len(rep["residual"]))
        for ln, ctx in rep["residual"][:5]:
            print("  line %d: ...%s..." % (ln, ctx))
    if rep.get("backup"):
        print("original saved: %s" % rep["backup"])
    return 2 if (rep["removed"] and not a.apply) else 0


if __name__ == "__main__":
    sys.exit(main())
