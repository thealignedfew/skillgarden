#!/usr/bin/env python3
"""Write sample_transactions.csv: about 25 months of made-up transactions for a fictional
household (the Rivera household) in the column layout of a Tiller "Transactions" export.

Every name, amount and account number here is invented. The random seed is fixed, so the
file comes out the same on every run.

Usage: python make_sample.py [output.csv]
"""
import csv
import json
import os
import random
import sys
from datetime import date, timedelta

SEED = 20240611
START = date(2024, 11, 1)
END = date(2026, 11, 5)          # the last month is partial on purpose

CHECKING = 'xxxx1111'
REWARDS = 'xxxx3344'
STORE = 'xxxx5566'
TRAVEL = 'xxxx7700'
ACCOUNT_NAMES = {CHECKING: 'Everyday Checking', REWARDS: 'Rewards Card', STORE: 'Store Card', TRAVEL: 'Travel Card'}

rng = random.Random(SEED)
rows = []


def add(d, desc, cat, amount, acct):
    if START <= d <= END:
        rows.append((d, desc, cat, round(amount, 2), acct))


def day(y, m, d):
    while True:
        try:
            return date(y, m, d)
        except ValueError:
            d -= 1


def months():
    y, m = START.year, START.month
    while (y, m) <= (END.year, END.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


WORK_TRIPS = {(2025, 3): ('Chicago', 'Lakefront Deli'), (2025, 9): ('Boise', 'Foothills Diner'), (2026, 4): ('Chicago', 'Lakefront Deli')}
PERSONAL_TRIPS = {(2025, 7): ('Santa Fe', 'Mesa Verde Grill'), (2026, 2): ('San Diego', 'Harbor Taco Co')}

for y, m in months():
    ym = (y, m)
    k = (y - START.year) * 12 + m - START.month          # month number from the start
    # money in
    add(day(y, m, 1), 'ACME LOGISTICS PAYROLL', 'Paycheck', 2850, CHECKING)
    add(day(y, m, 15), 'ACME LOGISTICS PAYROLL', 'Paycheck', 2850, CHECKING)
    if ym not in ((2025, 1), (2025, 8), (2026, 10)):
        add(day(y, m, rng.randint(5, 10)), 'Brightpath Studio Contract', 'Income', rng.randint(60, 104) * 50, CHECKING)
    add(day(y, m, 28), 'Interest Paid', 'Interest', rng.randint(9, 31) + rng.randint(0, 99) / 100, CHECKING)
    if ym == (2025, 4):
        add(day(y, m, 18), 'TAX REFUND STATE AND FEDERAL', 'Tax Refund', 1240, CHECKING)
    if rng.random() < 0.3:
        add(day(y, m, rng.randint(3, 27)), 'SHOPNOW MKTP refund', 'Shopping', rng.randint(12, 60), REWARDS)
    # transfers and card payments (left out by ignoreCategories)
    add(day(y, m, 3), 'Transfer to Savings', 'Transfer', -500, CHECKING)
    pay = rng.randint(900, 1600)
    add(day(y, m, 20), 'Payment to Rewards Card', 'Credit Card Payment', -pay, CHECKING)
    add(day(y, m, 20), 'Payment Thank You', 'Credit Card Payment', pay, REWARDS)
    # housing and bills
    add(day(y, m, 1), 'Hometown Mortgage', 'Mortgage, HELOC & loans', -2140, CHECKING)
    season = 1.6 if m in (12, 1, 2, 7, 8) else 1.0
    add(day(y, m, 12), 'City Power & Light', 'Utilities, phone & HOA', -round(rng.uniform(85, 120) * season, 2), CHECKING)
    add(day(y, m, 14), 'Metro Water', 'Utilities, phone & HOA', -round(rng.uniform(44, 69), 2), CHECKING)
    add(day(y, m, 9), 'FiberNet Internet', 'Utilities, phone & HOA', -79.99, REWARDS)
    add(day(y, m, 22), 'TalkWave Wireless', 'Utilities, phone & HOA', -round(rng.uniform(121, 134), 2), REWARDS)
    add(day(y, m, 6), 'SafeHarbor Insurance', 'Insurance', -168.40, CHECKING)
    # food
    for _ in range(rng.randint(3, 5)):
        add(day(y, m, rng.randint(1, 28)), 'GROCERY MART #215', 'Groceries', -round(rng.uniform(70, 185), 2), REWARDS)
    for _ in range(rng.randint(0, 2)):
        add(day(y, m, rng.randint(1, 28)), 'Fresh Fields Market', 'Groceries', -round(rng.uniform(25, 80), 2), REWARDS)
    for _ in range(rng.randint(2, 5)):
        add(day(y, m, rng.randint(1, 28)), 'SQ *CORNER CAFE', 'Restaurants', -round(rng.uniform(6, 19), 2), REWARDS)
    for _ in range(rng.randint(1, 2)):
        add(day(y, m, rng.randint(1, 28)), 'Pizza Palace', 'Dining, bars & coffee', -round(rng.uniform(24, 46), 2), REWARDS)
    if rng.random() < 0.5:
        add(day(y, m, rng.randint(1, 28)), 'Noodle House', 'Dining, bars & coffee', -round(rng.uniform(30, 70), 2), REWARDS)
    # getting around
    for _ in range(rng.randint(2, 4)):
        add(day(y, m, rng.randint(1, 28)), 'QuickFuel', 'Gas, rides & parking', -round(rng.uniform(34, 61), 2), REWARDS)
    if rng.random() < 0.4:
        add(day(y, m, rng.randint(1, 28)), 'RideNow Trip', 'Gas, rides & parking', -round(rng.uniform(11, 38), 2), REWARDS)
    if k % 5 == 2:
        add(day(y, m, rng.randint(1, 28)), 'Main Street Auto', 'Car repair', -round(rng.uniform(90, 640), 2), REWARDS)
    # subscriptions (StreamFlix raises its price in September 2025)
    add(day(y, m, 4), 'StreamFlix', 'Entertainment & streaming', -(17.99 if ym >= (2025, 9) else 15.49), REWARDS)
    add(day(y, m, 11), 'TuneBox Music', 'Entertainment & streaming', -10.99, REWARDS)
    add(day(y, m, 17), 'CloudDrive Storage', 'Subscriptions', -2.99, REWARDS)
    add(day(y, m, 19), 'PixelPlay Pass', 'Entertainment & streaming', -9.99, STORE)
    if ym <= (2025, 8):
        add(day(y, m, 8), 'NewsDaily Digital', 'Subscriptions', -4.00, REWARDS)
    if m == 2:
        add(day(y, m, 2), 'PhotoVault Annual Plan', 'Subscriptions', -59.99, REWARDS)
    add(day(y, m, 2), 'IronWorks Gym', 'Fitness & personal care', -49.00, CHECKING)
    add(day(y, m, 16), 'CloudDesk Pro', 'Business & work tools', -29.00, REWARDS)
    # pets
    for _ in range(rng.randint(1, 3)):
        add(day(y, m, rng.randint(1, 28)), 'Pet Pantry', 'Pets', -round(rng.uniform(22, 74), 2), REWARDS)
    add(day(y, m, 5), 'PawSure Pet Insurance', 'Pets', -32.00, REWARDS)
    if k % 4 == 1:
        add(day(y, m, rng.randint(1, 28)), 'Happy Paws Vet', 'Pets', -round(rng.uniform(110, 390), 2), REWARDS)
    # home upkeep
    for _ in range(rng.randint(0, 2)):
        add(day(y, m, rng.randint(1, 28)), 'Hardware Barn', 'Home & yard', -round(rng.uniform(14, 160), 2), STORE)
    if m in (4, 5, 6):
        add(day(y, m, rng.randint(1, 28)), 'Green Thumb Garden Center', 'Home & yard', -round(rng.uniform(40, 180), 2), STORE)
    if ym in ((2025, 3), (2025, 10), (2026, 5)):
        add(day(y, m, rng.randint(1, 28)), 'HandyPro Services', 'Services', -round(rng.uniform(180, 650), 2), CHECKING)
    # shopping
    for _ in range(rng.randint(2, 6)):
        add(day(y, m, rng.randint(1, 28)), 'SHOPNOW MKTP', 'Shopping', -round(rng.uniform(12, 95), 2), REWARDS)
    for _ in range(rng.randint(0, 2)):
        add(day(y, m, rng.randint(1, 28)), 'MegaMart', 'Shopping', -round(rng.uniform(18, 120), 2), STORE)
    if rng.random() < 0.3:
        add(day(y, m, rng.randint(1, 28)), 'Threadline Apparel', 'Shopping', -round(rng.uniform(30, 140), 2), STORE)
    # health
    if rng.random() < 0.35:
        add(day(y, m, rng.randint(1, 28)), 'Valley Clinic', 'Medical & dental', -round(rng.uniform(25, 60), 2), CHECKING)
    if m in (3, 9):
        add(day(y, m, rng.randint(1, 28)), 'Bright Smile Dental', 'Medical & dental', -round(rng.uniform(80, 260), 2), CHECKING)
    # giving, taxes
    add(day(y, m, 25), 'Community Food Bank', 'Giving', -25.00, CHECKING)
    if m == 12:
        add(day(y, m, 10), 'County Tax Office', 'Taxes & government', -1450.00, CHECKING)
    if m == 5:
        add(day(y, m, 10), 'State Motor Vehicles', 'Taxes & government', -118.00, CHECKING)
    # hobbies
    if ym >= (2025, 6):
        add(day(y, m, 7), 'Clay Corner Studio', 'Education & activities', -85.00, REWARDS)
    if rng.random() < 0.25:
        add(day(y, m, rng.randint(1, 28)), 'Spoke & Chain Bikes', 'Shopping', -round(rng.uniform(20, 210), 2), STORE)
    if rng.random() < 0.3:
        add(day(y, m, rng.randint(1, 28)), 'PixelPlay Store', 'Entertainment & streaming', -round(rng.uniform(9, 70), 2), STORE)
    # card interest and fees
    if ym <= (2025, 8):
        add(day(y, m, 24), 'Interest Charge on Card Balance', 'Card interest & fees', -round(rng.uniform(38, 142), 2), REWARDS)
    if ym == (2025, 2):
        add(day(y, m, 24), 'Late Fee', 'Card interest & fees', -35.00, REWARDS)
    if ym == (2024, 12):
        add(day(y, m, 6), 'Balance Transfer Fee', 'Card interest & fees', -210.00, REWARDS)
    if m == 1:
        add(day(y, m, 15), 'Annual Membership Fee', 'Card interest & fees', -95.00, TRAVEL)
    # legal (excluded in config)
    if ym == (2025, 4):
        add(day(y, m, 9), 'Harbor Legal Group', 'Legal & collections', -1500.00, CHECKING)
    if ym == (2025, 6):
        add(day(y, m, 9), 'Harbor Legal Group', 'Legal & collections', -820.00, CHECKING)
    # travel
    for trips in (WORK_TRIPS, PERSONAL_TRIPS):
        if ym in trips:
            place, local = trips[ym]
            add(day(y, m, 6), 'SkyHop Air', 'Travel', -round(rng.uniform(240, 520), 2), TRAVEL)
            add(day(y, m, 12), 'Stayover Hotels ' + place, 'Travel', -round(rng.uniform(320, 760), 2), TRAVEL)
            for _ in range(rng.randint(2, 3)):
                add(day(y, m, rng.randint(12, 15)), local, 'Dining, bars & coffee', -round(rng.uniform(18, 64), 2), TRAVEL)
    if ym == (2026, 8):
        add(day(y, m, 3), 'Pacific Coast Rail', 'Travel', -1840.00, TRAVEL)
    # the dependent: a summer program in 2026
    if ym == (2026, 5):
        add(day(y, m, 20), 'Lakeside Summer Program', 'Education & activities', -1200.00, CHECKING)
    if ym == (2026, 6):
        add(day(y, m, 18), 'Lakeside Summer Program', 'Education & activities', -2400.00, CHECKING)
        add(day(y, m, 29), 'Coastline Bus', 'Gas, rides & parking', -64.00, REWARDS)
    if ym == (2026, 7):
        add(day(y, m, 3), 'Lakeside Campus Store', 'Shopping', -48.50, REWARDS)
        add(day(y, m, 11), 'Lakeside Campus Store', 'Shopping', -22.75, REWARDS)
        add(day(y, m, 26), 'Coastline Bus', 'Gas, rides & parking', -64.00, REWARDS)

rows.sort(key=lambda r: (r[0], r[1]))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample_transactions.csv')
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Date', 'Description', 'Category', 'Amount', 'Account', 'Account #'])
    for d, desc, cat, amt, acct in rows:
        w.writerow([f'{d.month}/{d.day}/{d.year}', desc, cat, f'{amt:.2f}', ACCOUNT_NAMES[acct], acct])
print(f'wrote {len(rows)} rows to {out}')

# A small order list for the Shopping tab: some ShopNow charges get an order placed 0 to 3 days before.
ITEMS = ['Glaze sampler set', 'Dog chew toys 3 pack', 'USB-C charging cable', 'Ceramic coffee mug', 'Cotton bath towels',
         'Running socks 6 pack', 'LED desk lamp', 'Kitchen knife set', 'Wireless mouse', 'Storage bins with lids',
         'Dog leash 6 ft', 'Gray hoodie', 'Clay trimming tools', 'HDMI adapter', 'Tea sampler']
orders = []
for d, desc, cat, amt, acct in rows:
    if desc == 'SHOPNOW MKTP' and amt < 0 and rng.random() < 0.45:
        od = d - timedelta(days=rng.randint(0, 3))
        orders.append({'d': od.isoformat(), 'item': rng.choice(ITEMS), 'more': rng.choice([0, 0, 0, 1, 2])})
orders.sort(key=lambda o: o['d'])
op = os.path.join(os.path.dirname(os.path.abspath(out)), 'sample_orders.json')
with open(op, 'w', encoding='utf-8') as f:
    json.dump(orders, f, indent=0)
print(f'wrote {len(orders)} orders to {op}')
