# src/list_series.py
import argparse, sqlite3

def main(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("Tables:")
    for (name,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"):
        print(" -", name)

    print("\nViews:")
    for (name,) in cur.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name;"):
        print(" -", name)

    print("\nprices_long columns (via PRAGMA):")
    try:
        cols = [r[1] for r in cur.execute("PRAGMA table_info(prices_long);")]
        print(" - " + ", ".join(cols))
    except sqlite3.OperationalError as e:
        print(" (could not read columns)", e)

    print("\nDistinct symbols in prices_long:")
    try:
        for (sym,) in cur.execute("SELECT DISTINCT symbol FROM prices_long ORDER BY symbol;"):
            print(" -", sym)
    except sqlite3.OperationalError as e:
        print(" (could not query prices_long)", e)

    conn.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to SQLite database")
    args = ap.parse_args()
    main(args.db)
