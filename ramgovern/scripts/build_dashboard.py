"""build_dashboard.py  ramgovern 0.2.1: build the RAM dashboard page.

Reads three local sources and writes one self-contained HTML page, then adds the stagecraft include file:
  sampler files   samples-YYYYMMDD.jsonl from sampler.ps1 (free RAM, commit, processor use, the busiest programs)
  govern.log      every trim run and every brake action
  brake.json      the programs the brake may slow, and who approved each
and the brake's procmem-YYYYMMDD.jsonl lines beside govern.log (RAM by program, commit, page file).
The charts are drawn here as plain SVG, so the page needs no script of its own beyond stagecraft. This page NEEDS the
stagecraft skill from the same repository: its tabs, tables, themes and comments come from it. Without it this script stops
with a message and writes nothing.

  python build_dashboard.py [--out <file>] [--days 7] [--samples <folder>] [--log <govern.log>] [--config <brake.json>]
      [--seat <name>] [--session <id>] [--account <label>] [--stagecraft <skill folder>]
      [--free-mb 500] [--commit-pct 95] [--cpu-pct 90] [--late-pct 20]

All paths default to the ramgovern home (see brake_suggest.home): the folder named by RAMGOVERN_HOME, or the folder holding
govern.json, or .threadops/ramgovern under your profile. The page is written to <home>/dashboard/ramgovern-dashboard.html.
It leads with a row of figures, then a day-by-hour heat grid of when the machine struggled, then the detailed tables, and a
Method tab explains every figure to a reader with nothing else.
"""
import argparse, glob, html, json, os, re, subprocess, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brake_suggest import load_samples, suggest, struggling, home  # noqa: E402

LOG_RE = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([+-]\d{2}:\d{2}|[A-Z]{3,4}) (.*)$')
TRIM_RE = re.compile(r'^(stage[12]) (task|self|seat) (?:APPLY|TRIMMED): .*?resident (\d+) -> (\d+) \(2s\) -> (\d+) \(30s\) MB')
LIM = {'free_mb': 500, 'commit_pct': 95, 'cpu_pct': 90, 'late_pct': 20}   # what counts as struggling; main() sets it from the options
E = html.escape


def parse_log(path, since):
    trims, brakes, storms, errors = [], [], 0, 0
    if not os.path.exists(path):
        return trims, brakes, storms, errors
    size = os.path.getsize(path)
    with open(path, encoding='utf-8', errors='replace') as fh:
        fh.seek(max(0, size - 12_000_000))
        for line in fh:
            m = LOG_RE.match(line.rstrip('\n'))
            if not m:
                continue
            t = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
            if t < since:
                continue
            body = m.group(3)
            if 'ERROR' in body:
                errors += 1
            if re.search(r'storm (?!none)', body) and '0 storms' not in body:
                storms += 1
            tm = TRIM_RE.match(body)
            if tm:
                trims.append({'t': t, 'kind': 'one session' if tm.group(2) in ('self', 'seat') else 'idle sessions',
                              'before': int(tm.group(3)), 'after2': int(tm.group(4)), 'after30': int(tm.group(5))})
            bm = re.match(r'^brake (BRAKE|RELEASE[^:]*|CONFIG[^:]*|START[^;]*|ERROR)(?::\s*)?(.*)$', body)
            if bm:
                brakes.append({'t': t, 'what': bm.group(1).split(' (')[0].title(), 'detail': bm.group(2)[:220]})
    return trims, brakes, storms, errors


