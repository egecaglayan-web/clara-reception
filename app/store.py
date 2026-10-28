import json
import sqlite3
import threading
import time
from pathlib import Path


class Store:
    """Small single-instance SQLite store, committed on every state transition."""

    def __init__(self, path):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS records (namespace TEXT, key TEXT, data TEXT, updated REAL, PRIMARY KEY(namespace,key))")
        self.db.commit()

    def get(self, namespace, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT data FROM records WHERE namespace=? AND key=?", (namespace, key)).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, namespace, key, value):
        with self.lock, self.db:
            self.db.execute("INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET data=excluded.data,updated=excluded.updated",
                            (namespace, key, json.dumps(value, ensure_ascii=False), time.time()))

    def all(self, namespace):
        with self.lock:
            return [(row[0], json.loads(row[1])) for row in self.db.execute("SELECT key,data FROM records WHERE namespace=?", (namespace,))]

    def prune(self, days):
        cutoff = time.time() - days * 86400
        with self.lock, self.db:
            # Uncertain side effects and deliveries wait for human review even after retention expires.
            for namespace in ("threads", "links", "messages", "ai_budget"):
                self.db.execute("DELETE FROM records WHERE namespace=? AND updated<? AND COALESCE(json_extract(data,'$.state'),'') NOT IN ('processing','uncertain')",
                                (namespace, cutoff))
            self.db.execute("DELETE FROM records WHERE namespace='outbox' AND updated<? AND json_extract(data,'$.state')='sent'", (cutoff,))
            self.db.execute("DELETE FROM records WHERE namespace='demo_sent' AND updated<?", (cutoff,))

    def close(self):
        self.db.close()
