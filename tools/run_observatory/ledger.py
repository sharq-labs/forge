"""The run root and its SQLite index.

Layout of a run root (outside any repository; safe to delete -- nothing in FORGE reads it)::

    <run-root>/
        ledger.sqlite      searchable index (WAL); rebuildable from receipts/ with ``reindex``
        host_salt          random salt for the pseudonymous host id
        receipts/          one sealed, read-only JSON receipt per run -- the canonical record
        receipts/quarantine/  pending receipts too damaged to recover
        logs/              redacted stdout / stderr per run
        artifacts/<run>/   adapter reports (junit.xml) and the child's report file
        summaries/         one human-readable summary per run

Concurrency: every write is one ``BEGIN IMMEDIATE`` transaction with a 30 s busy timeout, so
simultaneous completions serialize instead of interleaving. Receipt files have unique names and
are published by hard link, so they never collide at all.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Iterator

from tools.run_observatory import LEDGER_SCHEMA_VERSION, receipt as receipt_mod

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, schema TEXT NOT NULL, run_kind TEXT NOT NULL, name TEXT, status TEXT NOT NULL,
    partial INTEGER NOT NULL, started_utc TEXT, ended_utc TEXT, wall_seconds REAL, cpu_seconds REAL,
    peak_rss_bytes REAL, io_read_bytes REAL, io_write_bytes REAL, exit_code INTEGER,
    git_sha TEXT, git_branch TEXT, tree_clean INTEGER, code_identity TEXT,
    workload_id TEXT, environment_id TEXT, comparison_group TEXT, parent_run_id TEXT, replay_of TEXT,
    adapter TEXT, comparability TEXT, performance TEXT, baseline_run_id TEXT,
    receipt_path TEXT NOT NULL, receipt_sha256 TEXT NOT NULL, indexed_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (run_id TEXT NOT NULL, tag TEXT NOT NULL, PRIMARY KEY (run_id, tag));
CREATE TABLE IF NOT EXISTS counters (run_id TEXT NOT NULL, name TEXT NOT NULL, value REAL, source TEXT,
                                     PRIMARY KEY (run_id, name));
CREATE TABLE IF NOT EXISTS failures (run_id TEXT NOT NULL, nodeid TEXT NOT NULL, PRIMARY KEY (run_id, nodeid));
CREATE INDEX IF NOT EXISTS runs_workload ON runs (workload_id, started_utc);
CREATE INDEX IF NOT EXISTS runs_sha ON runs (git_sha);
CREATE INDEX IF NOT EXISTS runs_kind ON runs (run_kind, started_utc);
CREATE INDEX IF NOT EXISTS runs_started ON runs (started_utc);
"""

_RETRY_SECONDS = 60.0


class LedgerConflict(RuntimeError):
    """A run id already indexed with a different receipt digest."""


def _metric(rec: dict, name: str):
    return ((rec.get("resources") or {}).get(name) or {}).get("value")


