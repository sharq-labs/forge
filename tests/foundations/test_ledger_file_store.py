"""The file-backed ledger store on every platform.

Until 2026-10-13 ``FileLedgerStore.append`` imported ``fcntl`` inside the method, so every file-backed ledger raised
``ModuleNotFoundError`` on Windows the first time it wrote -- the authority ledger, the durable campaigns and the
battery blind dry run with it. The lock is ``flock`` on POSIX and a byte-range lock past the end of the file on
Windows; the bytes on disk are the same LF-terminated lines on both.
"""

from __future__ import annotations

import pytest

from engcore.authority.keys import AuthorityRefused
from engcore.authority.ledger import FileLedgerStore


def test_appends_are_lf_terminated_lines_on_every_platform(tmp_path) -> None:
    store = FileLedgerStore(tmp_path / "ledger.jsonl")
    store.append('{"n":0}', expected_lines=0)
    store.append('{"n":1}', expected_lines=1)
    assert (tmp_path / "ledger.jsonl").read_bytes() == b'{"n":0}\n{"n":1}\n'
    assert store.read() == ['{"n":0}', '{"n":1}']


def test_a_writer_that_verified_a_shorter_file_is_refused(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    first, second = FileLedgerStore(path), FileLedgerStore(path)
    first.append('{"n":0}', expected_lines=0)
    with pytest.raises(AuthorityRefused, match="another writer appended"):
        second.append('{"n":0,"fork":true}', expected_lines=0)
    assert path.read_bytes() == b'{"n":0}\n'


def test_a_line_holds_one_event(tmp_path) -> None:
    with pytest.raises(AuthorityRefused, match="one event"):
        FileLedgerStore(tmp_path / "ledger.jsonl").append('{"n":0}\n{"n":1}', expected_lines=0)


def test_a_second_writer_waits_for_the_lock_and_then_sees_what_was_appended_under_it(tmp_path) -> None:
    """The ``expected_lines`` guard is atomic only under the lock (review finding F7): a writer must not count the
    file while another writer holds the lock, or both could count n and both append event n."""
    import os
    import threading

    from engcore.authority.ledger import _exclusive

    path = tmp_path / "ledger.jsonl"
    FileLedgerStore(path).append('{"n":0}', expected_lines=0)
    outcome: list[object] = []

    def second_writer() -> None:
        try:
            FileLedgerStore(path).append('{"n":1,"writer":"second"}', expected_lines=1)
            outcome.append("appended")
        except AuthorityRefused as exc:
            outcome.append(exc)

    fd = os.open(path, os.O_RDWR | os.O_APPEND | getattr(os, "O_BINARY", 0))
    try:
        with _exclusive(fd):
            writer = threading.Thread(target=second_writer)
            writer.start()
            writer.join(0.5)
            assert writer.is_alive() and outcome == []  # blocked on the lock, has not counted the file
            os.write(fd, b'{"n":1,"writer":"first"}\n')
    finally:
        os.close(fd)
    writer.join(15)
    assert not writer.is_alive()
    (result,) = outcome
    assert isinstance(result, AuthorityRefused) and "another writer appended" in str(result)
    assert path.read_bytes() == b'{"n":0}\n{"n":1,"writer":"first"}\n'


def test_the_lock_is_released_after_a_refused_append(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    store = FileLedgerStore(path)
    store.append('{"n":0}', expected_lines=0)
    with pytest.raises(AuthorityRefused):
        store.append('{"n":1}', expected_lines=5)
    store.append('{"n":1}', expected_lines=1)  # would block (POSIX) or be refused (Windows) if the lock leaked
    assert store.read() == ['{"n":0}', '{"n":1}']
