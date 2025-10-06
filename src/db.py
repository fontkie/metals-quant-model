from pathlib import Path
import sqlite3

def get_conn(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("""
    CREATE TABLE IF NOT EXISTS prices(
        dt TEXT NOT NULL,
        symbol TEXT NOT NULL,
        px_settle REAL NOT NULL,
        PRIMARY KEY (dt, symbol)
    )
    """)
    return con
