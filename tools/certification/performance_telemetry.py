"""Best-effort execution diagnostics, never consumed by certification."""
from __future__ import annotations

from contextlib import contextmanager
import json
import pathlib
import os
import stat
import tempfile
import time

PERFORMANCE_SCHEMA = "forge.local_assurance_performance/1"


class PerformanceTelemetry:
    def __init__(self, path, *, shard=None):
        self.path = pathlib.Path(path).absolute() if path is not None else None
        self.parent_identities = None
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.parent_identities = self._parent_chain()
            except Exception:
                pass
        self.seconds = {}
        self.counts = {}
        self.counters = {"seed_bytes_from_cache": 0}
        self.details = {"shard": shard, "mutation_id": None,
                        "worker_retained": False, "descendant_quiescence": None,
                        "source_commit": os.environ.get("FORGE_SOURCE_COMMIT"),
                        "source_tree": os.environ.get("FORGE_SOURCE_TREE"),
                        "execution": os.environ.get("FORGE_ASSURANCE_EXECUTION"),
                        "retained_path": None}
        self.lifecycle_stage = None
        self.lifecycle = []
        self.failures = []

    @staticmethod
    def start():
        try:
            return time.monotonic()
        except Exception:
            return None

    def add_seconds(self, category, seconds):
        try:
            self.seconds[category] = self.seconds.get(category, 0.0) + seconds
            self.counts[category] = self.counts.get(category, 0) + 1
        except Exception:
            pass

    def increment(self, category, amount=1):
        try:
            self.counters[category] = self.counters.get(category, 0) + amount
        except Exception:
            pass

    def finish(self, category, started):
        try:
            if started is not None:
                self.add_seconds(category, time.monotonic() - started)
        except Exception:
            pass

    @contextmanager
    def measure(self, category):
        started = self.start()
        try:
            yield
        finally:
            self.finish(category, started)

    def context(self, **fields):
        try:
            self.details.update(fields)
        except Exception:
            pass

    def stage(self, name, **fields):
        try:
            self.lifecycle_stage = name
            self.lifecycle.append({**self.details, "stage": name, **fields})
        except Exception:
            pass

    def failure(self, exc, *, category=None):
        try:
            relative = getattr(exc, "path", None)
            if relative is not None and (pathlib.PurePosixPath(relative).is_absolute()
                                        or ".." in pathlib.PurePosixPath(relative).parts):
                relative = None
            self.failures.append({**self.details, "stage": self.lifecycle_stage,
                                  "category": category or type(exc).__name__,
                                  "affected_path": relative, "message": str(exc)})
            self.write()
        except Exception:
            pass

    def document(self):
        return {"schema": PERFORMANCE_SCHEMA,
                "certification_authority": False, "safe_to_push_authority": False,
                "seconds": dict(sorted(self.seconds.items())),
                "samples": dict(sorted(self.counts.items())),
                "counters": dict(sorted(self.counters.items())),
                "context": dict(self.details), "lifecycle_stage": self.lifecycle_stage,
                "lifecycle": list(self.lifecycle), "failures": list(self.failures)}

    def _parent_chain(self):
        rows = []
        for path in (self.path.parent, *self.path.parent.parents):
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or path.resolve() != path.absolute():
                raise OSError("diagnostic parent is linked or substituted")
            rows.append((str(path), info.st_dev, info.st_ino))
        return tuple(rows)

    def write(self, document=None):
        # Semantics A: unavailable telemetry is ignorable, never gate authority.
        # Replace a fresh file; never open a possibly linked diagnostic destination.
        if self.path is None or self.parent_identities is None:
            return
        temporary = None
        try:
            if self._parent_chain() != self.parent_identities:
                return
            fd, name = tempfile.mkstemp(prefix=".forge-performance-", dir=self.path.parent)
            temporary = pathlib.Path(name)
            try:
                handle = os.fdopen(fd, "w", encoding="utf-8")
            except BaseException:
                os.close(fd)
                raise
            with handle:
                json.dump(self.document() if document is None else document, handle, indent=2, sort_keys=True)
                handle.write("\n")
            if self._parent_chain() != self.parent_identities:
                return
            os.replace(temporary, self.path)
        except Exception:
            pass
        finally:
            # Do not follow a substituted parent even to clean a temporary file.
            try:
                if temporary is not None and self._parent_chain() == self.parent_identities:
                    temporary.unlink(missing_ok=True)
            except Exception:
                pass


def is_performance_document(document):
    return (isinstance(document, dict)
            and document.get("schema") == PERFORMANCE_SCHEMA
            and document.get("certification_authority") is False
            and document.get("safe_to_push_authority") is False)
