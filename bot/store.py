import sqlite3
from dataclasses import dataclass

from .providers import Video


@dataclass(frozen=True)
class Subscription:
    id: int
    kind: str
    source: str
    channel_id: int


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, source TEXT NOT NULL,
                channel_id INTEGER NOT NULL, UNIQUE(kind, source, channel_id));
            CREATE TABLE IF NOT EXISTS seen (
                subscription_id INTEGER REFERENCES subscriptions(id) ON DELETE CASCADE,
                video_id TEXT NOT NULL, PRIMARY KEY(subscription_id, video_id));
            CREATE TABLE IF NOT EXISTS pending (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER REFERENCES subscriptions(id) ON DELETE CASCADE,
                video_id TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
                UNIQUE(subscription_id, video_id));
        """)

    def all(self):
        return [Subscription(*row) for row in self.db.execute("SELECT * FROM subscriptions ORDER BY id")]

    def add(self, kind, source, channel_id, baseline):
        # Baseline and subscription are committed together. Duplicate add never swallows pending videos.
        with self.db:
            cursor = self.db.execute("INSERT INTO subscriptions(kind,source,channel_id) VALUES(?,?,?)",
                                     (kind, source, channel_id))
            sub_id = cursor.lastrowid
            self.db.executemany("INSERT OR IGNORE INTO seen VALUES(?,?)", [(sub_id, v.id) for v in baseline])
        return sub_id

    def contains(self, sub_id, video_id):
        return self.db.execute("SELECT 1 FROM seen WHERE subscription_id=? AND video_id=?",
                               (sub_id, video_id)).fetchone() is not None

    def mark(self, sub_id, video_id):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO seen VALUES(?,?)", (sub_id, video_id))
            self.db.execute("DELETE FROM pending WHERE subscription_id=? AND video_id=?", (sub_id, video_id))

    def enqueue(self, sub_id, videos):
        with self.db:
            for video in videos:
                if not self.contains(sub_id, video.id):
                    self.db.execute("INSERT OR IGNORE INTO pending(subscription_id,video_id,title,url) "
                                    "VALUES(?,?,?,?)", (sub_id, video.id, video.title, video.url))

    def pending(self, sub_id, limit):
        return [Video(*row) for row in self.db.execute(
            "SELECT video_id,title,url FROM pending WHERE subscription_id=? ORDER BY sequence LIMIT ?",
            (sub_id, limit))]

    def remove(self, sub_id):
        with self.db:
            return self.db.execute("DELETE FROM subscriptions WHERE id=?", (sub_id,)).rowcount > 0

    def close(self):
        self.db.close()
