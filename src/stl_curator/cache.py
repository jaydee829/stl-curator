from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from stl_curator.scan import FileRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
  rel_path TEXT PRIMARY KEY, hash TEXT NOT NULL,
  size INTEGER, mtime REAL, kind TEXT);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(hash);
CREATE TABLE IF NOT EXISTS mesh_facts(
  hash TEXT PRIMARY KEY, height_mm REAL, triangles INTEGER,
  watertight INTEGER, error TEXT);
CREATE TABLE IF NOT EXISTS groups(
  group_id TEXT PRIMARY KEY, member_hashes TEXT NOT NULL,
  member_paths TEXT NOT NULL DEFAULT '[]',
  confidence REAL, human_claimed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS thumbs(hash TEXT PRIMARY KEY, source TEXT);
"""


class Cache:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def upsert_file(self, rec: FileRecord) -> None:
        self.conn.execute(
            "INSERT INTO files(rel_path,hash,size,mtime,kind) VALUES(?,?,?,?,?) "
            "ON CONFLICT(rel_path) DO UPDATE SET hash=excluded.hash, "
            "size=excluded.size, mtime=excluded.mtime, kind=excluded.kind",
            (rec.rel_path, rec.hash, rec.size, rec.mtime, rec.kind),
        )
        self.conn.commit()

    def file_unchanged(self, rec: FileRecord) -> bool:
        row = self.conn.execute(
            "SELECT hash FROM files WHERE rel_path=?", (rec.rel_path,)
        ).fetchone()
        return bool(row) and row["hash"] == rec.hash

    def get_files(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM files ORDER BY rel_path").fetchall()

    def set_mesh_facts(self, hash: str, height_mm, triangles, watertight, error) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO mesh_facts VALUES(?,?,?,?,?)",
            (hash, height_mm, triangles, None if watertight is None else int(watertight), error),
        )
        self.conn.commit()

    def get_mesh_facts(self, hash: str):
        return self.conn.execute("SELECT * FROM mesh_facts WHERE hash=?", (hash,)).fetchone()

    def upsert_group(
        self,
        group_id: str,
        member_hashes: list[str],
        confidence: float,
        human_claimed: bool = False,
        member_paths: list[str] | None = None,
    ) -> None:
        """Upsert a group row.

        `member_hashes` and `member_paths` are parallel but independent
        views of a group's membership: hashes are content identity (what a
        file IS), paths are location identity (WHERE it is). They are not
        interchangeable — the same hash can legitimately appear at two
        different paths (content-identical files in different folders), so
        claim/exclusion decisions must key off `member_paths`, never
        `member_hashes` alone (see `claimed_paths`). `member_paths` defaults
        to an empty list for callers that only care about hash bookkeeping
        (e.g. mesh-fact-adjacent tests).
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO groups(group_id, member_hashes, member_paths, "
            "confidence, human_claimed) VALUES(?,?,?,?,?)",
            (
                group_id,
                json.dumps(sorted(member_hashes)),
                json.dumps(sorted(member_paths or [])),
                confidence,
                int(human_claimed),
            ),
        )
        self.conn.commit()

    def group_members(self, group_id: str) -> set[str]:
        row = self.conn.execute(
            "SELECT member_hashes FROM groups WHERE group_id=?", (group_id,)
        ).fetchone()
        if row is None:
            return set()
        return set(json.loads(row["member_hashes"]))

    def claimed_paths(self) -> set[str]:
        """Rel-paths excluded from future regrouping (human-diverged groups).

        Path-scoped, not hash-scoped: two different physical files can share
        a content hash (a legitimate cross-folder duplicate) without sharing
        a location. Excluding by hash would collaterally exclude every file
        with that hash anywhere in the store the moment ANY one of them got
        claimed — this is what a rel_path-keyed exclusion set avoids.
        """
        out: set[str] = set()
        for row in self.conn.execute("SELECT member_paths FROM groups WHERE human_claimed=1"):
            out.update(json.loads(row["member_paths"]))
        return out

    def set_thumb(self, hash: str, source: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO thumbs VALUES(?,?)", (hash, source))
        self.conn.commit()

    def duplicate_hashes(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        rows = self.conn.execute(
            "SELECT hash, rel_path FROM files WHERE hash IN "
            "(SELECT hash FROM files GROUP BY hash HAVING COUNT(*)>1) "
            "ORDER BY hash, rel_path"
        ).fetchall()
        for r in rows:
            out.setdefault(r["hash"], []).append(r["rel_path"])
        return out

    def clear(self) -> None:
        for t in ("files", "mesh_facts", "groups", "thumbs"):
            self.conn.execute(f"DROP TABLE IF EXISTS {t}")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
