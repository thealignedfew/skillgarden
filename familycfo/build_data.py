#!/usr/bin/env python3
"""familycfo builder.

Reads a Tiller-style "Transactions" CSV export (columns Date, Description, Category, Amount,
Account #; a negative amount is spending, a positive amount is money in) plus config.json, and
writes data.json in the shape index.html expects.

Usage:
    python build_data.py [--config config.json] [--csv transactions.csv] [--out data.json]

With no --config it uses config.json beside this script, or config.example.json when there is
no config.json yet. Relative paths inside the config are read relative to the config file.
Optional inputs (subscriptions CSV, orders JSON) are skipped when the file is missing.
Standard library only.
"""
import argparse
import calendar
import csv
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))

# Keys only the builder uses; they are not copied into data.json.
BUILDER_ONLY = {'transactionsCsv', 'subscriptionsCsv', 'ordersJson', 'ignoreCategories', 'incomeRules',
                'refundSource', 'categoryMap', 'catFix', 'aliasRules', 'vendorRules', 'increaseSplit',
                'lastMonthPartial', 'subscriptionCategories'}


def parse_amount(s):
    s = (s or '').strip().replace('$', '').replace(',', '').replace(' ', '')
    if not s:
        return None
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_date(s):
    s = (s or '').strip()
    for f in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y', '%Y/%m/%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def compile_pairs(pairs):
    out = []
    for p in pairs or []:
        try:
            out.append((re.compile(p[0], re.I),) + tuple(p[1:]))
        except re.error as e:
            print(f'warning: skipped bad regex {p[0]!r}: {e}', file=sys.stderr)
    return out


def month_add(ym, n):
    y, m = int(ym[:4]), int(ym[5:7]) + n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f'{y:04d}-{m:02d}'