def svg_line(samples, hours, w=1000, h=220):
    """Free RAM (line) and late-frame % (bars) over the last `hours`."""
    end = datetime.now()
    start = end - timedelta(hours=hours)
    pts = [s for s in samples if datetime.fromisoformat(s['t']) >= start]
    if not pts:
        return '<p class="muted">No samples in this window.</p>'
    span = (end - start).total_seconds()
    maxmb = max(max(s.get('availMB', 0) for s in pts), 1000)
    x = lambda t: 40 + (w - 50) * (datetime.fromisoformat(t) - start).total_seconds() / span
    y = lambda mb: 10 + (h - 40) * (1 - mb / maxmb)
    # one point a minute keeps the page small
    keep, last = [], None
    for s in pts:
        k = s['t'][:16]
        if k != last:
            keep.append(s)
            last = k
    # split the line wherever samples stop for more than 3 minutes, and shade the gap as no data
    segs, cur, gaps, prev = [], [], [], None
    for s in keep:
        ts = datetime.fromisoformat(s['t'])
        if prev is not None and (ts - prev).total_seconds() > 180:
            segs.append(cur)
            cur = []
            gaps.append((prev, ts))
        cur.append(s)
        prev = ts
    segs.append(cur)
    if (end - prev).total_seconds() > 180:
        gaps.append((prev, end))
    if (datetime.fromisoformat(keep[0]['t']) - start).total_seconds() > 180:
        gaps.insert(0, (start, datetime.fromisoformat(keep[0]['t'])))
    xt = lambda d: 40 + (w - 50) * (d - start).total_seconds() / span
    gap_svg = ''.join(f'<rect x="{xt(g0):.1f}" y="10" width="{max(xt(g1) - xt(g0), 1):.1f}" height="{h - 40}" class="gap" '
                      f'data-tip="No samples from {g0.strftime("%a %H:%M")} to {g1.strftime("%a %H:%M")}: the sampler was not running"/>'
                      + (f'<text x="{(xt(g0) + xt(g1)) / 2:.1f}" y="24" text-anchor="middle" class="gt">no data</text>' if xt(g1) - xt(g0) > 40 else '')
                      for g0, g1 in gaps)
    line = ''.join('<polyline points="' + ' '.join(f'{x(s["t"]):.1f},{y(s.get("availMB", 0)):.1f}' for s in sg) + '" class="fl"/>' for sg in segs if sg)
    bars = ''.join(f'<rect x="{x(s["t"]):.1f}" y="{h - 30 - (h - 40) * min(s.get("latePct", 0), 100) / 100:.1f}" width="1.6" '
                   f'height="{(h - 40) * min(s.get("latePct", 0), 100) / 100:.1f}" class="lb"/>' for s in keep if (s.get('latePct') or 0) > 0)
    ticks = ''
    t = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    step = 6 if hours > 24 else 3
    while t < end:
        if t.hour % step == 0:
            xx = 40 + (w - 50) * (t - start).total_seconds() / span
            lab = t.strftime('%a %H:00') if t.hour == 0 else t.strftime('%H:00')
            ticks += f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="10" y2="{h - 30}" class="gl"/><text x="{xx:.1f}" y="{h - 14}" text-anchor="middle">{lab}</text>'
        t += timedelta(hours=1)
    ylab = ''.join(f'<text x="34" y="{y(v) + 4:.1f}" text-anchor="end">{v / 1024:.0f} GB</text><line x1="40" x2="{w - 10}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="gl"/>'
                   for v in range(0, int(maxmb) + 1, 4096))
    return (f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Free RAM, last {hours} hours">'
            f'{gap_svg}{ylab}{ticks}{bars}{line}</svg>')


PALETTE = ['#2a78d6', '#eb6834', '#1baf7a', '#c98500', '#d55181', '#6250d6', '#008300', '#9AA1AD']


def load_procmem(folder, days):
    cut = datetime.now() - timedelta(days=days)
    out = []
    for f in sorted(glob.glob(os.path.join(folder, 'procmem-*.jsonl'))):
        with open(f, encoding='utf-8-sig', errors='replace') as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    if datetime.fromisoformat(r['t']) >= cut:
                        out.append(r)
                except Exception:
                    continue
    return out


def svg_series(series, hours, unit='GB', ymax=None, w=1000, h=230, gap_s=180, label=''):
    """Lines for several series over the last `hours`; a line stops at gaps over gap_s and the span is shaded as no data."""
    end = datetime.now()
    start = end - timedelta(hours=hours)
    span = (end - start).total_seconds()
    pts_all = [(datetime.fromisoformat(t), v) for _, _, pts in series for t, v in pts if datetime.fromisoformat(t) >= start]
    if not pts_all:
        return '<p class="muted">No data in this window yet. The memory sampler inside the brake writes one line a minute; this chart fills in once it has run.</p>'
    top = ymax or (max(v for _, v in pts_all) * 1.08) or 1
    xt = lambda d: 40 + (w - 50) * (d - start).total_seconds() / span
    y = lambda v: 10 + (h - 40) * (1 - min(v, top) / top)
    body, gaps = '', []
    times = sorted({d for d, _ in pts_all})
    if (times[0] - start).total_seconds() > gap_s:
        gaps.append((start, times[0]))
    for a0, a1 in zip(times, times[1:]):
        if (a1 - a0).total_seconds() > gap_s:
            gaps.append((a0, a1))
    if (end - times[-1]).total_seconds() > gap_s:
        gaps.append((times[-1], end))
    for g0, g1 in gaps:
        body += (f'<rect x="{xt(g0):.1f}" y="10" width="{max(xt(g1) - xt(g0), 1):.1f}" height="{h - 40}" class="gap" '
                 f'data-tip="No data from {g0.strftime("%a %H:%M")} to {g1.strftime("%a %H:%M")}"/>')
        if xt(g1) - xt(g0) > 40:
            body += f'<text x="{(xt(g0) + xt(g1)) / 2:.1f}" y="24" text-anchor="middle" class="gt">no data</text>'
    for i in range(5):
        v = top / 4 * i
        body += (f'<line x1="40" x2="{w - 10}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="gl"/>'
                 f'<text x="34" y="{y(v) + 4:.1f}" text-anchor="end">{v:.0f}{"%" if unit == "%" else ""}</text>')
    tick_step = 1 if hours <= 6 else 6
    t0 = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while t0 < end:
        if t0.hour % tick_step == 0:
            lab = t0.strftime("%a %H:00") if t0.hour == 0 else t0.strftime("%H:00")
            body += (f'<line x1="{xt(t0):.1f}" x2="{xt(t0):.1f}" y1="10" y2="{h - 30}" class="gl"/>'
                     f'<text x="{xt(t0):.1f}" y="{h - 14}" text-anchor="middle">{lab}</text>')
        t0 += timedelta(hours=1)
    for name, color, pts in series:
        pp = [(datetime.fromisoformat(t), v) for t, v in pts if datetime.fromisoformat(t) >= start]
        seg, prev = [], None
        for d, v in pp:
            if prev is not None and (d - prev).total_seconds() > gap_s and seg:
                body += f'<polyline points="{" ".join(seg)}" style="stroke:{color}" class="sl"><title>{E(name)}</title></polyline>'
                seg = []
            seg.append(f'{xt(d):.1f},{y(v):.1f}')
            prev = d
        if seg:
            body += f'<polyline points="{" ".join(seg)}" style="stroke:{color}" class="sl"><title>{E(name)}</title></polyline>'
    legend = ''.join(f'<span><i style="background:{c}"></i>{E(n)}</span>' for n, c, _ in series)
    unit_note = 'GB' if unit == 'GB' else ''
    return (f'<div class="legend">{legend}</div><svg viewBox="0 0 {w} {h}" class="chart" role="img" '
            f'aria-label="{E(label)}">{body}</svg>' + (f'<p class="muted">Scale in {unit_note}.</p>' if unit_note else ''))


