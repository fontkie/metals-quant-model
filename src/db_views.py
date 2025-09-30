import sqlite3, sys
from pathlib import Path
import yaml

def create_standard_view(db_path: str, cfg_path: str, view_name: str = "prices_std"):
    db = Path(db_path)
    cfg = yaml.safe_load(Path(cfg_path).read_text())
    # Choose the active schema; e.g. "copper_v1"
    sch = cfg["schemas"][cfg["active"]]

    # Map real table/cols -> standard names
    table = sch["table"]                 # e.g. "prices"
    col_date = sch["date"]
    col_3m   = sch["px_3m"]
    col_cash = sch["px_cash"]

    sql = f"""
    DROP VIEW IF EXISTS {view_name};
    CREATE VIEW {view_name} AS
    SELECT
      {col_date} AS date,
      {col_3m}   AS px_3m,
      {col_cash} AS px_cash
    FROM {table};
    """
    with sqlite3.connect(db) as con:
        con.executescript(sql)
    print(f"[OK] Created view '{view_name}' on {db}")
    
if __name__ == "__main__":
    # usage: python src/db_views.py db/copper/quant.db config/schema.yaml
    create_standard_view(sys.argv[1], sys.argv[2])