def month_diff(a, b):
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def main():
    ap = argparse.ArgumentParser(description='Build data.json for the familycfo page.')
    ap.add_argument('--config', help='settings file (default: config.json, else config.example.json)')
    ap.add_argument('--csv', help='Tiller Transactions CSV export (default: transactionsCsv in the config)')
    ap.add_argument('--out', help='output file (default: data.json beside this script)')
    args = ap.parse_args()

    cfg_path = args.config or (os.path.join(HERE, 'config.json') if os.path.exists(os.path.join(HERE, 'config.json'))
                               else os.path.join(HERE, 'config.example.json'))
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(cfg_path))
    rel = lambda p: p if os.path.isabs(p) else os.path.join(base, p)
    csv_path = args.csv or rel(cfg.get('transactionsCsv', 'transactions.csv'))
    out_path = args.out or os.path.join(HERE, 'data.json')

    ignore = {c.strip().lower() for c in cfg.get('ignoreCategories', [])}
    inc_rules = compile_pairs(cfg.get('incomeRules'))
    refund_source = cfg.get('refundSource', 'Refunds and other deposits')
    cat_map = cfg.get('categoryMap', {})
    cat_fix = compile_pairs(cfg.get('catFix'))
    aliases = compile_pairs(cfg.get('aliasRules'))
    vrules = compile_pairs(cfg.get('vendorRules'))

    def clean(v):
        raw = re.sub(r'\s+', ' ', (v or '').strip())
        for rx, a in aliases:
            if rx.search(raw):
                return a
        v = re.sub(r'^(SQ|SP|TST|PY|PP|PAYPAL)\s*\*\s*', '', raw, flags=re.I)
        v = re.sub(r'^(Sp|Sq|Tst|Py) (?=\S+ \S)', '', v)
        v = re.sub(r'\s+-$', '', v)
        v = re.sub(r'\s+#\s*\d+$', '', v).strip()
        for rx, a in aliases:
            if rx.search(v):
                return a
        if v.isupper() and len(v) > 3:
            v = v.title()
        return v or 'Unknown'

    # ---------- read the CSV ----------
    if not os.path.exists(csv_path):
        sys.exit(f'Transactions file not found: {csv_path}')
    recs = []
    with open(csv_path, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            r = {(k or '').strip().lower(): (v or '') for k, v in row.items()}
            d = parse_date(r.get('date'))
            a = parse_amount(r.get('amount'))
            if d is None or a is None or a == 0:
                continue
            cat = r.get('category', '').strip()
            if cat.lower() in ignore:
                continue
            desc = r.get('description') or r.get('full description') or ''
            acct_raw = r.get('account #') or r.get('account number') or r.get('account') or ''
            digits = re.sub(r'\D', '', acct_raw)
            acct = digits[-4:] if digits else (acct_raw.strip()[:16] or '?')
            recs.append((d, desc, cat, a, acct))
    if not recs:
        sys.exit('No usable transactions: check the Date and Amount columns.')

    first = min(r[0] for r in recs)
    last = max(r[0] for r in recs)
    months = [first.strftime('%Y-%m')]
    while months[-1] < last.strftime('%Y-%m'):
        months.append(month_add(months[-1], 1))
    N = len(months)
    idx = {m: i for i, m in enumerate(months)}
    partial = cfg.get('lastMonthPartial')
    if partial is None:
        partial = last.day < calendar.monthrange(last.year, last.month)[1]
    last_full = N - 2 if partial else N - 1

    # ---------- money in and spending ----------
    income = defaultdict(lambda: [0.0] * N)
    agg = {}
    tx = []
    memo = {}
    for d, desc, cat, a, acct in recs:
        mi = idx[d.strftime('%Y-%m')]
        if a > 0:
            hay = desc + ' | ' + cat
            src = next((r[1] for r in inc_rules if r[0].search(hay)), None) or refund_source
            income[src][mi] += a
            continue
        key0 = (desc, cat)
        if key0 not in memo:
            v = clean(desc)
            c = cat_map.get(cat, cat) or 'Other'
            if c.lower() in ('other', 'uncategorized'):
                c = next((r[1] for r in cat_fix if r[0].search(v)), c)
            tags = []
            for rr in vrules:
                rx, t, nc = rr[0], (rr[1] if len(rr) > 1 else ''), (rr[2] if len(rr) > 2 else '')
                if rx.search(v):
                    if t:
                        tags.append(t)
                    if nc:
                        c = nc
            memo[key0] = (v, c, ','.join(tags))
        v, c, tags = memo[key0]
        k = v + '|' + c
        o = agg.get(k)
        if not o:
            o = agg[k] = {'v': v, 'c': c, 'ac': set(), 'm': [0.0] * N}
            if tags:
                o['tags'] = tags
        o['ac'].add(acct)
        o['m'][mi] += -a
        tx.append([d.isoformat(), v, round(-a, 2), acct])

    vlist = []
    for o in agg.values():
        o['ac'] = '/'.join(sorted(o['ac']))
        vlist.append(o)

    # optional: split a price rise into its own line
    extra = []
    for sp in cfg.get('increaseSplit', []):
        if sp.get('from') not in idx:
            continue
        k = idx[sp['from']]
        for o in vlist:
            if o['v'] != sp.get('vendor'):
                continue
            dlt = [max(0.0, x - sp.get('base', 0)) if i >= k else 0.0 for i, x in enumerate(o['m'])]
            if sum(dlt):
                o['m'] = [x - y for x, y in zip(o['m'], dlt)]
                e = {'v': sp.get('label', o['v'] + ' increase'), 'c': o['c'], 'ac': o['ac'], 'm': dlt}
                if sp.get('tags'):
                    e['tags'] = sp['tags']
                extra.append(e)
    vlist = vlist + extra
    for o in vlist:
        o['m'] = [round(x, 2) for x in o['m']]
    vlist.sort(key=lambda o: -sum(o['m']))

    # ---------- one-time income ----------
    for name, mm in (cfg.get('oneoffIncome') or {}).items():
        a = [0.0] * N
        for m, v in mm.items():
            if m in idx:
                a[idx[m]] += v
        income[name] = a
    oneoff = list((cfg.get('oneoffIncome') or {}).keys()) + [k for k in cfg.get('oneoff', []) if k not in (cfg.get('oneoffIncome') or {})]

    # ---------- subscriptions ----------
    subs = []
    sub_csv = cfg.get('subscriptionsCsv')
    if sub_csv and os.path.exists(rel(sub_csv)):
        with open(rel(sub_csv), encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                r = {k.strip(): (v or '').strip() for k, v in r.items() if k}
                r['amount'] = parse_amount(r.get('amount')) or 0.0
                subs.append(r)
        print(f'subscriptions: read {len(subs)} rows from {sub_csv}')
    else:
        # find them: same vendor and same amount in three or more months
        cats = set(cfg.get('subscriptionCategories') or [])
        vcat = {}
        for o in vlist:
            vcat.setdefault(o['v'], o['c'])
        by = defaultdict(list)
        for d, v, a, ac in tx:
            if cats and vcat.get(v) not in cats:
                continue
            by[(v, a)].append((d, ac))
        for (v, a), hits in by.items():
            ms = sorted({h[0][:7] for h in hits})
            if len(ms) < 3:
                continue
            gaps = [month_diff(x, y) for x, y in zip(ms, ms[1:])]
            med = statistics.median(gaps)
            cadence = 'Monthly' if med <= 1 else 'Quarterly' if med <= 3.5 else 'Yearly' if med >= 10 else f'Every {round(med)} months'
            dates = sorted(h[0] for h in hits)
            since = (last - date.fromisoformat(dates[-1])).days
            status = 'Active' if since <= (50 if cadence == 'Monthly' else 50 + 31 * med) else 'Stopped'
            if status == 'Active' and cadence != 'Monthly':
                status = 'Check'
            subs.append({'service': v, 'category': vcat.get(v, ''), 'cadence': cadence, 'amount': a,
                         'last_charge': dates[-1], 'paid_with': 'card ' + ', '.join(sorted({h[1] for h in hits})),
                         'status': status, 'note': f'{len(dates)} charges since {dates[0]}'})
        subs.sort(key=lambda s: (s['status'], -s['amount']))
        print(f'subscriptions: found {len(subs)} recurring charges')

    # ---------- orders (optional) ----------
    orders = []
    oj = cfg.get('ordersJson')
    if oj and os.path.exists(rel(oj)):
        with open(rel(oj), encoding='utf-8') as f:
            for o in json.load(f):
                d = o.get('d') or o.get('date')
                item = o.get('item') or o.get('title')
                if d and item and 'cancel' not in str(o.get('status', '')).lower():
                    orders.append({'d': str(d)[:10], 'item': str(item).strip(), 'more': int(o.get('more') or 0)})
        orders.sort(key=lambda o: o['d'])

    # ---------- card interest and fees by account, last 12 full months ----------
    fee_cat = cfg.get('feeCategory', 'Card interest & fees')
    l12 = range(max(0, last_full - 11), last_full + 1)
    fees = defaultdict(float)
    for o in vlist:
        if o['c'] == fee_cat:
            for ac in o['ac'].split('/'):
                fees[ac] += sum(o['m'][i] for i in l12) / max(1, len(o['ac'].split('/')))
    interest = [{'account': 'card ' + ac, 'fees': round(v, 2)} for ac, v in sorted(fees.items(), key=lambda x: -x[1]) if v > 0]

    # ---------- travel places ----------
    vt = defaultdict(float)
    for o in vlist:
        vt[o['v']] += sum(o['m'])
    places = []
    for p in cfg.get('places', []):
        p = dict(p)
        p['keys'] = sorted({clean(k) for k in p.get('keys', [])})
        p['spend'] = round(sum(vt.get(k, 0) for k in p['keys']))
        places.append(p)

    data = {
        'months': months,
        'partial': bool(partial),
        'income': {k: [round(x, 2) for x in v] for k, v in income.items()},
        'oneoff': oneoff,
        'vendors': vlist,
        'tx': tx,
        'orders': orders,
        'subs': subs,
        'interest': interest,
    }
    for k, v in cfg.items():
        if k.startswith('_') or k in BUILDER_ONLY or k in data:
            continue
        data[k] = v
    data['places'] = places

    s = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(s)
    print(f'wrote {out_path}: {len(s)} bytes, {N} months ({months[0]} to {months[-1]}{", last partial" if partial else ""}), '
          f'{len(vlist)} vendor lines, {len(tx)} charges, {len(income)} income sources, {len(orders)} orders')
    for p in places:
        print(f"  place {p['name']}: {p['spend']}")


if __name__ == '__main__':
    main()
