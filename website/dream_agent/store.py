import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def now():
    return datetime.now(timezone.utc).isoformat()


BASE = {"checks": [], "lessons": []}


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS proposals(id INTEGER PRIMARY KEY, base INTEGER NOT NULL,
            body TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, time TEXT NOT NULL,
            event TEXT NOT NULL, body TEXT NOT NULL, previous TEXT NOT NULL, digest TEXT NOT NULL);
        ''')
        with self.transaction():
            if not self.db.execute("SELECT 1 FROM versions").fetchone():
                self.db.execute("INSERT INTO versions VALUES (1,?)", (encode(BASE),))
                self.db.execute("INSERT INTO state VALUES ('active','1')")
                self.log("initialized", {"version": 1})

    @contextmanager
    def transaction(self):
        nested = self.db.in_transaction
        self.db.execute("SAVEPOINT nested" if nested else "BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("RELEASE nested" if nested else "COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK TO nested" if nested else "ROLLBACK")
            if nested:
                self.db.execute("RELEASE nested")
            raise

    def close(self):
        self.db.close()

    def log(self, event, body):
        row = self.db.execute("SELECT digest FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        previous = row[0] if row else "0" * 64
        stamp, payload = now(), encode(body)
        digest = hashlib.sha256(encode([stamp, event, payload, previous]).encode()).hexdigest()
        self.db.execute("INSERT INTO audit(time,event,body,previous,digest) VALUES(?,?,?,?,?)",
                        (stamp, event, payload, previous, digest))

    def verify(self):
        previous = "0" * 64
        for row in self.db.execute("SELECT * FROM audit ORDER BY id"):
            expected = hashlib.sha256(encode([row['time'], row['event'], row['body'], previous]).encode()).hexdigest()
            if row['previous'] != previous or row['digest'] != expected:
                return False
            previous = expected
        return True

    def active(self):
        version = int(self.db.execute("SELECT value FROM state WHERE key='active'").fetchone()[0])
        return version, self.version(version)

    def version(self, version):
        row = self.db.execute("SELECT body FROM versions WHERE id=?", (version,)).fetchone()
        if row is None:
            raise ValueError("Unknown version")
        return json.loads(row[0])

    def runs(self):
        return [dict(id=r['id'], **json.loads(r['body'])) for r in self.db.execute("SELECT * FROM runs ORDER BY id")]

    def proposals(self):
        return [dict(id=r['id'], base=r['base'], status=r['status'], **json.loads(r['body']))
                for r in self.db.execute("SELECT * FROM proposals ORDER BY id")]
