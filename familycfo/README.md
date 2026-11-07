# familycfo

A household money ledger in one web page. It reads a Tiller-style transactions export and shows where the money goes, month by month.

## How it works

1. You export your transactions from Tiller (or any tool) as a CSV file.
2. You describe your household in `config.json`: categories, groups, centers, income sources and the like.
3. `build_data.py` reads both and writes `data.json`.
4. `index.html` loads `data.json` and draws the ledger: Overview, Spending, Vendors, Cash in and out, Subscriptions, Hobbies, Centers, a Dependent tab, a Travel map, Shopping, Notes and Options.

Tabs you do not configure (hobbies, a dependent, places, a shopping store) stay hidden.

## Requirements

- Python 3.8 or newer. The builder uses the standard library only.
- A modern web browser.
- An internet connection when the page opens, to load the chart libraries (d3, ECharts, topojson-client) and fonts from public CDNs. The map outlines also come from a CDN unless you put local copies beside the page.

## Quick start

```
python make_sample.py            # writes sample_transactions.csv and sample_orders.json
python build_data.py             # uses config.example.json until you create config.json
python -m http.server 8000 --bind 127.0.0.1
```

Open http://127.0.0.1:8000/index.html. The page must be served; opening the file directly will not load `data.json`.

For your own data:

1. Export the Tiller "Transactions" sheet as CSV. It needs the columns Date, Description, Category, Amount and Account #. A negative amount is spending; a positive amount is money in.
2. Copy `config.example.json` to `config.json`, set `transactionsCsv` to your file, and change the rest.
3. Run `python build_data.py` again and reload the page.

Options: `python build_data.py --config other.json --csv export.csv --out data.json`.

## Settings

`config.json` reference, one line per key. Keys that start with `_` are comments and are ignored. Regexes are matched without regard to case.

- `title`: page heading and browser tab title.
- `transactionsCsv`: the transactions CSV, relative to the config file.
- `subscriptionsCsv`: optional list of subscriptions (service, category, cadence, amount, last_charge, paid_with, status, note); without it the builder finds recurring charges itself.
- `ordersJson`: optional list of online orders, each `{d, item, more}`.
- `lastMonthPartial`: true or false; leave out to decide from the last transaction date.
- `ignoreCategories`: categories that are neither spending nor income, such as transfers and card payments.
- `incomeRules`: `[regex, source]` pairs tested against "Description | Category" for money in.
- `refundSource`: income source name for other money in (refunds and the like).
- `categoryMap`: rename categories, `{from: to}`.
- `catFix`: `[regex on vendor, category]` for spending left in Other.
- `aliasRules`: `[regex on description, clean name]`; several spellings can share one name.
- `vendorRules`: `[regex on vendor, tags, category]` to add tags or force a category.
- `increaseSplit`: split a vendor's price rise into its own line: `{vendor, from, base, label, tags}`.
- `payrollSource`: the income source smoothed to a flat monthly amount and taxed.
- `taxRate`: percent of `payrollSource` set aside for income tax.
- `oneoffIncome`: one-time money in, `{name: {YYYY-MM: amount}}`.
- `oneoffTaxable`: names from `oneoffIncome` that also get the tax set-aside.
- `oneoffNetOfCenter`: a center whose excluded costs are taken off one-time money in before tax.
- `groups`: chart groups, each `{name, categories, color}`.
- `categoryNames`: default display names, `{category: name}`.
- `centerRules`: default center for a whole category, `{category: #center}`.
- `centers`: cost and profit centers, each `{id, name, note, match, hidden}`.
- `exclude`: spending left out of every total and shown in a center: `{match, center, receivable, category, before, after, countAsDebt}`.
- `feeCategory`: the category for card interest and fees.
- `fees`: `{avoidable, chosen, interestAvoidableFrom}` to sort fees.
- `foodCategories`: categories summed in the Food tile.
- `hobbies`: hobby cards, each `{id, name, who, note, re}`.
- `dependent`: the Dependent tab: `{label, tabLabel, center, tag, note, matchRegex, from, to, matchWhy, items, tripShare, leftOut, footnote}`.
- `travelCategory`: the category that holds trips.
- `travelGenericRegex`: vendors (airlines, hotels) split between work and personal by month.
- `workMonths`: months (YYYY-MM) with work travel.
- `places`: map places, each `{name, lat, lon, when, keys, months, home, work, planned, route}`.
- `route`: optional route line, a list of `[lon, lat]`.
- `routeMonth`: month the route appears on the timeline.
- `mapCenter`: first map center, `[lon, lat]`.
- `mapZoom`: first map zoom.
- `mapData`: optional `{states, countries}` URLs for your own map outline files.
- `shopping`: the Shopping tab: `{label, vendorRegex, excludeRegex, orderLookupUrl, kinds}`.
- `orderKinds`: set the kind of one order, `{item: kind}`.
- `orderTags`: `[regex on item, #center]` to put orders into a center.
- `vendorNotes`: a note shown when you hover a vendor, `{vendor: note}`.
- `balances`: `{asOf, checking, cards}` for the projection and the card table.
- `known`: known future items for the projection, each `{name, amount, month, uncertain}`.
- `projection`: `{interestSaving}` monthly saving to assume.
- `subscriptionCategories`: limits the automatic subscription finder to these categories.
- `subsStreamingRegex`: picks the streaming and apps tile.
- `notes`: optional page text: `{cashflow, leftOut, shopping}`.
- `source`: one line on where the data came from.

## Your data stays local

- The builder reads files on your computer and writes `data.json` beside the page. It makes no network calls.
- The page loads `data.json` from the same folder. It sends nothing anywhere.
- Your tags, budgets, renames, notes and options are saved in your browser's localStorage. When the page runs as a claude.ai artifact, they are saved with the artifact instead.
- The page does load public code and fonts from CDNs (cdnjs, jsdelivr, Google Fonts). Those requests carry no transaction data.
- Keep `config.json`, your CSV and `data.json` out of any public repository. They describe your household.

## Files

- `index.html`: the ledger page.
- `build_data.py`: turns the CSV and config into `data.json`.
- `config.example.json`: a full example for a fictional household.
- `make_sample.py`: writes the fictional sample data with a fixed random seed.
- `sample_transactions.csv`: about 25 months of made-up transactions.
- `sample_orders.json`: made-up online orders for the Shopping tab.
- `data.json`: built from the sample, so the page works out of the box.
- `SKILL.md`: instructions for Claude to set this up for a household.

## Limits and honest caveats

- The numbers are only as good as the export. Unlinked accounts, cash and payment apps are missing.
- Categories come from your export. The page does not guess them, apart from the rules you write.
- Refunds count as money in, not as lower spending.
- Subscription finding is simple: the same vendor and amount in three or more months. Price changes break the match.
- The tax set-aside is a flat percent. It is not tax advice.
- The projection is arithmetic on your assumptions, not a forecast.
- Saved settings live in one browser. Clearing site data removes them.
- The map needs the us-atlas and world-atlas outline files, from a CDN or local copies.
- US dollars only.

Not affiliated with Anthropic, Tiller or any bank.
