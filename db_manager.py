import sqlite3,json
from pathlib import Path
from datetime import datetime,timezone
class Database:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True);self.path=path
        with self.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY,created_at TEXT,signal_id TEXT UNIQUE,mode TEXT,side TEXT,quantity REAL,entry REAL,stop_loss REAL,take_profit REAL,exit REAL,pnl REAL,fees REAL,status TEXT,metadata TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS bot_state(key TEXT PRIMARY KEY,value TEXT)")
    def connect(self):return sqlite3.connect(self.path)
    def save_trade(self,t):
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO trades(created_at,signal_id,mode,side,quantity,entry,stop_loss,take_profit,status,metadata) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(),t["signal_id"],t["mode"],t["side"],t["quantity"],t["entry"],t["stop_loss"],t["take_profit"],t.get("status","open"),json.dumps(t)))
    def trades(self):
        with self.connect() as c:
            c.row_factory=sqlite3.Row
            return [dict(x) for x in c.execute("SELECT * FROM trades ORDER BY id DESC")]
    def set_state(self,k,v):
        with self.connect() as c:c.execute("INSERT OR REPLACE INTO bot_state VALUES(?,?)",(k,json.dumps(v)))

    def get_state(self,k,default=None):
        with self.connect() as c:
            row=c.execute("SELECT value FROM bot_state WHERE key=?",(k,)).fetchone()
            return json.loads(row[0]) if row else default