def heat(samples, days):
    """Days by hours: share of samples where the PC struggled."""
    cells = {}
    for s in samples:
        t = datetime.fromisoformat(s['t'])
        k = (t.date(), t.hour)
        c = cells.setdefault(k, [0, 0])
        c[0] += 1
        if struggling(s, **LIM):
            c[1] += 1
    today = datetime.now().date()
    shares = sorted(b / n for n, b in cells.values() if n and b)
    top = shares[int(0.95 * (len(shares) - 1))] if shares else 1.0
    top = max(top, 0.01)
    out = ['<div class="heat"><span></span>' + ''.join(f'<span class="hh">{h:02d}</span>' for h in range(24))]
    for d in range(days):
        day = today - timedelta(days=d)
        out.append(f'<span class="hl">{day.strftime("%a %m-%d")}</span>')
        for h in range(24):
            n, b = cells.get((day, h), (0, 0))
            if n == 0:
                out.append('<span class="c none" data-tip="no samples"></span>')
            else:
                p = b / n
                out.append(f'<span class="c" style="--p:{min(p / top, 1):.2f}" data-tip="{day.strftime("%a %m-%d")} {h:02d}:00, {b} of {n} samples struggling ({100 * p:.0f}%)"></span>')
    out.append('</div>')
    out.append(f'<div class="heatleg"><span>0%</span><span class="ramp"></span><span>{100 * top:.0f}% or more of the hour&#39;s samples struggling (the strongest colour; fainter means fewer)</span></div>')
    return ''.join(out)


