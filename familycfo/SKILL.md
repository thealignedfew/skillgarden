---
name: familycfo
description: Set up and maintain familycfo, a one-page household money ledger built from a Tiller-style transactions export. Use when someone wants to see where their household's money goes from bank and card data, build a family budget page or dashboard from a Tiller (or similar) CSV, track cost centers such as home upkeep or reimbursable work costs, follow spending for one dependent, or update an existing familycfo page with new transactions, categories, aliases or exclusions.
---

# familycfo

familycfo is a folder with `index.html` (the page), `build_data.py` (the builder), `config.example.json` and sample data. The builder reads a transactions CSV plus `config.json` and writes `data.json`; the page draws from `data.json`.

## Set it up for a household

1. **Get the export.** Ask the person to export the Tiller "Transactions" sheet as CSV (File, Download, CSV). It needs the columns Date, Description, Category, Amount and Account #. Negative amounts are spending, positive amounts are money in. Other tools work if they produce the same columns. Save it in the familycfo folder, for example as `transactions.csv`.
2. **Look before you write.** Read only the header and a small sample of rows, and list the distinct categories with their counts. Do not paste whole statements into the conversation.
3. **Write `config.json` with the person.** Start from `config.example.json`. Ask about, in this order:
   - `transactionsCsv` and `ignoreCategories` (which categories are transfers and card payments).
   - `incomeRules`: each regular income and how its description reads. Which one, if any, has no tax withheld (`payrollSource`, `taxRate`). Any one-time money in (`oneoffIncome`).
   - `categoryMap` and `groups`: map their categories onto the groups they want to see.
   - `centers` and `centerRules`: the slices they care about (home upkeep, a pet, a side business).
   - `exclude`: spending to keep out of every total, such as work costs an employer pays back (`receivable: true`) or a legal matter (`receivable: false`).
   - Optional tabs: `hobbies`, `dependent`, `places`, `shopping`. Leave a key out to hide its tab.
   Keep the person's names, employers and places only in their own `config.json`, never in shared files.
4. **Build.** Run `python build_data.py`. Read its summary line: months covered, vendor lines, charges, income sources. If a month looks empty or income looks wrong, fix `incomeRules` or `ignoreCategories` and build again.
5. **Show it.** Serve the folder with `python -m http.server 8000 --bind 127.0.0.1` and open http://127.0.0.1:8000/index.html. The page must be served, not opened as a file. To publish it as a claude.ai artifact instead, publish `index.html` with `data.json` as a supporting file; settings then save with the artifact. Publish only when the person asks, and remind them the page holds their financial data.
6. **Check it.** Open each tab. The lede on the Overview should state 12-month spending; the Vendors table should list merchants; the Centers tab should show each center. Ask the person whether the top vendors and categories look right.

## Change it later

- **New transactions:** export again, replace the CSV, run `python build_data.py`, reload.
- **Add a center:** add `{"id": "#Name", "name": "...", "note": "...", "match": "regex"}` to `centers`. A whole category goes in with `centerRules`; one vendor goes in by tagging it `#Name` on the Vendors tab (`-#Name` takes it out).
- **Add an exclusion:** add `{"match": "regex on vendor", "center": "#Name", "receivable": true}` to `exclude`. Use `category`, `before` or `after` (YYYY-MM) to narrow it. Rebuild. Excluded spending leaves every total and appears in its center.
- **Clean or merge vendor names:** add `[regex, "Clean Name"]` to `aliasRules` and rebuild. For quick fixes the person can use the Aliases box on the Vendors tab, which saves in their browser.
- **Add a dependent tab:** set `dependent` to `{label, center, note, matchRegex, from, to, items, tripShare, leftOut}`. `matchRegex` picks charges by vendor between `from` and `to`; `items` adds rows by hand; `tripShare` gives the dependent a share of a family trip; tagging a vendor with the label in lower case adds all its charges.
- **Hobbies, places, shopping:** see the comments in `config.example.json`, one per key.

## Care points

- Treat every transaction, name and amount as private. Do not copy them into shared files, commit messages or public repositories.
- Never invent numbers. If something looks off, say what you see and ask.
- The tax set-aside and the projection are rough arithmetic, not tax or financial advice. Say so when you present them.
