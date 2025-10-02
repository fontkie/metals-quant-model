📄 README.md
# Base Metals Quant Model

# Metals Quant Model

End-to-end workflow for uploading raw pricing data from Excel, storing in SQLite, building signals, and backtesting.

---

## Folder structure

```text
Metals/
  Copper/
    pricing_values.xlsx   # Raw input Excel (sheet: Raw, col A: Date, other cols = price series)
    quant.db              # Auto-created SQLite database
  outputs/
    Copper/               # Signals + backtest outputs
  src/
    load_data.py          # Load Excel → SQLite (prices table, clean-load replace mode)
    build_signals.py      # Generate momentum, hook, carry signals → CSV
    backtest_prices.py    # Simple backtester (reads prices_std + signals)
    test_db.py            # Sanity checks (prices_long + signals)
    fix_views.py          # Creates views: prices_long (long), prices_std (wide)
    list_series.py        # Inspect DB tables, views, and distinct symbols
    write_last_run.py     # Writes LAST_RUN.json snapshot
  run_all.bat             # One-click pipeline
  setup_once.bat          # One-time environment setup
  requirements.txt        # Python package list
  README.md
  CHANGELOG.md

Quickstart

Clone repo and open Command Prompt (not PowerShell).

Go to project folder:

cd C:\Code\Metals


One-time setup (creates .venv and installs packages):

setup_once.bat


Put your raw data in:

Copper\pricing_values.xlsx


Sheet: Raw
Column A: Date
Other columns: price series (e.g. copper_lme_3mo, copper_lme_cash_3mo, …)

Run (clean load → views → quick check):

python src\load_data.py --db Copper\quant.db --xlsx Copper\pricing_values.xlsx --mode replace
python src\fix_views.py --db Copper\quant.db
python src\list_series.py --db Copper\quant.db


(Optional one-click full run)

run_all.bat


Steps performed:

Load Excel → SQLite prices(date, symbol, price)

Create DB views:

prices_long(date, symbol, price) tidy view for checks

prices_std(date, …series…) wide pivot for backtest

Build signals (signals_export.csv)

Run sanity checks

Run backtest (saves curves, summary, charts in outputs\Copper)

Check outputs:

outputs\Copper\signals_export.csv

outputs\Copper\backtest_summary_prices.csv

outputs\Copper\equity_curves_prices.csv

outputs\Copper\charts\...

DB schema

Canonical table: prices(date, symbol, price)

Views / tables created by the pipeline:

prices_long(date, symbol, price) – tidy view for checks

prices_std(date, …series…) – wide pivot for signals/backtests

Daily workflow

Update Excel file

Run run_all.bat

Review new outputs in outputs\Copper

Snapshot for new chats:
After each run, write_last_run.py saves:

outputs\LAST_RUN.json


Paste that JSON + repo link into a new chat and everything can be picked up immediately.

Requirements

See requirements.txt. Installed automatically by setup_once.bat.

pandas

numpy

matplotlib

sqlalchemy

openpyxl

Utilities

list_series.py – inspect DB tables, views, and distinct symbols.
Usage:

python src\list_series.py --db Copper\quant.db

Troubleshooting

Old column names showing up?
Re-run loader with clean mode:

python src\load_data.py --db Copper\quant.db --xlsx Copper\pricing_values.xlsx --mode replace