def table(tid, headers, rows, prio=None):
    th = ''.join(f'<th{(" data-priority=" + chr(34) + str(prio[i]) + chr(34)) if prio and prio[i] else ""}>{E(h)}</th>' for i, h in enumerate(headers))
    body = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows)
    return f'<table id="{tid}" data-pb-key="{tid}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(home(), 'dashboard', 'ramgovern-dashboard.html'))
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--samples', default=home())
    ap.add_argument('--log', default=os.path.join(home(), 'govern.log'))
    ap.add_argument('--config', default=os.path.join(home(), 'brake.json'))
    ap.add_argument('--seat', default='')
    ap.add_argument('--account', default='')
    ap.add_argument('--free-mb', type=float, default=500)
    ap.add_argument('--commit-pct', type=float, default=95)
    ap.add_argument('--cpu-pct', type=float, default=90)
    ap.add_argument('--late-pct', type=float, default=20)
    ap.add_argument('--session', default='')
    ap.add_argument('--stagecraft', default=os.path.join(os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude')), 'skills', 'stagecraft'))
    a = ap.parse_args()
    inj = os.path.join(a.stagecraft, 'scripts', 'inject_stagecraft.py')
    if not os.path.exists(inj):
        print('This page needs the stagecraft skill, and it was not found at ' + a.stagecraft + '. Install stagecraft from the same '
              'repository, or pass --stagecraft <its folder>, and run this again. Nothing was written.')
        sys.exit(2)
    LIM.update(free_mb=a.free_mb, commit_pct=a.commit_pct, cpu_pct=a.cpu_pct, late_pct=a.late_pct)
    lim = LIM
    now = datetime.now()
    since = now - timedelta(days=a.days)
    samples = load_samples(a.samples, a.days)
    cfg = json.load(open(a.config, encoding='utf-8')) if os.path.exists(a.config) else {'targets': []}
    targets = cfg.get('targets', [])
    trims, brakes, storms, errors = parse_log(a.log, since)
    sug = suggest(samples, [t['name'] for t in targets], **LIM)
    live = {}
    try:
        out = subprocess.run(['tasklist', '/fo', 'csv', '/nh'], capture_output=True, text=True, timeout=30).stdout
        for line in out.splitlines():
            nm = line.split('","')[0].strip('"').lower()
            if nm.endswith('.exe'):
                nm = nm[:-4]
            live[nm] = live.get(nm, 0) + 1
    except Exception:
        pass
    windows = [(1, 'Last day'), (3, 'Last 3 days'), (7, 'Last 7 days'), (14, 'Last 14 days')]
    samples_all = load_samples(a.samples, 14)
    sug_by_window = []
    for d, lab in windows:
        cut = (now - timedelta(days=d)).isoformat()
        sw = suggest([s for s in samples_all if s['t'] >= cut], [t['name'] for t in targets], **LIM)
        sug_by_window.append((lab, sw))

    last = samples[-1] if samples else {}
    hour = [s for s in samples if datetime.fromisoformat(s['t']) >= now - timedelta(hours=1)]
    today = [s for s in samples if datetime.fromisoformat(s['t']).date() == now.date()]
    late_hr = 100 * sum(1 for s in hour if struggling(s, **LIM)) / max(1, len(hour))
    worst_today = min((s.get('availMB', 0) for s in today), default=0)
    trims_today = [t for t in trims if t['t'].date() == now.date()]
    freed_today = sum(t['before'] - t['after30'] for t in trims_today)
    brakes_today = sum(1 for b in brakes if b['t'].date() == now.date() and b['what'] == 'Brake')
    s_through = last.get('t', '')[:16].replace('T', ' ')
    l_through = (trims[-1]['t'] if trims else now).strftime('%Y-%m-%d %H:%M')

    cards = (
        f'<div class="tiles">'
        f'<div class="tile"><span class="lbl">Free RAM now</span><span class="v">{last.get("availMB", 0) / 1024:.1f} GB</span><span class="s">at {E(s_through[11:])}</span></div>'
        f'<div class="tile"><span class="lbl">Commit now</span><span class="v">{last.get("commitPct", 0):.0f}%</span><span class="s">of RAM plus page file</span></div>'
        f'<div class="tile"><span class="lbl">Struggling, last hour</span><span class="v">{late_hr:.0f}%</span><span class="s">samples that counted as struggling</span></div>'
        f'<div class="tile"><span class="lbl">Lowest free RAM today</span><span class="v">{worst_today:,} MB</span><span class="s">{len(today):,} samples</span></div>'
        f'<div class="tile"><span class="lbl">Trims today</span><span class="v">{len(trims_today):,}</span><span class="s">{freed_today / 1024:.1f} GB held off after 30 s</span></div>'
        f'<div class="tile"><span class="lbl">Brakes today</span><span class="v">{brakes_today}</span><span class="s">{storms} storms, {errors} errors in {a.days} days</span></div>'
        f'</div>')

    trim_rows = [[E(t['t'].strftime('%m-%d %H:%M:%S')), E(t['kind']), f'<span data-int>{t["before"]}</span>', f'<span data-int>{t["after2"]}</span>',
                  f'<span data-int>{t["after30"]}</span>', f'<span data-int>{t["before"] - t["after30"]}</span>'] for t in reversed(trims[-300:])]
    brake_rows = [[E(b['t'].strftime('%m-%d %H:%M:%S')), E(b['what']), E(b['detail'])] for b in reversed(brakes[-200:])]
    tgt_rows = [[E(t['name']), E(t.get('match') or 'every copy'), E(', '.join(t.get('helpers') or []) or 'none'),
                 'on' if t.get('enabled') else 'off', E(t.get('approved', '')), E(t.get('why', ''))] for t in targets]
    sug_rows = []
    for lab, sw in sug_by_window:
        for r in sw['rows'][:25]:
            sug_rows.append([E(lab), E(r['name']), E(r['verdict']), f'{r["bad_share_pct"]:.1f}%', f'{r["median_cpu_pct"]:.0f}%',
                             f'{r["peak_cpu_pct"]:.0f}%', f'<span data-int>{r["bad_samples"]}</span>', f'<span data-int>{r["hours"]}</span>',
                             E(r['first_seen']), E(r['last_seen']), f'<span data-int>{live.get(r["name"], 0)}</span>', f'{r["foreground_pct"]:.1f}%'])

    pb = {
        'key': 'ramgovern-dashboard',
        'tabs': [{'id': 'now', 'label': 'RAM now'}, {'id': 'governor', 'label': 'Trims'}, {'id': 'brake', 'label': 'Brake'}, {'id': 'method', 'label': 'Method'}],
        'header': {'seat': a.seat, 'session': a.session, 'account': a.account, 'headless': False, 'published': now.strftime('%Y-%m-%d %H:%M'), 'refresh_min': 50},
        'sources': [{'name': 'sampler files', 'through': s_through}, {'name': 'govern.log', 'through': l_through},
                    {'name': 'brake.json', 'through': datetime.fromtimestamp(os.path.getmtime(a.config)).strftime('%Y-%m-%d %H:%M') if os.path.exists(a.config) else ''}],
        'glossary': {'trim': 'Moving a process\'s idle memory pages out of RAM. The process keeps running and pulls pages back when it needs them.',
                     'brake': 'Slowing a background process while the person is at the PC: fewer processor threads and low priority. Nothing is stopped.',
                     'commit': 'Memory promised to programs, as a share of RAM plus the page file. Near 100% new allocations fail.'},
        'log': {'qa': [], 'versions': [{'when': now.strftime('%Y-%m-%d %H:%M'), 'what': 'Built by build_dashboard.py'}]},
    }

    pm = load_procmem(os.path.dirname(a.log), 3)
    late_leg = ('<span><i style="background:var(--ask)"></i>late frames (% of screen frames drawn late)</span>'
                if any(s.get('latePct') for s in samples) else '')
    charts = ''
    for hrs in (4, 48):
        cut = (now - timedelta(hours=hrs)).isoformat()
        pmw = [r for r in pm if r['t'] >= cut]
        peak = {}
        for r in pmw:
            for pr in r.get('top', []):
                peak[pr['n']] = max(peak.get(pr['n'], 0), pr['ws'])
        names = [n for n, _ in sorted(peak.items(), key=lambda kv: -kv[1])[:6]]
        proc_series = [(n, PALETTE[i], [(r['t'], next((pr['ws'] for pr in r['top'] if pr['n'] == n), 0) / 1024) for r in pmw])
                       for i, n in enumerate(names)]
        if pmw:
            proc_series.append(('everything else', PALETTE[7],
                                [(r['t'], (r['wsAllMB'] - sum(pr['ws'] for pr in r['top'] if pr['n'] in names)) / 1024) for r in pmw]))
        sw = [s for s in samples if s['t'] >= cut]
        com = [s.get('commitPct', 0) for s in sw]
        pf_series = [('commit, % of RAM plus page file', '#eb6834', [(s['t'], s.get('commitPct', 0)) for s in sw])]
        if pmw:
            pf_series.append(('page file in use, % of its size', '#2a78d6',
                              [(r['t'], 100 * r['pfUsedMB'] / max(1, r['pfSizeMB'])) for r in pmw]))
        last_pm = pmw[-1] if pmw else (pm[-1] if pm else None)
        if com:
            near = sum(1 for c in com if c >= 90) / len(com)
            pf_sum = (f'Commit peaked at {max(com):.0f}% and averaged {sum(com) / len(com):.0f}%; {100 * near:.0f}% of samples '
                      'were at 90% or more, where new memory requests start to fail.')
        else:
            pf_sum = 'No commit samples in this window.'
        if last_pm:
            privs = sorted(last_pm['top'], key=lambda pr: -pr['pv'])[:3]
            pf_sum += (f' Latest reading: {last_pm["commitMB"] / 1024:.0f} of {last_pm["limitMB"] / 1024:.0f} GB committed; page file '
                       f'{last_pm["pfUsedMB"] / 1024:.0f} of {last_pm["pfSizeMB"] / 1024:.0f} GB in use (peak {last_pm["pfPeakMB"] / 1024:.0f} GB). '
                       'Largest private memory, which is what commit counts: '
                       + ', '.join(f'{E(pr["n"])} {pr["pv"] / 1024:.0f} GB over {pr["c"]} copies' for pr in privs) + '.')
        charts += (f'<div data-win-show="{hrs}">'
                   '<h3>Free RAM</h3><div class="legend"><span><i style="background:var(--accent)"></i>free RAM</span>'
                   + late_leg + '</div>'
                   + svg_line(samples, hrs)
                   + '<h3>RAM held by the busiest programs</h3><p class="muted">Working set in GB, all copies of a program added '
                   'together: the six that held the most in this window, and everything else.</p>'
                   + svg_series(proc_series, hrs, label='RAM by program')
                   + f'<h3>Commit and the page file</h3><p class="muted">{pf_sum}</p>'
                   + svg_series(pf_series, hrs, unit='%', ymax=100, label='Commit and page file')
                   + '</div>')
    pbjs = re.sub(r'"([A-Za-z_][A-Za-z0-9_]*)":', lambda m: m.group(1) + ':', json.dumps(pb, default=str))
    page = f'''<title>RAM Governor</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
.wrapd {{ display: flex; flex-direction: column; gap: 18px; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }}
.tile {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; min-width: 0; }}
.tile .v {{ font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }}
.tile .s, .muted {{ font-size: 12px; color: var(--muted); }}
.lbl {{ font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }}
.panel {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-width: 0; }}
svg.chart {{ width: 100%; height: auto; display: block; }}
svg.chart text {{ fill: var(--muted); font-size: 11px; }}
svg.chart .gl {{ stroke: var(--line); stroke-opacity: .35; }}
svg.chart .fl {{ fill: none; stroke: var(--accent); stroke-width: 1.6; }}
svg.chart .lb {{ fill: var(--ask); fill-opacity: .55; }}
.legend {{ display: flex; gap: 16px; font-size: 12px; color: var(--muted); flex-wrap: wrap; }}
.legend i {{ display: inline-block; width: 12px; height: 4px; margin-right: 6px; vertical-align: middle; }}
.heat {{ display: grid; grid-template-columns: 72px repeat(24, minmax(0, 1fr)); gap: 2px; font-size: 10.5px; }}
.heat .hl, .heat .hh {{ color: var(--muted); white-space: nowrap; text-align: center; }}
.heat .hl {{ text-align: left; }}
.heat .c {{ height: 16px; border-radius: 2px; background: color-mix(in srgb, var(--ask) calc(var(--p) * 100%), var(--accent-soft)); }}
.heatleg {{ display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); margin-top: 10px; flex-wrap: wrap; }}
.heatleg .ramp {{ width: 140px; height: 10px; border-radius: 2px; background: linear-gradient(90deg, var(--accent-soft), var(--ask)); }}
svg.chart .gap {{ fill: var(--muted); fill-opacity: .12; stroke: var(--muted); stroke-opacity: .35; stroke-dasharray: 3 3; }}
svg.chart text.gt {{ font-style: italic; }}
.wbar {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }}
.wbar h2 {{ margin: 0; }}
.seg {{ display: inline-flex; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }}
.seg button {{ border: 0; background: var(--surface); color: var(--fg); padding: 5px 12px; cursor: pointer; font: inherit; }}
.seg button[aria-pressed="true"] {{ background: var(--accent); color: var(--surface); }}
#winbox[data-win="4"] [data-win-show="48"], #winbox[data-win="48"] [data-win-show="4"] {{ display: none; }}
#winbox h3 {{ font-size: 14px; margin: 18px 0 4px; }}
svg.chart .sl {{ fill: none; stroke-width: 1.6; }}
.heat .c.none {{ background: transparent; border: 1px dashed var(--line); }}
</style>
<div class="wrapd" data-pb-tab="now">
<p>How much memory this PC has free, when it struggled, and what the Governor and the brake did about it. Detail level 0 shows the figures and the charts (4 hours by default, 48 with the switch); level 1 adds the week grid and the brake log. Rebuilt by ramgovern's build_dashboard.py.</p>
{cards}
<div class="panel" id="winbox" data-win="4">
<div class="wbar"><h2>Charts for the last</h2><span class="seg" role="group" aria-label="Chart window"><button type="button" data-w="4" aria-pressed="true">4 hours</button><button type="button" data-w="48" aria-pressed="false">48 hours</button></span></div>
{charts}
</div>
<div class="panel l1"><h2>When the PC struggled, last {a.days} days</h2>
<p class="muted">Newest day first. Each cell is one hour: the share of samples that counted as struggling (see the Method tab), coloured relative to this week (the key below gives the real percent). Hover a cell for its numbers; dashed means no samples.</p>
{heat(samples, a.days)}</div>
</div>
<div class="wrapd" data-pb-tab="governor">
<p>Every trim in the last {a.days} days, newest first (up to 300). Resident is the memory the trimmed processes held in RAM, in MB: before, 2 seconds after and 30 seconds after. What comes back within 30 seconds was needed; the rest was idle.</p>
<div class="pb-chips" data-target="#trims" data-column="What was trimmed"></div>
{table("trims", ["When", "What was trimmed", "Before MB", "After 2 s MB", "After 30 s MB", "Held off MB"], trim_rows, [None, None, 3, 2, None, None])}
</div>
<div class="wrapd" data-pb-tab="brake">
<h2>Processes the brake may slow</h2>
<p>While the person is at the PC (input within {cfg.get("active_window_sec", 600)} s), each enabled target gets {cfg.get("threads", 8)} processor threads, low priority and low memory and disk priority. Nothing is stopped. A target is added only with the person's yes.</p>
{table("targets", ["Process", "Only copies whose command line has", "Helpers braked with it", "State", "Approved", "Why"], tgt_rows, [None, None, 2, None, 3, 1])}
<h2>Suggested by the agent</h2>
<p>Processes often among the five busiest (at least half a core) while the PC struggled. Pick a window and a verdict with the chips; each window is worked out on its own (last 7 days: {sug["bad_samples"]:,} struggling samples of {sug["samples"]:,}). First and last seen are the first and last struggling samples that caught the process busy; running now counts its copies when the page was built. "suggest" means worth asking about; protected names and the person's own apps are never braked.</p>
<div class="pb-chips" data-target="#suggest" data-column="Window"></div>
<div class="pb-chips" data-target="#suggest" data-column="Verdict"></div>
{table("suggest", ["Window", "Process", "Verdict", "Share of struggling samples", "Median CPU (100% = one core)", "Peak CPU", "Struggling samples", "Hours seen", "First seen", "Last seen", "Running now (copies)", "In front"], sug_rows, [None, None, None, None, 4, 5, 3, 2, None, None, None, 1])}
<h2 class="l1">Brake activity</h2>
<div class="l1"><div class="pb-chips" data-target="#brakes" data-column="Action"></div>
{table("brakes", ["When", "Action", "Detail"], brake_rows)}</div>
</div>
<section id="method-purpose" data-pb-tab="method"><h2>What this page is for and who it is for</h2>
<p>It answers: is this machine short of memory right now, when has it struggled, and what did ramgovern's trims and brake do about it. It is for the machine's owner and for whoever runs ramgovern for them, to decide whether a change helped and whether another program should be braked. It is a capture, rebuilt whenever the build script is run.</p></section>
<section id="method-derived" data-pb-tab="method"><h2>How each figure was derived</h2>
<table data-pb-key="method-derived" data-pb-prose><thead><tr><th>Figure</th><th>Where it appears</th><th>The rule, in words</th><th>Source</th></tr></thead><tbody>
<tr><td>RAM held by the busiest programs</td><td>RAM now</td><td>Once a minute the brake's memory sampler adds up the working set (RAM in use) of every copy of each program and keeps the twelve largest. The chart shows the six with the highest peak in the window, and everything else (the total for all programs minus those six).</td><td>procmem files</td></tr>
<tr><td>Commit and page file</td><td>RAM now</td><td>Commit is memory promised to programs as a share of RAM plus the page file (commitPct in a sample). Page file in use is the page file's current usage divided by its allocated size (memory sampler). The summary gives peak and average commit, the share of samples at 90 percent or more, and the three programs with the most private memory, which is what commit counts.</td><td>sampler files, procmem files</td></tr>
<tr><td>Gaps in the 48-hour chart</td><td>RAM now</td><td>Wherever two samples are more than 3 minutes apart, the line stops and the stretch is shaded as no data: the sampler was not running.</td><td>sampler files</td></tr>
<tr><td>Free RAM now</td><td>RAM now, first card</td><td>availMB of the newest sample, shown in GB (divided by 1024).</td><td>sampler files</td></tr>
<tr><td>Commit now</td><td>RAM now</td><td>commitPct of the newest sample.</td><td>sampler files</td></tr>
<tr><td>Struggling, last hour</td><td>RAM now</td><td>Samples in the last 60 minutes that count as struggling (see the assumed values), divided by all samples in that hour.</td><td>sampler files</td></tr>
<tr><td>Lowest free RAM today</td><td>RAM now</td><td>The smallest availMB among today's samples (local time).</td><td>sampler files</td></tr>
<tr><td>Trims today, GB held off</td><td>RAM now</td><td>Count of today's trim lines in govern.log; held off is the sum over them of resident before minus resident 30 seconds after.</td><td>govern.log</td></tr>
<tr><td>Brakes today; storms; errors</td><td>RAM now</td><td>Count of today's brake lines that slowed a process; lines with a storm other than "storm none"; lines with ERROR, over the page's days.</td><td>govern.log</td></tr>
<tr><td>Heat grid cell</td><td>RAM now</td><td>For one hour, samples that count as struggling, divided by all samples in that hour. The colour is that share divided by the 95th percentile of the week's non-zero hours, capped at 1, so the scale is relative to the week.</td><td>sampler files</td></tr>
<tr><td>Suggestion window, first and last seen, hours seen, running now</td><td>Brake</td><td>Each window (1, 3, 7, 14 days) is computed separately from the samples in it. First and last seen are the earliest and latest struggling samples where the program was among the busiest at half a core or more; hours seen counts distinct clock hours among them. Running now is the number of copies of that program name in the Windows task list when the page was built.</td><td>sampler files, Windows task list</td></tr>
<tr><td>Suggestion verdict</td><td>Brake</td><td>A program among the five busiest at 50 percent CPU or more in at least 15 percent of struggling samples is "suggest", unless it is protected, already a target, or in front in over 5 percent of all samples ("your own app").</td><td>sampler files, brake.json</td></tr>
</tbody></table></section>
<section id="method-sources" data-pb-tab="method"><h2>Sources</h2>
<table data-pb-key="method-sources" data-pb-prose><thead><tr><th>Source</th><th>What it is</th><th>How it was reached</th><th>Data through</th></tr></thead><tbody>
<tr><td>sampler files</td><td>One line every few seconds from sampler.ps1: free RAM, commit, total processor use, the application in front, the five busiest programs.</td><td>samples-YYYYMMDD.jsonl in the ramgovern home, read by the build script.</td><td>{E(s_through)}</td></tr>
<tr><td>govern.log</td><td>One line per trim run and per brake action.</td><td>govern.log in the ramgovern home (or the path given with --log).</td><td>{E(l_through)}</td></tr>
<tr><td>procmem files</td><td>One line a minute from the brake's memory sampler: RAM by program, commit, page file. The charts are blank before the brake first ran.</td><td>procmem-YYYYMMDD.jsonl beside govern.log.</td><td>{E(pm[-1]["t"][:16].replace("T", " ") if pm else "")}</td></tr>
<tr><td>brake.json</td><td>The list of programs the brake may slow, with who approved each.</td><td>brake.json in the ramgovern home.</td><td>{E(pb["sources"][2]["through"])}</td></tr>
</tbody></table></section>
<section id="method-assumed" data-pb-tab="method"><h2>Hard-coded and assumed values</h2>
<table data-pb-key="method-assumed" data-pb-prose><thead><tr><th>Value</th><th>Where it is used</th><th>Why this value</th><th>When to revisit</th></tr></thead><tbody>
<tr><td>Struggling: free RAM under {lim["free_mb"]:g} MB, commit over {lim["commit_pct"]:g} percent, processor use over {lim["cpu_pct"]:g} percent, or (when a sample carries it) late frames over {lim["late_pct"]:g} percent</td><td>Struggling figure, heat grid, suggestions</td><td>Under a few hundred MB free is where paging takes over; commit near its limit makes new memory requests fail; sustained processor use near the top leaves nothing for you. A sample that lacks a field never counts for it. Change the limits with the command-line options of build_dashboard.py.</td><td>If the grid looks all clear while you feel lag, or the reverse.</td></tr>
<tr><td>Half a core (50 percent CPU) and 15 percent of struggling samples</td><td>Suggestions</td><td>Filters out programs that are only briefly busy.</td><td>When a suggestion turns out wrong.</td></tr>
<tr><td>Protected names</td><td>Brake and suggestions</td><td>Windows itself, your editor and browsers, the agents' own tools and the Defender engine are never braked.</td><td>When you ask.</td></tr>
<tr><td>{a.days} days; 48 hours</td><td>Heat grid and tables; the line chart</td><td>Long enough to compare weekdays, short enough to load fast.</td><td>None planned.</td></tr>
</tbody></table></section>
<section id="method-limits" data-pb-tab="method"><h2>Limits: what this page cannot tell you</h2>
<p>The busiest programs are ranked by processor use, not memory, so a program that holds memory but is idle never shows in the suggestions. The page is a capture: it is as current as the dates at the right, not live. A brake that slowed a program does not prove the program caused the strain.</p></section>
<section id="method-rebuild" data-pb-tab="method"><h2>How to rebuild or extend this page</h2>
<p>Run scripts\build_dashboard.py with Python 3 on the machine; it reads the sources above and writes the page, then adds the stagecraft include file. It needs the stagecraft skill installed and stops with a message if it is not. Do not change the page key ramgovern-dashboard or the tab ids now, governor, brake and method, or readers lose their saved setup. Add a brake target only with the owner's yes; never from this page's suggestions alone.</p></section>
<script>
(function () {{
  var box = document.getElementById('winbox'); if (!box) return;
  var key = 'ramgovern-win';
  function set(w) {{ box.setAttribute('data-win', w); box.querySelectorAll('.seg button').forEach(function (b) {{ b.setAttribute('aria-pressed', b.getAttribute('data-w') === w ? 'true' : 'false'); }}); try {{ localStorage.setItem(key, w); }} catch (e) {{}} }}
  box.querySelectorAll('.seg button').forEach(function (b) {{ b.addEventListener('click', function () {{ set(b.getAttribute('data-w')); }}); }});
  try {{ var s = localStorage.getItem(key); if (s === '4' || s === '48') set(s); }} catch (e) {{}}
}})();
</script>
<script>
var PB_CONFIG = {pbjs};
</script>
'''
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8', newline='') as fh:
        fh.write(page)
    cmd = [sys.executable, inj, a.out, '--key', 'ramgovern-dashboard']
    if a.seat:
        cmd += ['--seat', a.seat]
    if a.session:
        cmd += ['--session', a.session]
    if a.account:
        cmd += ['--account', a.account]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    print(f'wrote {a.out}: {len(samples):,} samples, {len(trims):,} trims, {len(brakes)} brake lines, {len(targets)} targets, {sum(1 for x in sug["rows"] if x["verdict"] == "suggest")} suggestions')


if __name__ == '__main__':
    main()