class Ledger:
    def __init__(self, run_root: Path | str) -> None:
        self.root = Path(run_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "ledger.sqlite"
        self._retry(self._ensure_schema)

    # -- plumbing -------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=30000")
        return con

    @staticmethod
    def _retry(action):
        deadline = time.monotonic() + _RETRY_SECONDS
        while True:
            try:
                return action()
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc) and "busy" not in str(exc) or time.monotonic() > deadline:
                    raise
                time.sleep(0.05)

    def _ensure_schema(self) -> None:
        con = self._connect()
        try:
            if con.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                con.execute("PRAGMA journal_mode=WAL")
            con.execute("BEGIN IMMEDIATE")
            try:
                for statement in _SCHEMA.split(";"):
                    if statement.strip():
                        con.execute(statement)
                con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('ledger_schema_version', ?)",
                            (str(LEDGER_SCHEMA_VERSION),))
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
        finally:
            con.close()

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        con = self._connect()
        try:
            return [dict(row) for row in con.execute(sql, params).fetchall()]
        finally:
            con.close()

    def journal_mode(self) -> str:
        return self._query("PRAGMA journal_mode")[0]["journal_mode"].lower()

    # -- writes ---------------------------------------------------------------

    def index(self, rec: dict, receipt_path: Path) -> bool:
        """Index a sealed receipt. True when inserted, False when already present with the same digest."""
        if not receipt_mod.verify(rec):
            raise ValueError(f"refusing to index a receipt that does not verify: {rec.get('run_id')}")
        return self._retry(lambda: self._index(rec, Path(receipt_path)))

    def _index(self, rec: dict, receipt_path: Path) -> bool:
        git, result = rec.get("git") or {}, rec.get("result") or {}
        comparison, parent = rec.get("comparison") or {}, rec.get("parent") or {}
        try:
            rel = receipt_path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            rel = str(receipt_path)
        row = {
            "run_id": rec["run_id"], "schema": rec["schema"], "run_kind": rec["run_kind"], "name": rec.get("name"),
            "status": result.get("status"), "partial": int(bool(rec.get("partial"))),
            "started_utc": rec["timing"].get("started_utc"), "ended_utc": rec["timing"].get("ended_utc"),
            "wall_seconds": rec["timing"].get("wall_seconds"), "cpu_seconds": _metric(rec, "cpu_seconds"),
            "peak_rss_bytes": _metric(rec, "peak_rss_bytes"), "io_read_bytes": _metric(rec, "io_read_bytes"),
            "io_write_bytes": _metric(rec, "io_write_bytes"), "exit_code": result.get("exit_code"),
            "git_sha": git.get("head_sha"), "git_branch": git.get("branch"),
            "tree_clean": None if git.get("tree_clean") is None else int(git["tree_clean"]),
            "code_identity": git.get("code_identity"),
            "workload_id": (rec.get("workload") or {}).get("workload_id"),
            "environment_id": (rec.get("environment") or {}).get("environment_id"),
            "comparison_group": parent.get("comparison_group"), "parent_run_id": parent.get("parent_run_id"),
            "replay_of": parent.get("replay_of"), "adapter": (rec.get("command") or {}).get("adapter"),
            "comparability": comparison.get("comparability"), "performance": comparison.get("performance"),
            "baseline_run_id": comparison.get("baseline_run_id"),
            "receipt_path": rel, "receipt_sha256": receipt_mod.digest_of(rec),
            "indexed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            try:
                existing = con.execute("SELECT receipt_sha256 FROM runs WHERE run_id = ?", (row["run_id"],)).fetchone()
                if existing is not None:
                    con.execute("ROLLBACK")
                    if existing[0] != row["receipt_sha256"]:
                        raise LedgerConflict(f"{row['run_id']} is already indexed with a different digest")
                    return False
                con.execute(f"INSERT INTO runs ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                            tuple(row.values()))
                con.executemany("INSERT OR IGNORE INTO tags (run_id, tag) VALUES (?, ?)",
                                [(row["run_id"], t) for t in rec.get("tags") or ()])
                values = (rec.get("counters") or {}).get("values") or {}
                con.executemany("INSERT INTO counters (run_id, name, value, source) VALUES (?, ?, ?, ?)",
                                [(row["run_id"], k, v.get("value"), v.get("source")) for k, v in values.items()])
                outcomes = result.get("adapter_outcomes") or {}
                con.executemany("INSERT OR IGNORE INTO failures (run_id, nodeid) VALUES (?, ?)",
                                [(row["run_id"], n) for n in outcomes.get("failure_set") or ()])
                con.execute("COMMIT")
                return True
            except LedgerConflict:
                raise
            except BaseException:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        finally:
            con.close()

    def reindex(self) -> dict:
        """Rebuild the index from the receipt files, the canonical source."""
        indexed, rejected = 0, []
        for path in self.receipt_files():
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                rejected.append(path.name)
                continue
            if not receipt_mod.verify(rec):
                rejected.append(path.name)
                continue
            if self.index(rec, path):
                indexed += 1
        return {"indexed": indexed, "rejected": rejected}

    # -- reads ----------------------------------------------------------------

    def receipt_files(self) -> Iterator[Path]:
        folder = self.root / "receipts"
        if folder.is_dir():
            yield from sorted(p for p in folder.glob("*.json") if not p.name.endswith(".pending.json"))

    def get(self, run_id: str) -> dict | None:
        rows = self._query("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        return rows[0] if rows else None

    def load_receipt(self, run_id: str) -> dict | None:
        row = self.get(run_id)
        path = (self.root / row["receipt_path"]) if row else self.root / "receipts" / f"{run_id}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def verify_receipt(self, rec: dict) -> str:
        """VALID, INTEGRITY_FAILED (the seal is broken), LEDGER_MISMATCH (re-sealed after indexing), NOT_INDEXED."""
        if not receipt_mod.verify(rec):
            return "INTEGRITY_FAILED"
        row = self.get(rec.get("run_id", ""))
        if row is None:
            return "NOT_INDEXED"
        return "VALID" if row["receipt_sha256"] == receipt_mod.digest_of(rec) else "LEDGER_MISMATCH"

    _ORDER = " ORDER BY started_utc DESC, rowid DESC"

    def latest(self, limit: int = 20) -> list[dict]:
        return self._query("SELECT * FROM runs" + self._ORDER + " LIMIT ?", (limit,))

    def by_kind(self, kind: str, limit: int = 100) -> list[dict]:
        return self._query("SELECT * FROM runs WHERE run_kind = ?" + self._ORDER + " LIMIT ?", (kind, limit))

    def by_workload(self, workload_id: str, limit: int = 100) -> list[dict]:
        return self._query("SELECT * FROM runs WHERE workload_id = ?" + self._ORDER + " LIMIT ?", (workload_id, limit))

    def by_git_sha(self, sha: str, limit: int = 100) -> list[dict]:
        return self._query("SELECT * FROM runs WHERE git_sha LIKE ?" + self._ORDER + " LIMIT ?", (sha + "%", limit))

    def failed(self, limit: int = 100) -> list[dict]:
        return self._query("SELECT * FROM runs WHERE status IN ('RUN_FAIL', 'RUN_ERROR')" + self._ORDER + " LIMIT ?",
                           (limit,))

    def history(self, workload_id: str) -> list[dict]:
        """Every run of one workload, oldest first: the performance history."""
        return self._query("SELECT run_id, started_utc, status, partial, wall_seconds, cpu_seconds, peak_rss_bytes, "
                           "io_read_bytes, io_write_bytes, git_sha, tree_clean, code_identity, environment_id, "
                           "comparability, performance, baseline_run_id FROM runs WHERE workload_id = ? "
                           "ORDER BY started_utc ASC, rowid ASC", (workload_id,))

    def fastest_exact_comparable(self, run_id: str) -> dict | None:
        """The fastest completed run with the same workload, environment and code as ``run_id``."""
        ref = self.get(run_id)
        if ref is None or ref["code_identity"] is None:
            return None
        rows = self._query("SELECT * FROM runs WHERE workload_id = ? AND environment_id = ? AND code_identity = ? "
                           "AND partial = 0 AND status = ? AND wall_seconds IS NOT NULL "
                           "ORDER BY wall_seconds ASC LIMIT 1",
                           (ref["workload_id"], ref["environment_id"], ref["code_identity"], ref["status"]))
        return rows[0] if rows else None

    def find_baseline(self, rec: dict) -> dict | None:
        """The most informative earlier run to compare ``rec`` with.

        Same workload, environment and code first; then same workload and environment; then same
        workload; then the same comparison group, or name, so a changed workload is still reported
        as a WORKLOAD_VARIANT instead of silently having no baseline.
        """
        workload = (rec.get("workload") or {}).get("workload_id")
        environment = (rec.get("environment") or {}).get("environment_id")
        code = (rec.get("git") or {}).get("code_identity")
        run_id = rec.get("run_id")
        base = "SELECT * FROM runs WHERE partial = 0 AND run_id != ? AND "
        attempts = []
        if workload:
            if environment and code:
                attempts.append(("workload_id = ? AND environment_id = ? AND code_identity = ?",
                                 (workload, environment, code)))
            if environment:
                attempts.append(("workload_id = ? AND environment_id = ?", (workload, environment)))
            attempts.append(("workload_id = ?", (workload,)))
        group = (rec.get("parent") or {}).get("comparison_group")
        if group:
            attempts.append(("comparison_group = ?", (group,)))
        elif rec.get("name"):
            attempts.append(("name = ?", (rec["name"],)))
        for where, params in attempts:
            rows = self._query(base + where + self._ORDER + " LIMIT 1", (run_id, *params))
            if rows:
                return rows[0]
        return None


def iter_pending(run_root: Path) -> Iterator[Path]:
    folder = Path(run_root) / "receipts"
    if folder.is_dir():
        yield from sorted(folder.glob("*.pending.json"))


def quarantine(path: Path) -> Path:
    target_dir = path.parent / "quarantine"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / path.name
    os.replace(path, target)
    return target
